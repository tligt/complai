"""
RECOSA Marketing Monitor
Uses Mistral Agents API with web_search_premium to find recent EU compliance
news articles, then saves relevant items to Supabase for admin review
and LinkedIn draft generation.

No external news API needed — uses Mistral's built-in web search.
Sources/queries loaded dynamically from monitoring_sources table
where monitor_type = 'marketing'.

Run via GitHub Actions cron or manually from the admin BO.
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timezone
from database import (
    save_marketing_update,
    log_token_usage,
    load_monitoring_sources,
    start_monitor_run,
    complete_monitor_run,
)

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"
MISTRAL_API_BASE = "https://api.mistral.ai/v1"


# ── Mistral web search ────────────────────────────────────────

def search_news_with_mistral(query: str, api_key: str) -> list[dict]:
    """
    Use Mistral Agents API with web_search_premium to find recent
    news articles matching the query.
    Returns list of raw items with title, url, description, published_raw.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Step 1: Create a temporary agent with web_search_premium
    # We create one per run, could be cached but ephemeral is simpler
    agent_payload = {
        "model": "mistral-small-latest",  # Small is sufficient for search tasks
        "name":  "RECOSA-NewsSearch",
        "description": "Finds recent EU compliance news articles",
        "instructions": (
            "You are a news research assistant for RECOSA, an EU regulatory compliance platform. "
            "When asked to find news, use the web search tool to find REAL recent articles. "
            "Return results as a JSON array only — no prose, no markdown, just valid JSON. "
            "Each item must have: title, url, description (1-2 sentences), published_date (YYYY-MM-DD or empty string)."
        ),
        "tools": [{"type": "web_search_premium"}],
        "completion_args": {"temperature": 0.1},
    }

    try:
        # Create agent
        agent_resp = requests.post(
            f"{MISTRAL_API_BASE}/agents",
            headers=headers,
            json=agent_payload,
            timeout=30,
        )
        agent_resp.raise_for_status()
        agent_id = agent_resp.json().get("id")
        if not agent_id:
            print(f"  Could not create agent for query '{query}'")
            return []

        # Step 2: Start a conversation with the agent
        conv_payload = {
            "agent_id": agent_id,
            "inputs":   (
                f"Find the 8 most recent news articles published in the last 48 hours about: {query}\n\n"
                f"Focus on EU, Belgium, France context. "
                f"Return ONLY a JSON array like this:\n"
                f'[{{"title":"...","url":"...","description":"...","published_date":"YYYY-MM-DD"}}]\n'
                f"No other text."
            ),
        }

        conv_resp = requests.post(
            f"{MISTRAL_API_BASE}/conversations",
            headers=headers,
            json=conv_payload,
            timeout=60,
        )
        conv_resp.raise_for_status()
        conv_data = conv_resp.json()

        # Extract the text response from outputs
        outputs = conv_data.get("outputs", [])
        raw_text = ""
        for output in outputs:
            if output.get("type") == "message.output":
                chunks = output.get("content", [])
                for chunk in chunks:
                    if chunk.get("type") == "text":
                        raw_text += chunk.get("text", "")

        if not raw_text:
            print(f"  No text response from agent for query '{query}'")
            return []

        # Parse JSON array from response
        raw_text = re.sub(r"```json|```", "", raw_text).strip()
        match = re.search(r'\[[\s\S]*\]', raw_text)
        if not match:
            print(f"  Could not find JSON array in response for '{query}'")
            print(f"  Response preview: {raw_text[:200]}")
            return []

        articles = json.loads(match.group(0))

        # Normalise to our item format
        results = []
        for a in articles:
            title = (a.get("title") or "").strip()
            url   = (a.get("url") or "").strip()
            desc  = (a.get("description") or "").strip()
            pub   = (a.get("published_date") or "").strip()

            if not title or not url:
                continue
            if url in ("", "N/A", "unknown"):
                continue

            results.append({
                "title":        title,
                "url":          url,
                "description":  desc[:500],
                "published_raw": pub,
            })

        return results

    except json.JSONDecodeError as e:
        print(f"  JSON parse error for query '{query}': {e}")
        return []
    except Exception as e:
        print(f"  Mistral web search error for query '{query}': {e}")
        return []


# ── Mistral relevance + summary ───────────────────────────────

def analyse_for_marketing(
    items: list[dict],
    source_config: dict,
    api_key: str,
) -> tuple[list[dict], int, int]:
    """
    Filter and summarise items for RECOSA marketing relevance using Mistral.
    Returns (relevant_items, input_tokens_total, output_tokens_total).
    """
    if not items or not api_key:
        return [], 0, 0

    results      = []
    total_input  = 0
    total_output = 0

    for item in items:
        title = item["title"]
        desc  = item.get("description", "")

        system_prompt = """You are a content strategist for RECOSA, an EU regulatory compliance SaaS
platform helping SMEs in Belgium and France comply with GDPR, NIS2, and the EU AI Act.

Analyse this news item and return ONLY valid JSON:
{
  "relevant": true/false,
  "relevance_reason": "one sentence explaining why this is or isn't relevant to RECOSA",
  "summary": "2-3 sentence summary from the perspective of an EU compliance professional",
  "severity": "info|important|urgent",
  "content_angle": "enforcement|policy|guidance|market|tech|other"
}

relevant: true if useful for:
- Understanding the regulatory landscape RECOSA operates in
- Competitor or market intelligence
- LinkedIn post inspiration about EU compliance for SMEs
- News a compliance officer in Belgium or France would care about

relevant: false for generic tech news unrelated to EU compliance, US-only news,
sports, entertainment, or articles with no useful compliance angle."""

        user_prompt = (
            f"SOURCE: {source_config['name']} ({source_config.get('category', '')})\n"
            f"SEARCH QUERY: {source_config.get('query', '')}\n"
            f"TITLE: {title}\n"
            f"CONTENT: {desc}\n\n"
            f"Is this relevant for RECOSA's marketing and content strategy?"
        )

        try:
            resp = requests.post(
                f"{MISTRAL_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       "mistral-large-latest",
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "max_tokens": 300,
                },
                timeout=30,
            )
            resp.raise_for_status()
            _rdata   = resp.json()
            _usage   = _rdata.get("usage", {})
            total_input  += _usage.get("prompt_tokens", 0)
            total_output += _usage.get("completion_tokens", 0)

            raw = _rdata["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            m   = re.search(r'\{[\s\S]*\}', raw)
            if m:
                raw = m.group(0)

            analysis = json.loads(raw)
            if not analysis.get("relevant", False):
                continue

            results.append({
                "source":           source_config["name"],
                "category":         source_config.get("category", ""),
                "title":            title,
                "summary":          analysis.get("summary", desc[:300]),
                "url":              item["url"],
                "severity":         analysis.get("severity", "info"),
                "relevance_reason": analysis.get("relevance_reason", ""),
                "published_at":     _parse_date(item.get("published_raw", "")),
                "status":           "pending",
            })

            time.sleep(0.3)

        except Exception as e:
            print(f"  Could not analyse '{title[:50]}': {e}")
            continue

    return results, total_input, total_output


def _parse_date(date_str: str) -> str | None:
    if not date_str:
        return None
    formats = [
        "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


# ── Main marketing monitoring run ─────────────────────────────

def run_marketing_monitoring(triggered_by: str = "cron") -> dict:
    """
    Main entry point. Loads marketing sources from DB, searches via
    Mistral web_search_premium, filters with Mistral, saves results.
    """
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        return {"error": "MISTRAL_API_KEY not set", "saved": 0, "skipped": 0}

    print(f"\nRECOSA Marketing Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    run_id  = start_monitor_run("marketing", triggered_by=triggered_by)
    sources = load_monitoring_sources(monitor_type="marketing")

    if not sources:
        print("  No active marketing sources found in DB.")
        if run_id:
            complete_monitor_run(run_id, 0, 0, 0, 0, [], {},
                                 status="completed",
                                 error_message="No active sources")
        return {"fetched": 0, "saved": 0, "skipped": 0, "errors": 0}

    print(f"Loaded {len(sources)} active marketing sources from DB.")

    total_fetched = total_saved = total_skipped = total_errors = 0
    total_in = total_out = 0
    source_stats = []

    for source in sources:
        fetch_type = source.get("fetch_type", "search")
        print(f"\n[{source.get('category','')}] {source['name']} via {fetch_type.upper()}...")

        stat = {
            "name":    source["name"],
            "fetched": 0,
            "saved":   0,
            "skipped": 0,
            "error":   None,
        }

        try:
            if fetch_type == "search":
                query = source.get("query", "")
                if not query:
                    print("  No query defined — skipping.")
                    source_stats.append(stat)
                    continue
                raw_items = search_news_with_mistral(query, api_key)
            else:
                # RSS/scrape fallback — not primary but kept for flexibility
                print("  Non-search source — skipping in marketing monitor.")
                source_stats.append(stat)
                continue

            print(f"  {len(raw_items)} articles found")
            stat["fetched"]  = len(raw_items)
            total_fetched   += len(raw_items)

            if not raw_items:
                source_stats.append(stat)
                continue

            enriched, inp, out = analyse_for_marketing(raw_items, source, api_key)
            total_in  += inp
            total_out += out
            print(f"  {len(enriched)} relevant after analysis")

            for item in enriched:
                result = save_marketing_update(item)
                if result:
                    total_saved += 1
                    stat["saved"] += 1
                    print(f"  ✅ {item['title'][:60]}")
                else:
                    total_skipped += 1
                    stat["skipped"] += 1
                    print(f"  ⤷ Duplicate: {item['title'][:60]}")

        except Exception as e:
            err_msg = str(e)
            print(f"  ❌ Error: {err_msg}")
            stat["error"] = err_msg
            total_errors += 1

        source_stats.append(stat)
        time.sleep(2)  # Pause between queries to respect rate limits

    # Log all token usage in one call
    if total_in + total_out > 0:
        log_token_usage(
            user_id=SYSTEM_USER_ID,
            feature="marketing_monitor_analyse",
            input_tokens=total_in,
            output_tokens=total_out,
        )

    token_usage = {
        "input":    total_in,
        "output":   total_out,
        "cost_usd": round(
            (total_in  / 1_000_000) * 2.00 +
            (total_out / 1_000_000) * 6.00, 6
        ),
    }

    print(f"\n{'='*60}")
    print("MARKETING MONITORING COMPLETE")
    print(f"Fetched: {total_fetched} | New: {total_saved} | "
          f"Duplicates: {total_skipped} | Errors: {total_errors}")
    print(f"Tokens: {total_in} in / {total_out} out — ${token_usage['cost_usd']:.4f}")

    result = {
        "fetched":  total_fetched,
        "saved":    total_saved,
        "skipped":  total_skipped,
        "errors":   total_errors,
        "run_at":   datetime.now(timezone.utc).isoformat(),
    }

    if run_id:
        complete_monitor_run(
            run_id,
            total_fetched=total_fetched,
            total_saved=total_saved,
            total_skipped=total_skipped,
            total_errors=total_errors,
            source_stats=source_stats,
            token_usage=token_usage,
            status="completed",
        )

    return result


if __name__ == "__main__":
    result = run_marketing_monitoring(triggered_by="cron")
    print(json.dumps(result, indent=2))
