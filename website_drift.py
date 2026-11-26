"""
website_drift.py — the website-drift crawl (S67 follow-up, D-218).

Is the Privacy Policy / Cookie Policy on the company's website the version in
force in RECOSA? "Your website is showing v2; you adopted v3 in September" is a
real finding: a policy that is adopted but not published informs nobody
(GDPR Art. 12). Scoped in 3b under the S67 heartbeat; left out of D-188 as the
largest single check.

TWO HALVES
- Pure (no Supabase, no network): text normalising, shingles, `compare()` and
  `discover()`. Tested in test_website_drift.py.
- I/O: `check_client()` downloads the stored .docx of each version and fetches
  the pages. Called by monitor_heartbeat.py only — never on a page open, the
  crawl takes seconds. Its result is stored in clients.website_drift, and
  heartbeat.website_drift() turns THAT into findings, so the action plan and
  the nightly job read the same thing and cannot disagree (the reconcile on a
  page open would otherwise close what the job opened).

WHERE THE POLICY IS
The address the client gave (client_documents.published_url, asked when a
version is put in force), else links on the homepage whose address or text
names the policy, else the usual paths. Pages identical to the homepage are
dropped: many sites answer every path with the same catch-all page (creagent.be
does), which would otherwise "find" a policy on /privacy that is not there.

HOW IT COMPARES
Word 5-grams (accents and punctuation dropped), and CONTAINMENT: the share of a
version's 5-grams found on the page. Containment, not similarity, because the
page also carries navigation and the site's own text. Measured on the stored
creagent versions (26 Nov): distinct versions 0.11–0.34, identical ones 1.00 —
MATCH = 0.6 sits well clear of both. Below FOUND = 0.15 the best page is
just whichever unrelated page scored highest, so it is "not found", not a page
named as differing.
Telling v2 from v3 when they differ by one clause: both score high, so the
deciding evidence is the 5-grams that ONLY one of them has. The page shows the
older version when it carries clearly more of the older one's own text than of
the newer one's.

WHAT IT DOES NOT DO
- Run JavaScript. A site built in JavaScript returns an empty page to a plain
  fetch; that is reported as "could not be read", never as "not found" or
  "differs" (by request, 26 Nov — no headless browser on the server).
- Act. It reads public pages and records what it saw.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urljoin, urlparse

DOC_TYPES = ("privacy_policy", "cookie_policy")

N = 5                  # words per shingle
MATCH = 0.6            # containment at or above which a version is on the page
FOUND = 0.15           # below this no page carries the policy at all: an unrelated
                       # page scores ~0 (APD and Mozilla privacy pages, 26 Nov)
OLDER_MARGIN = 0.2     # own-text share by which the older version must lead
MIN_TEXT = 200         # characters below which a page "has no readable text"
KEEP_VERSIONS = 6      # newest versions compared per language

# Words in a link's address or text that name the policy.
_KEYWORDS = {
    "privacy_policy": r"privacy|privacit|confidential|vie[-_ ]priv|datenschutz|gdpr|rgpd|avg\b|persoonsgegevens",
    "cookie_policy": r"cookie",
}
_PATHS = {
    "privacy_policy": ["/privacy", "/privacy-policy", "/privacybeleid", "/privacyverklaring",
                       "/politique-de-confidentialite", "/politique-confidentialite",
                       "/confidentialite", "/vie-privee", "/datenschutz", "/gdpr", "/rgpd"],
    "cookie_policy": ["/cookies", "/cookie-policy", "/cookiebeleid", "/cookie-beleid",
                      "/politique-cookies", "/politique-de-cookies"],
}

# States stored per document type. Only the last four produce a finding.
MATCHES, OLDER, DIFFERS, NOT_FOUND, UNREADABLE = (
    "matches", "older", "differs", "not_found", "unreadable")


# ── Pure ──────────────────────────────────────────────────────────────────

def words(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", t)


def shingles(text: str, n: int = N) -> set[str]:
    w = words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def containment(part: set[str], page: set[str]) -> float:
    """Share of `part` found in `page`; 0 when `part` is empty."""
    return len(part & page) / len(part) if part else 0.0


def readable(text: str) -> bool:
    return len((text or "").strip()) >= MIN_TEXT


def discover(doc_type: str, homepage_html: str, base_url: str) -> list[str]:
    """Candidate addresses for one policy: homepage links first, then the usual paths.

    A link counts when its address or its visible text names the policy, so
    /legal/notice-3 titled "Privacy" is found. Same site only.
    """
    from bs4 import BeautifulSoup  # noqa: PLC0415
    pat = re.compile(_KEYWORDS[doc_type], re.I)
    host = urlparse(base_url).netloc.lower().removeprefix("www.")
    out: list[str] = []
    if homepage_html:
        for a in BeautifulSoup(homepage_html, "html.parser").find_all("a", href=True):
            url = urljoin(base_url, a["href"]).split("#")[0]
            if urlparse(url).netloc.lower().removeprefix("www.") != host:
                continue
            if pat.search(url) or pat.search(a.get_text(" ", strip=True)):
                out.append(url)
    p = urlparse(base_url)
    out += [f"{p.scheme}://{p.netloc}{path}" for path in _PATHS[doc_type]]
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def compare(pages: Mapping[str, str], versions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Which version, if any, the pages show.

    pages: {url: text}, already stripped of pages with no readable text.
    versions: rows with version, status, language, effective_from and `text`
    (the stored document's text), any language, in force and superseded.

    Returns {state, url, language, version_shown, in_force_version,
    in_force_since, score}. Called only with at least one in-force version.
    """
    vs = [dict(v, sh=shingles(v.get("text") or "")) for v in versions]
    vs = [v for v in vs if v["sh"]]
    live = [v for v in vs if v.get("status") == "in_force"]
    page_sh = {u: shingles(t) for u, t in pages.items()}
    head = max(live, key=lambda v: v.get("version") or 0) if live else {}
    base = {"in_force_version": head.get("version"), "language": head.get("language"),
            "in_force_since": head.get("effective_from")}
    if not page_sh or not live:
        return {**base, "state": NOT_FOUND, "url": None, "version_shown": None, "score": 0.0}

    # The best (page, version) pair over everything stored.
    scored = [(containment(v["sh"], p), u, v) for u, p in page_sh.items() for v in vs]
    best_score, best_url, best = max(scored, key=lambda s: (s[0], s[2].get("status") == "in_force"))
    # The in-force version of the best version's language, on the same page.
    cur = next((v for v in live if v.get("language") == best.get("language")), None)
    if cur is None:
        cur = max(live, key=lambda v: containment(v["sh"], page_sh[best_url]))
    cur_score = containment(cur["sh"], page_sh[best_url])
    out = {"url": best_url, "language": cur.get("language"),
           "in_force_version": cur.get("version"), "in_force_since": cur.get("effective_from")}

    if best_score < FOUND:
        return {**base, "state": NOT_FOUND, "url": None, "version_shown": None,
                "score": round(best_score, 2)}
    if best_score < MATCH:
        return {**out, "state": DIFFERS, "version_shown": None, "score": round(best_score, 2)}
    if best is cur or best["sh"] == cur["sh"]:
        return {**out, "state": MATCHES, "version_shown": cur.get("version"), "score": round(cur_score, 2)}

    # A superseded version scores highest. It is what the site shows only if
    # the page carries clearly more of its OWN text than of the newer one's.
    page = page_sh[best_url]
    own_old = containment(best["sh"] - cur["sh"], page)
    own_new = containment(cur["sh"] - best["sh"], page)
    if own_old >= own_new + OLDER_MARGIN:
        return {**out, "state": OLDER, "version_shown": best.get("version"), "score": round(best_score, 2)}
    if cur_score >= MATCH:
        return {**out, "state": MATCHES, "version_shown": cur.get("version"), "score": round(cur_score, 2)}
    return {**out, "state": DIFFERS, "version_shown": None, "score": round(cur_score, 2)}


# ── I/O ───────────────────────────────────────────────────────────────────

def docx_text(data: bytes) -> str:
    import docx  # noqa: PLC0415
    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts += [c.text for c in row.cells]
    return "\n".join(parts)


def _versions(sb, client_id: str, doc_type: str) -> list[dict]:
    """In-force and the newest superseded versions, with their text."""
    rows = (sb.table("client_documents")
            .select("id, language, version, status, effective_from, file_path, published_url")
            .eq("client_id", client_id).eq("document_type", doc_type)
            .in_("status", ["in_force", "superseded"]).not_.is_("version", "null")
            .execute().data or [])
    keep: list[dict] = []
    for lang in {r.get("language") for r in rows}:
        mine = sorted((r for r in rows if r.get("language") == lang),
                      key=lambda r: r.get("version") or 0, reverse=True)
        keep += mine[:KEEP_VERSIONS]
    for r in keep:
        try:
            r["text"] = docx_text(sb.storage.from_("compliance-files").download(r["file_path"])) \
                if (r.get("file_path") or "").endswith(".docx") else ""
        except Exception as e:
            print(f"      drift: version text not read ({doc_type} v{r.get('version')}): {e}")
            r["text"] = ""
    return keep


def check_client(sb, client: Mapping[str, Any], now: datetime | None = None) -> dict | None:
    """Crawl one company's site; the value to store in clients.website_drift.

    None when there is nothing to check (no website, no policy in force).
    A document type whose page could not be reached tonight keeps its previous
    result, so a site that is down for a night does not close and re-open the
    finding (and email the owner about it again).
    """
    import crawler  # noqa: PLC0415
    site = (client.get("website_url") or "").strip()
    if not site:
        return None
    now = now or datetime.now(timezone.utc)
    previous = {r.get("document_type"): r for r in
                ((client.get("website_drift") or {}).get("results") or [])}
    base = crawler.normalise_url(site)
    home_html, home_text = crawler.fetch_page(base)
    home_sh = shingles(home_text)

    results = []
    for doc_type in DOC_TYPES:
        versions = _versions(sb, client["id"], doc_type)
        if not any(v.get("status") == "in_force" for v in versions):
            continue
        given = next((v.get("published_url") for v in sorted(
            versions, key=lambda v: (v.get("status") == "in_force", v.get("version") or 0), reverse=True)
            if v.get("published_url")), None)
        unreachable = False
        if given:
            html, text = crawler.fetch_page(crawler.normalise_url(given))
            unreachable = not html
            candidates = {given: text}
        elif not home_html:
            unreachable = True
            candidates = {}
        else:
            urls = discover(doc_type, home_html, base)
            from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
            with ThreadPoolExecutor(max_workers=6) as pool:
                texts = list(pool.map(lambda u: crawler.fetch_page(u)[1], urls))
            # Drop the catch-all page: the same text as the homepage is not a policy.
            candidates = {u: t for u, t in zip(urls, texts)
                          if t and not (home_sh and shingles(t) == home_sh)}

        if unreachable:
            if doc_type in previous:
                results.append(previous[doc_type])
            continue
        pages = {u: t for u, t in candidates.items() if readable(t)}
        if not pages and (given or not readable(home_text)):
            head = max((v for v in versions if v.get("status") == "in_force"),
                       key=lambda v: v.get("version") or 0)
            r = {"state": UNREADABLE, "url": given or base, "language": head.get("language"),
                 "version_shown": None, "in_force_version": head.get("version"),
                 "in_force_since": head.get("effective_from"), "score": 0.0}
        else:
            r = compare(pages, versions)
        results.append({"document_type": doc_type, "given_url": bool(given), **r})

    if not results:
        return None
    return {"checked_at": now.isoformat(), "site": site, "results": results}
