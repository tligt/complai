"""
RECOSA Marketing Monitor
Uses a persistent Mistral Agent with Premium Search to find recent EU
compliance news, then saves relevant items to Supabase for admin review
and LinkedIn draft generation.

A single reusable agent (RECOSA-NewsSearch) is pre-created in Mistral Studio
with web_search_premium enabled. Its ID is stored as MISTRAL_AGENT_ID secret.

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

# Pre-created agent in Mistral Studio with web_search_premium enabled.
# Override via MISTRAL_AGENT_ID environment variable.
DEFAULT_AGENT_ID = "ag_019efe92f08e71a78d70f0f8b9230d29"


# ── Mistral agent search ──────────────────────────────────────

def search_news_with_agent(query: str, api_key: str, agent_id: str) -> list[dict]:
    """
    Use the persistent RECOSA-NewsSearch Mistral agent with Premium Search
    to find recent news articles matching the query.

    The agent returns rich markdown — we extract structured items from it.
    Returns list of raw items with title, url, description, published_raw.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    prompt = (
        f"Find the 8 most recent news articles published in the last 48 hours about: {query}\n\n"
        f"Focus on EU, Belgium, and France context where relevant.\n\n"
        f"For each article, provide:\n"
        f"- Title\n"
        f"- URL (exact link)\n"
        f"- 1-2 sentence description\n"
        f"- Publication date (YYYY-MM-DD)\n\n"
        f"Return ONLY a JSON array, no other text:\n"
        f'[{{"title":"...","url":"...","description":"...","published_date":"YYYY-MM-DD"}}]'
    )

    try:
        resp = requests.post(
            f"{MISTRAL_API_BASE}/conversations",
            headers=headers,
            json={
                "agent_id": agent_id,
                "inputs":   prompt,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text from conversation outputs
        raw_text = _extract_text_from_conversation(data)

        if not raw_text:
            print(f"  No text response for query '{query}'")
            return []

        # Try JSON array first
        items = _parse_json_array(raw_text)
        if items:
            return _normalise_items(items)

        # Fallback: parse markdown response into structured items
        items = _parse_markdown_response(raw_text)
        return items

    except Exception as e:
        print(f"  Agent search error for '{query}': {e}")
        return []


def _extract_text_from_conversation(data: dict) -> str:
    """Extract plain text from Mistral Conversations API response."""
    raw_text = ""

    # Try outputs array (Agents API format)
    outputs = data.get("outputs", [])
    for output in outputs:
        if output.get("type") == "message.output":
            chunks = output.get("content", [])
            for chunk in chunks:
                if chunk.get("type") == "text":
                    raw_text += chunk.get("text", "")

    # Fallback: direct message content (chat completions format)
    if not raw_text:
        choices = data.get("choices", [])
        for choice in choices:
            msg = choice.get("message", {})
            raw_text += msg.get("content", "")

    # Fallback: check for 'message' key directly
    if not raw_text:
        msg = data.get("message", {})
        if isinstance(msg, dict):
            raw_text = msg.get("content", "")

    return raw_text.strip()


def _parse_json_array(text: str) -> list:
    """Try to extract and parse a JSON array from text."""
    try:
        text = re.sub(r"```json|```", "", text).strip()
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return []


def _parse_markdown_response(text: str) -> list[dict]:
    """
    Parse a markdown-formatted news response into structured items.
    Handles the rich markdown format that Mistral returns when not
    strictly following JSON instructions.
    """
    items = []

    # Split by numbered sections or ### headers
    sections = re.split(r'\n(?=###|\*\*\d+\.)', text)

    for section in sections:
        if not section.strip():
            continue

        # Extract title — look for bold text or ### heading
        title_match = (
            re.search(r'###\s+\*?\*?(.+?)\*?\*?\n', section) or
            re.search(r'\*\*(\d+\.\s+.+?)\*\*', section) or
            re.search(r'#+\s+(.+)', section)
        )
        title = title_match.group(1).strip() if title_match else ""

        # Clean up title
        title = re.sub(r'^\d+\.\s*', '', title).strip()
        title = re.sub(r'\*', '', title).strip()

        if not title or len(title) < 10:
            continue

        # Extract URL
        url_match = re.search(r'\[([^\]]+)\]\((https?://[^\)]+)\)', section)
        url = url_match.group(2).strip() if url_match else ""

        # Extract description — first substantive sentence after title
        # Remove markdown formatting
        clean = re.sub(r'#+\s+.+\n', '', section)
        clean = re.sub(r'\*\*[^*]+\*\*:\s*', '', clean)
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)
        clean = re.sub(r'\*', '', clean)
        clean = re.sub(r'\n+', ' ', clean).strip()

        # Take first 300 chars as description
        desc = clean[:300].strip()

        # Extract date — look for month year patterns
        date_match = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            section
        )
        pub_date = ""
        if date_match:
            month_map = {
                "January":"01","February":"02","March":"03","April":"04",
                "May":"05","June":"06","July":"07","August":"08",
                "September":"09","October":"10","November":"11","December":"12"
            }
            pub_date = f"{date_match.group(2)}-{month_map[date_match.group(1)]}-01"

        if title and desc:
            items.append({
                "title":        title,
                "url":          url,
                "description":  desc,
                "published_raw": pub_date,
            })

    return items


def _normalise_items(raw: list) -> list[dict]:
    """Normalise JSON-parsed items to our standard format."""
    results = []
    for a in raw:
        title = (a.get("title") or "").strip()
        url   = (a.get("url") or "").strip()
        desc  = (a.get("description") or "").strip()
        pub   = (a.get("published_date") or a.get("published_raw") or "").strip()

        if not title or len(title) < 10:
            continue
        if url in ("", "N/A", "unknown", "https://example.com"):
            url = ""

        results.append({
            "title":        title,
            "url":          url,
            "description":  desc[:500],
            "published_raw": pub,
        })
    return results


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
                "url":              item.get("url", ""),
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
    persistent Mistral agent with Premium Search, filters with Mistral,
    saves results to marketing_updates.
    """
    api_key  = os.environ.get("MISTRAL_API_KEY", "")
    agent_id = os.environ.get("MISTRAL_AGENT_ID", DEFAULT_AGENT_ID)

    if not api_key:
        return {"error": "MISTRAL_API_KEY not set", "saved": 0, "skipped": 0}

    print(f"\nRECOSA Marketing Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Using agent: {agent_id}")
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

    print(f"Loaded {len(sources)} active marketing sources.")

    total_fetched = total_saved = total_skipped = total_errors = 0
    total_in = total_out = 0
    source_stats = []

    for source in sources:
        fetch_type = source.get("fetch_type", "search")
        print(f"\n[{source.get('category','')}] {source['name']}...")

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
                raw_items = search_news_with_agent(query, api_key, agent_id)
            else:
                print(f"  fetch_type={fetch_type} not handled in marketing monitor — skipping.")
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
        time.sleep(2)  # Pause between queries

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
