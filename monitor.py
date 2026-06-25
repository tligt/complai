"""
RECOSA Regulatory Monitor
Fetches RSS feeds and web pages from authoritative EU regulatory sources,
uses Mistral to summarise and categorise new items, and writes them to
Supabase as pending updates for admin review.

Sources are loaded dynamically from the monitoring_sources table —
no hardcoded URLs. Add/remove/toggle sources from the admin BO.

Run via GitHub Actions cron or manually from the admin BO.
"""

import os
import json
import time
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from database import (
    save_regulatory_update,
    log_token_usage,
    load_monitoring_sources,
    start_monitor_run,
    complete_monitor_run,
)

# Sentinel UUID for system/monitoring processes (no authenticated user)
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RECOSA-Monitor/1.0; +https://recosa.eu)"
}


# ── RSS parsing ───────────────────────────────────────────────

def parse_rss(url: str, source_config: dict) -> list[dict]:
    """Fetch and parse an RSS feed. Returns list of raw items."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        results = []
        filter_kw = [k.lower() for k in (source_config.get("filter_keywords") or [])]

        for item in items[:20]:
            title = (
                _get_text(item, "title") or
                _get_text(item, "atom:title", ns) or ""
            ).strip()

            link = (
                _get_text(item, "link") or
                _get_attr(item, "atom:link", "href", ns) or ""
            ).strip()

            description = (
                _get_text(item, "description") or
                _get_text(item, "summary") or
                _get_text(item, "atom:summary", ns) or ""
            ).strip()

            pub_date = (
                _get_text(item, "pubDate") or
                _get_text(item, "published") or
                _get_text(item, "atom:published", ns) or ""
            ).strip()

            if not title or not link:
                continue

            if filter_kw:
                combined = (title + " " + description).lower()
                if not any(kw in combined for kw in filter_kw):
                    continue

            results.append({
                "title": title,
                "url": link,
                "description": description[:500],
                "published_raw": pub_date,
            })

        return results

    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return []


# ── HTML scraping ─────────────────────────────────────────────

def parse_scrape(url: str, source_config: dict) -> list[dict]:
    """
    Lightweight scrape of a news page.
    Extracts headlines + links only — Mistral filters for relevance.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        html = response.text

        results = []
        link_pattern = re.compile(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>\s*([^<]{20,200})\s*</a>',
            re.IGNORECASE | re.DOTALL
        )

        seen_urls = set()
        base_url = "/".join(url.split("/")[:3])

        for match in link_pattern.finditer(html):
            href = match.group(1).strip()
            title = re.sub(r'\s+', ' ', match.group(2)).strip()

            if len(title) < 20:
                continue

            skip_patterns = [
                "javascript:", "mailto:", "#", "login", "logout",
                "search", "sitemap", "cookie", "privacy-policy",
                "terms", "contact", "about", "rss"
            ]
            if any(p in href.lower() for p in skip_patterns):
                continue

            if href.startswith("/"):
                href = base_url + href
            elif not href.startswith("http"):
                continue

            if href in seen_urls:
                continue
            seen_urls.add(href)

            if base_url not in href:
                continue

            results.append({
                "title": title,
                "url": href,
                "description": "",
                "published_raw": "",
            })

            if len(results) >= 15:
                break

        return results

    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return []


# ── XML helpers ───────────────────────────────────────────────

def _get_text(element, tag, ns=None) -> str:
    try:
        child = element.find(tag, ns) if ns else element.find(tag)
        return (child.text or "").strip() if child is not None else ""
    except Exception:
        return ""


def _get_attr(element, tag, attr, ns=None) -> str:
    try:
        child = element.find(tag, ns) if ns else element.find(tag)
        return child.get(attr, "") if child is not None else ""
    except Exception:
        return ""


def parse_published_date(date_str: str) -> str | None:
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


# ── Mistral summarisation ─────────────────────────────────────

def summarise_and_categorise(
    items: list[dict],
    source_config: dict,
    api_key: str,
) -> tuple[list[dict], int, int]:
    """
    Use Mistral to summarise and assess relevance of fetched items.
    Returns (enriched_items, input_tokens_total, output_tokens_total).
    """
    if not items or not api_key:
        return [], 0, 0

    results = []
    total_input = 0
    total_output = 0

    for item in items:
        title = item["title"]
        description = item.get("description", "")

        system_prompt = """You are an EU regulatory compliance expert.
Analyse this regulatory news item and return ONLY valid JSON:
{
  "relevant": true/false,
  "summary": "2-3 sentence plain English summary of what this means for EU SMEs",
  "severity": "info|important|urgent",
  "regulations": ["GDPR"|"NIS2"|"EU_AI_ACT"|"EPRIVACY"|"EAA"|"CONSUMER_RIGHTS"],
  "action_required": true/false,
  "action_description": "what SMEs need to do (empty if no action required)"
}
relevant: false if this is general news unrelated to compliance obligations.
severity: urgent=immediate action needed, important=awareness required, info=general update."""

        user_prompt = f"""SOURCE: {source_config['name']}
TITLE: {title}
CONTENT: {description}

Is this relevant to EU SME compliance? Summarise and categorise."""

        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistral-large-latest",
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 400,
                },
                timeout=30,
            )
            response.raise_for_status()
            _rdata = response.json()
            _usage = _rdata.get("usage", {})
            _input  = _usage.get("prompt_tokens", 0)
            _output = _usage.get("completion_tokens", 0)
            total_input  += _input
            total_output += _output

            raw = _rdata["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                raw = match.group(0)

            analysis = json.loads(raw)

            if not analysis.get("relevant", False):
                continue

            regs = list(set(
                (source_config.get("regulations") or []) +
                analysis.get("regulations", [])
            ))

            results.append({
                "source":             source_config["name"],
                "title":              title,
                "summary":            analysis.get("summary", description[:300]),
                "url":                item["url"],
                "regulations":        regs,
                "countries":          source_config.get("countries") or ["EU"],
                "severity":           analysis.get("severity", "info"),
                "action_required":    analysis.get("action_required", False),
                "action_description": analysis.get("action_description", ""),
                "published_at":       parse_published_date(item.get("published_raw", "")),
                "status":             "pending",
            })

            time.sleep(0.5)

        except Exception as e:
            print(f"  Could not analyse item '{title[:50]}': {e}")
            continue

    return results, total_input, total_output


# ── Main monitoring run ───────────────────────────────────────

def run_monitoring(triggered_by: str = "cron") -> dict:
    """
    Main entry point. Loads sources from DB, fetches, summarises,
    deduplicates, saves to Supabase. Logs run to monitor_runs.
    Returns summary stats.
    """
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        return {"error": "MISTRAL_API_KEY not set", "saved": 0, "skipped": 0}

    print(f"\nRECOSA Regulatory Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Start run log
    run_id = start_monitor_run("regulatory", triggered_by=triggered_by)

    # Load sources dynamically from DB
    sources = load_monitoring_sources(monitor_type="regulatory")
    if not sources:
        print("  No active regulatory sources found in DB.")
        if run_id:
            complete_monitor_run(
                run_id, 0, 0, 0, 0, [], {},
                status="completed",
                error_message="No active sources"
            )
        return {"fetched": 0, "saved": 0, "skipped": 0, "errors": []}

    print(f"Loaded {len(sources)} active regulatory sources from DB.")

    total_fetched  = 0
    total_saved    = 0
    total_skipped  = 0
    total_errors   = 0
    total_input_tokens  = 0
    total_output_tokens = 0
    source_stats   = []

    for source in sources:
        print(f"\nFetching {source['name']}...")
        source_stat = {
            "name":    source["name"],
            "fetched": 0,
            "saved":   0,
            "skipped": 0,
            "error":   None,
        }

        try:
            # Dispatch to RSS or scraper
            if source.get("fetch_type") == "scrape":
                raw_items = parse_scrape(source["url"], source)
            else:
                raw_items = parse_rss(source["url"], source)

            print(f"  {len(raw_items)} items fetched")
            source_stat["fetched"] = len(raw_items)
            total_fetched += len(raw_items)

            if not raw_items:
                source_stats.append(source_stat)
                continue

            enriched, inp, out = summarise_and_categorise(raw_items, source, api_key)
            total_input_tokens  += inp
            total_output_tokens += out
            print(f"  {len(enriched)} relevant items after analysis")

            for item in enriched:
                result = save_regulatory_update(item)
                if result:
                    total_saved += 1
                    source_stat["saved"] += 1
                    print(f"  ✅ Saved: {item['title'][:60]}")
                else:
                    total_skipped += 1
                    source_stat["skipped"] += 1
                    print(f"  ⤷ Duplicate skipped: {item['title'][:60]}")

        except Exception as e:
            err_msg = str(e)
            print(f"  ❌ Error processing {source['name']}: {err_msg}")
            source_stat["error"] = err_msg
            total_errors += 1

        source_stats.append(source_stat)

    # Log token usage with sentinel UUID
    if total_input_tokens + total_output_tokens > 0:
        log_token_usage(
            user_id=SYSTEM_USER_ID,
            feature="monitoring_summarise",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
        )

    token_usage = {
        "input":    total_input_tokens,
        "output":   total_output_tokens,
        "cost_usd": round(
            (total_input_tokens / 1_000_000) * 2.00 +
            (total_output_tokens / 1_000_000) * 6.00,
            6
        ),
    }

    print(f"\n{'='*60}")
    print("MONITORING COMPLETE")
    print(f"Fetched: {total_fetched} | Relevant: {total_saved + total_skipped} | "
          f"New: {total_saved} | Duplicates: {total_skipped} | Errors: {total_errors}")
    print(f"Tokens: {total_input_tokens} in / {total_output_tokens} out — "
          f"${token_usage['cost_usd']:.4f}")

    result = {
        "fetched":  total_fetched,
        "saved":    total_saved,
        "skipped":  total_skipped,
        "errors":   total_errors,
        "run_at":   datetime.now(timezone.utc).isoformat(),
    }

    # Complete run log
    if run_id:
        complete_monitor_run(
            run_id,
            total_fetched=total_fetched,
            total_saved=total_saved,
            total_skipped=total_skipped,
            total_errors=total_errors,
            source_stats=source_stats,
            token_usage=token_usage,
            status="completed" if total_errors == 0 else "completed",
        )

    return result


if __name__ == "__main__":
    result = run_monitoring(triggered_by="cron")
    print(json.dumps(result, indent=2))
