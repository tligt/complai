"""
RECOSA Marketing Monitor
Searches the web for recent news about EU compliance topics using NewsAPI,
filters for RECOSA-relevant content with Mistral, and saves to Supabase
for admin review and LinkedIn draft generation.

Sources are loaded dynamically from monitoring_sources table
where monitor_type = 'marketing'.

fetch_type options:
  'search' — NewsAPI keyword search (primary, broad coverage)
  'rss'    — RSS feed (specific sites, if needed)
  'scrape' — HTML scrape (fallback for sites without RSS)

Run via GitHub Actions cron or manually from the admin BO.
"""

import os
import json
import time
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from database import (
    save_marketing_update,
    log_token_usage,
    load_monitoring_sources,
    start_monitor_run,
    complete_monitor_run,
)

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RECOSA-Monitor/1.0; +https://recosa.eu)"
}


# ── NewsAPI search ────────────────────────────────────────────

def fetch_news_search(query: str, api_key: str, days_back: int = 1) -> list[dict]:
    """
    Search NewsAPI for recent articles matching the query.
    Returns last `days_back` days of results (default: 24h).
    """
    if not api_key:
        print("  NEWS_API_KEY not set — skipping search fetch.")
        return []

    # NewsAPI free tier only supports `from` up to 1 month back
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q":          query,
                "from":       from_date,
                "sortBy":     "publishedAt",
                "language":   "en",
                "pageSize":   20,           # Max 20 articles per query
                "apiKey":     api_key,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            print(f"  NewsAPI error: {data.get('message', 'Unknown error')}")
            return []

        articles = data.get("articles", [])
        results  = []

        for article in articles:
            title       = (article.get("title") or "").strip()
            url         = (article.get("url") or "").strip()
            description = (article.get("description") or "").strip()
            published   = (article.get("publishedAt") or "").strip()
            source_name = article.get("source", {}).get("name", "")

            if not title or not url:
                continue

            # Skip removed articles (NewsAPI sometimes returns placeholders)
            if title == "[Removed]" or url == "https://removed.com":
                continue

            results.append({
                "title":        f"{title} ({source_name})" if source_name else title,
                "url":          url,
                "description":  description[:500],
                "published_raw": published,
                "source_name":  source_name,
            })

        return results

    except Exception as e:
        print(f"  NewsAPI error for query '{query}': {e}")
        return []


# ── RSS parsing ───────────────────────────────────────────────

def parse_rss(url: str, source_config: dict) -> list[dict]:
    """Fetch and parse an RSS feed."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        results  = []
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
                "title":        title,
                "url":          link,
                "description":  description[:500],
                "published_raw": pub_date,
            })

        return results

    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return []


# ── HTML scraping ─────────────────────────────────────────────

def parse_scrape(url: str, source_config: dict) -> list[dict]:
    """Lightweight HTML scrape — headlines + links only."""
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
        base_url  = "/".join(url.split("/")[:3])

        for match in link_pattern.finditer(html):
            href  = match.group(1).strip()
            title = re.sub(r'\s+', ' ', match.group(2)).strip()

            if len(title) < 20:
                continue
            skip = ["javascript:", "mailto:", "#", "login", "logout",
                    "search", "sitemap", "cookie", "privacy-policy",
                    "terms", "contact", "about", "rss", "subscribe"]
            if any(p in href.lower() for p in skip):
                continue
            if href.startswith("/"):
                href = base_url + href
            elif not href.startswith("http"):
                continue
            if href in seen_urls or base_url not in href:
                continue
            seen_urls.add(href)

            results.append({
                "title":        title,
                "url":          href,
                "description":  "",
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


# ── Mistral relevance filtering ───────────────────────────────

def analyse_for_marketing(
    items: list[dict],
    source_config: dict,
    api_key: str,
) -> tuple[list[dict], int, int]:
    """
    Filter items for RECOSA marketing relevance using Mistral.
    Returns (relevant_items, input_tokens_total, output_tokens_total).
    """
    if not items or not api_key:
        return [], 0, 0

    results     = []
    total_input = 0
    total_output= 0

    for item in items:
        title       = item["title"]
        description = item.get("description", "")

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

relevant: false for generic tech news, unrelated politics, sports, entertainment,
US-only news with no EU angle, or paywalled content with no useful description."""

        user_prompt = f"""SOURCE: {source_config['name']} ({source_config.get('category', '')})
SEARCH QUERY: {source_config.get('query', '')}
TITLE: {title}
CONTENT: {description}

Is this relevant for RECOSA's marketing and content strategy?"""

        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
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
            response.raise_for_status()
            _rdata  = response.json()
            _usage  = _rdata.get("usage", {})
            total_input  += _usage.get("prompt_tokens", 0)
            total_output += _usage.get("completion_tokens", 0)

            raw = _rdata["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                raw = match.group(0)

            analysis = json.loads(raw)

            if not analysis.get("relevant", False):
                continue

            results.append({
                "source":           source_config["name"],
                "category":         source_config.get("category", ""),
                "title":            item["title"],  # Original title without source suffix
                "summary":          analysis.get("summary", description[:300]),
                "url":              item["url"],
                "severity":         analysis.get("severity", "info"),
                "relevance_reason": analysis.get("relevance_reason", ""),
                "published_at":     parse_published_date(item.get("published_raw", "")),
                "status":           "pending",
            })

            time.sleep(0.3)

        except Exception as e:
            print(f"  Could not analyse item '{title[:50]}': {e}")
            continue

    return results, total_input, total_output


# ── Main marketing monitoring run ─────────────────────────────

def run_marketing_monitoring(triggered_by: str = "cron") -> dict:
    """
    Main entry point. Loads marketing sources from DB, fetches via
    NewsAPI search / RSS / scrape, filters with Mistral, saves results.
    """
    mistral_key  = os.environ.get("MISTRAL_API_KEY", "")
    news_api_key = os.environ.get("NEWS_API_KEY", "")

    if not mistral_key:
        return {"error": "MISTRAL_API_KEY not set", "saved": 0, "skipped": 0}

    print(f"\nRECOSA Marketing Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    if not news_api_key:
        print("⚠️  NEWS_API_KEY not set — search-type sources will be skipped.")

    run_id  = start_monitor_run("marketing", triggered_by=triggered_by)
    sources = load_monitoring_sources(monitor_type="marketing")

    if not sources:
        print("  No active marketing sources found in DB.")
        if run_id:
            complete_monitor_run(run_id, 0, 0, 0, 0, [], {},
                                 status="completed", error_message="No active sources")
        return {"fetched": 0, "saved": 0, "skipped": 0, "errors": 0}

    print(f"Loaded {len(sources)} active marketing sources from DB.")

    total_fetched = total_saved = total_skipped = total_errors = 0
    total_in = total_out = 0
    source_stats = []

    for source in sources:
        fetch_type = source.get("fetch_type", "rss")
        print(f"\nFetching {source['name']} [{source.get('category','')}] via {fetch_type.upper()}...")

        stat = {
            "name":    source["name"],
            "fetched": 0,
            "saved":   0,
            "skipped": 0,
            "error":   None,
        }

        try:
            # Dispatch by fetch type
            if fetch_type == "search":
                query = source.get("query", "")
                if not query:
                    print("  No query defined — skipping.")
                    source_stats.append(stat)
                    continue
                if not news_api_key:
                    print("  NEWS_API_KEY missing — skipping search source.")
                    source_stats.append(stat)
                    continue
                raw_items = fetch_news_search(query, news_api_key)
            elif fetch_type == "scrape":
                raw_items = parse_scrape(source["url"], source)
            else:
                raw_items = parse_rss(source["url"], source)

            print(f"  {len(raw_items)} items fetched")
            stat["fetched"]  = len(raw_items)
            total_fetched   += len(raw_items)

            if not raw_items:
                source_stats.append(stat)
                continue

            enriched, inp, out = analyse_for_marketing(raw_items, source, mistral_key)
            total_in  += inp
            total_out += out
            print(f"  {len(enriched)} relevant after Mistral analysis")

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

    # Log token usage
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
