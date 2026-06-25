"""
RECOSA Marketing Monitor
Uses Mistral chat completions API with web_search_premium tool to find
recent EU compliance news, then saves relevant items to Supabase for
admin review and LinkedIn draft generation.

Uses the standard /v1/chat/completions endpoint (not the beta Conversations API)
with web_search_premium passed as a built-in tool — same pattern as the
Mistral docs examples.

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


# ── Mistral web search via chat completions ───────────────────

def search_news_with_mistral(query: str, api_key: str) -> list[dict]:
    """
    Use Mistral chat completions with web_search_premium tool to find
    recent news articles matching the query.
    Returns list of raw items with title, url, description, published_raw.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    system_prompt = (
        "You are a news research assistant for RECOSA, an EU regulatory compliance platform. "
        "Search the web to find REAL recent news articles. "
        "Always use the web search tool — never answer from memory. "
        "Return ONLY a valid JSON array, no prose, no markdown fences:\n"
        '[{"title":"...","url":"...","description":"1-2 sentences","published_date":"YYYY-MM-DD"}]'
    )

    user_prompt = (
        f"Search for the 8 most recent news articles from the last 48 hours about: {query}\n"
        f"Focus on EU, Belgium, and France context where relevant.\n"
        f"Return ONLY the JSON array."
    )

    payload = {
        "model":    "mistral-small-latest",
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "tools": [{"type": "web_search_premium"}],
        "max_tokens": 2000,
    }

    try:
        resp = requests.post(
            f"{MISTRAL_API_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )

        if not resp.ok:
            print(f"  API error {resp.status_code}: {resp.text[:300]}")
            return []

        data    = resp.json()
        content = data["choices"][0]["message"]["content"] or ""

        if not content.strip():
            # Model may have only returned tool calls without final content
            # Try to get the tool result from the message
            print(f"  Empty content for query '{query}' — checking tool calls")
            tool_calls = data["choices"][0]["message"].get("tool_calls", [])
            if tool_calls:
                print(f"  Tool was called but no final response — model needs follow-up")
            return []

        # Parse JSON array from response
        items = _parse_json_array(content)
        if items:
            return _normalise_items(items)

        # Fallback: parse markdown
        items = _parse_markdown_response(content)
        if items:
            print(f"  Parsed {len(items)} items from markdown response")
        return items

    except Exception as e:
        print(f"  Search error for '{query}': {e}")
        return []


def _parse_json_array(text: str) -> list:
    """Extract and parse a JSON array from text."""
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        match = re.search(r'\[[\s\S]*\]', clean)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return []


def _parse_markdown_response(text: str) -> list[dict]:
    """
    Parse markdown-formatted news response into structured items.
    Handles bold headers, numbered lists, and inline URLs.
    """
    items   = []
    sections = re.split(r'\n(?=###\s|\*\*\d+\.|\d+\.\s+\*\*)', text)

    for section in sections:
        if not section.strip() or len(section.strip()) < 30:
            continue

        # Extract title
        title_match = (
            re.search(r'###\s+\*?\*?(.+?)\*?\*?(?:\n|$)', section) or
            re.search(r'\*\*\d+\.\s+(.+?)\*\*', section) or
            re.search(r'^\d+\.\s+\*?\*?(.+?)\*?\*?(?:\n|$)', section, re.MULTILINE)
        )
        if not title_match:
            continue

        title = re.sub(r'\*+', '', title_match.group(1)).strip()
        if len(title) < 10:
            continue

        # Extract URL
        url_match = re.search(r'\[([^\]]+)\]\((https?://[^\)]+)\)', section)
        url = url_match.group(2).strip() if url_match else ""

        # Extract description — clean markdown, take first 300 chars
        clean = re.sub(r'###.+\n', '', section)
        clean = re.sub(r'\*\*[^*]+\*\*[:\s]*', '', clean)
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)
        clean = re.sub(r'\*+', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        desc  = clean[:300]

        # Extract date
        date_match = re.search(
            r'(January|February|March|April|May|June|July|August|'
            r'September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
            section
        )
        pub_date = ""
        if date_match:
            month_map = {
                "January":"01","February":"02","March":"03","April":"04",
                "May":"05","June":"06","July":"07","August":"08",
                "September":"09","October":"10","November":"11","December":"12"
            }
            pub_date = (
                f"{date_match.group(3)}-"
                f"{month_map[date_match.group(1)]}-"
                f"{date_match.group(2).zfill(2)}"
            )

        if title and desc:
            items.append({
                "title":         title,
                "url":           url,
                "description":   desc,
                "published_raw": pub_date,
            })

    return items


def _normalise_items(raw: list) -> list[dict]:
    """Normalise JSON-parsed items to standard format."""
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
            "title":         title,
            "url":           url,
            "description":   desc[:500],
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
    Filter and summarise items for RECOSA marketing relevance.
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

        system_prompt = (
            "You are a content strategist for RECOSA, an EU regulatory compliance SaaS "
            "helping SMEs in Belgium and France comply with GDPR, NIS2, and the EU AI Act.\n\n"
            "Analyse this news item and return ONLY valid JSON:\n"
            "{\n"
            '  "relevant": true/false,\n'
            '  "relevance_reason": "one sentence",\n'
            '  "summary": "2-3 sentence summary for EU compliance professionals",\n'
            '  "severity": "info|important|urgent",\n'
            '  "content_angle": "enforcement|policy|guidance|market|tech|other"\n'
            "}\n\n"
            "relevant: true if useful for understanding the EU compliance landscape, "
            "competitor intelligence, or LinkedIn content inspiration for SME compliance officers.\n"
            "relevant: false for generic tech, US-only news, sports, or entertainment."
        )

        user_prompt = (
            f"SOURCE: {source_config['name']} ({source_config.get('category', '')})\n"
            f"QUERY: {source_config.get('query', '')}\n"
            f"TITLE: {title}\n"
            f"CONTENT: {desc}\n\n"
            f"Is this relevant for RECOSA?"
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
    Mistral chat completions with web_search_premium, filters with
    Mistral, saves results to marketing_updates.
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
            if fetch_type != "search":
                print(f"  Non-search source skipped in marketing monitor.")
                source_stats.append(stat)
                continue

            query = source.get("query", "")
            if not query:
                print("  No query defined — skipping.")
                source_stats.append(stat)
                continue

            raw_items = search_news_with_mistral(query, api_key)
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
        time.sleep(2)

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
