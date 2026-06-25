"""
RECOSA Regulatory Monitor
Fetches RSS feeds and web pages from authoritative EU regulatory sources,
uses Mistral to summarise and categorise new items, and writes them to
Supabase as pending updates for admin review.

Run via GitHub Actions cron or manually from the admin panel.
"""

import os
import json
import time
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from database import save_regulatory_update, log_token_usage

# ── Sentinel UUID for system/monitoring processes ─────────────
# Used in usage_logs when there is no authenticated user.
# This UUID must exist in auth.users OR user_id must be nullable.
# Simplest fix: make user_id nullable in usage_logs (run in Supabase SQL editor):
#   ALTER TABLE public.usage_logs ALTER COLUMN user_id DROP NOT NULL;
# Then this sentinel signals "system process" in admin reporting.
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RECOSA-Monitor/1.0; +https://recosa.eu)"
}


# ── Monitored sources ─────────────────────────────────────────
# Sources with type="rss" are fetched via RSS feed.
# Sources with type="scrape" are fetched by parsing the HTML news page.
# EUR-Lex is excluded from automated monitoring (bot protection returns empty responses).
# Use manual Colab ingestion for EUR-Lex PDFs.

SOURCES = [
    # EDPB — European Data Protection Board (URL updated)
    {
        "name": "EDPB",
        "url": "https://edpb.europa.eu/feed/news_en",
        "type": "rss",
        "regulations": ["GDPR"],
        "countries": ["EU"],
    },
    # EU AI Office
    {
        "name": "EU AI Office",
        "url": "https://digital-strategy.ec.europa.eu/en/rss.xml",
        "type": "rss",
        "regulations": ["EU_AI_ACT"],
        "countries": ["EU"],
        "filter_keywords": ["AI Act", "artificial intelligence", "GPAI"],
    },
    # CERT-EU — Threat Intelligence (replaces ENISA RSS which is discontinued)
    {
        "name": "CERT-EU (Threat Intelligence)",
        "url": "https://cert.europa.eu/publications/threat-intelligence-rss",
        "type": "rss",
        "regulations": ["NIS2"],
        "countries": ["EU"],
    },
    # CERT-EU — Security Advisories
    {
        "name": "CERT-EU (Security Advisories)",
        "url": "https://cert.europa.eu/publications/security-advisories-rss",
        "type": "rss",
        "regulations": ["NIS2"],
        "countries": ["EU"],
    },
    # ENISA — news page scrape (RSS discontinued, scrape as safety net)
    {
        "name": "ENISA",
        "url": "https://www.enisa.europa.eu/news",
        "type": "scrape",
        "regulations": ["NIS2"],
        "countries": ["EU"],
    },
    # CNIL — French Data Protection Authority
    {
        "name": "CNIL",
        "url": "https://www.cnil.fr/fr/rss.xml",
        "type": "rss",
        "regulations": ["GDPR", "EPRIVACY"],
        "countries": ["FR"],
        "filter_keywords": ["RGPD", "données personnelles", "cookie", "cybersécurité"],
    },
    # CCB — Centre for Cybersecurity Belgium (URL updated)
    {
        "name": "CCB",
        "url": "https://ccb.belgium.be/news.xml",
        "type": "rss",
        "regulations": ["NIS2"],
        "countries": ["BE"],
    },
    # APD/GBA — Belgian Data Protection Authority (scrape, no RSS on new domain)
    {
        "name": "APD/GBA",
        "url": "https://www.dataprotectionauthority.be/professional/news",
        "type": "scrape",
        "regulations": ["GDPR"],
        "countries": ["BE"],
    },
]


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
        filter_kw = [k.lower() for k in source_config.get("filter_keywords", [])]

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
    Extracts headlines + links only — no full content.
    Mistral filters for relevance as normal.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        html = response.text

        results = []

        # Extract all anchor tags with href — look for news article links
        # Pattern: <a href="...">Title text</a>
        # We filter for links that look like articles (contain /news/ or /professional/)
        link_pattern = re.compile(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>\s*([^<]{20,200})\s*</a>',
            re.IGNORECASE | re.DOTALL
        )

        seen_urls = set()
        base_url = "/".join(url.split("/")[:3])  # e.g. https://www.enisa.europa.eu

        for match in link_pattern.finditer(html):
            href = match.group(1).strip()
            title = re.sub(r'\s+', ' ', match.group(2)).strip()

            # Skip navigation links, empty titles, very short titles
            if len(title) < 20:
                continue

            # Skip non-article links
            skip_patterns = [
                "javascript:", "mailto:", "#", "login", "logout",
                "search", "sitemap", "cookie", "privacy-policy",
                "terms", "contact", "about", "rss"
            ]
            if any(p in href.lower() for p in skip_patterns):
                continue

            # Normalise relative URLs
            if href.startswith("/"):
                href = base_url + href
            elif not href.startswith("http"):
                continue

            # Deduplicate
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Only keep links from the same domain
            if base_url not in href:
                continue

            results.append({
                "title": title,
                "url": href,
                "description": "",  # No description from scrape — Mistral works from title
                "published_raw": "",
            })

            if len(results) >= 15:  # Cap at 15 items per scrape source
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
) -> list[dict]:
    """
    Use Mistral to summarise and assess relevance of fetched items.
    Returns enriched items ready for database insertion.
    """
    if not items or not api_key:
        return []

    results = []

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

            # Log token usage with sentinel UUID (no authenticated user in cron context)
            try:
                log_token_usage(
                    user_id=SYSTEM_USER_ID,
                    feature="monitoring_summarise",
                    client_id=None,
                    input_tokens=_usage.get("prompt_tokens", 0),
                    output_tokens=_usage.get("completion_tokens", 0),
                )
            except Exception as log_err:
                print(f"  Could not log token usage: {log_err}")

            raw = _rdata["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                raw = match.group(0)

            analysis = json.loads(raw)

            if not analysis.get("relevant", False):
                continue

            regs = list(set(
                source_config.get("regulations", []) +
                analysis.get("regulations", [])
            ))

            results.append({
                "source": source_config["name"],
                "title": title,
                "summary": analysis.get("summary", description[:300]),
                "url": item["url"],
                "regulations": regs,
                "countries": source_config.get("countries", ["EU"]),
                "severity": analysis.get("severity", "info"),
                "action_required": analysis.get("action_required", False),
                "action_description": analysis.get("action_description", ""),
                "published_at": parse_published_date(item.get("published_raw", "")),
                "status": "pending",
            })

            time.sleep(0.5)

        except Exception as e:
            print(f"  Could not analyse item '{title[:50]}': {e}")
            continue

    return results


# ── Main monitoring run ───────────────────────────────────────

def run_monitoring() -> dict:
    """
    Main entry point. Fetches all sources, summarises, deduplicates,
    saves to Supabase. Returns summary stats.
    """
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        return {"error": "MISTRAL_API_KEY not set", "saved": 0, "skipped": 0}

    print(f"\nRECOSA Regulatory Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    total_fetched = 0
    total_saved = 0
    total_skipped = 0
    errors = []

    for source in SOURCES:
        print(f"\nFetching {source['name']}...")

        # Dispatch to RSS or scraper based on source type
        if source.get("type") == "scrape":
            raw_items = parse_scrape(source["url"], source)
        else:
            raw_items = parse_rss(source["url"], source)

        print(f"  {len(raw_items)} items fetched")
        total_fetched += len(raw_items)

        if not raw_items:
            continue

        enriched = summarise_and_categorise(raw_items, source, api_key)
        print(f"  {len(enriched)} relevant items after analysis")

        for item in enriched:
            result = save_regulatory_update(item)
            if result:
                total_saved += 1
                print(f"  ✅ Saved: {item['title'][:60]}")
            else:
                total_skipped += 1
                print(f"  ⤷ Duplicate skipped: {item['title'][:60]}")

    print(f"\n{'='*60}")
    print("MONITORING COMPLETE")
    print(f"Fetched: {total_fetched} | Relevant: {total_saved + total_skipped} | "
          f"New: {total_saved} | Duplicates: {total_skipped}")

    return {
        "fetched": total_fetched,
        "saved": total_saved,
        "skipped": total_skipped,
        "errors": errors,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    result = run_monitoring()
    print(json.dumps(result, indent=2))
