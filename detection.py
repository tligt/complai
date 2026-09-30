"""
detection.py — S48: which catalogue vendors does a company use?

Reads two public signals and matches them against the catalogue's
fingerprints (`vendor_domain_patterns`, authored in inventory_seed.py):

  Website  the homepage's script sources, iframes, images, stylesheets,
           inline code and response headers, plus the public Google Tag
           Manager container when the page loads one. Tags GTM injects at
           runtime are invisible to a static fetch; the container file
           lists them.
  DNS      MX hosts (the email provider) and SPF includes (services allowed
           to send mail for the domain).

Pure module: no Streamlit, no database writes. It only *suggests*: the UI
shows each detection with its evidence and the user confirms before
anything reaches the inventory (S48 scope lock). Services found but
matched by no fingerprint come back separately in `other_services`, so
they can be added by hand and point at which vendors to catalogue next.

Limits, accepted in the scope lock: cookies set by JavaScript are never
seen, so `cookie_name` fingerprints only match when the name appears in
the page's own code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from crawler import HEADERS, TIMEOUT, extract_domain, normalise_url

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

# Google Tag Manager container ids on the page, e.g. GTM-ABC1234.
_GTM_ID_RE = re.compile(r"\bGTM-[A-Z0-9]{4,10}\b")
_GTM_URL = "https://www.googletagmanager.com/gtm.js?id={}"
_MAX_GTM_CONTAINERS = 3

# Only the start of the SPF record matters; includes and redirects name the
# services (e.g. include:spf.protection.outlook.com).
_SPF_MECHANISM_RE = re.compile(r"(?:include:|redirect=)([^\s]+)", re.IGNORECASE)


@dataclass
class Detection:
    catalogue_key: str
    name: str
    confidence: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    domain: str
    detected: list[Detection] = field(default_factory=list)
    # (host, how it was seen), for services no fingerprint recognises
    other_services: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Signals ──────────────────────────────────────────────────────────────

@dataclass
class _WebSignals:
    script_srcs: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)        # every resource URL referenced
    code: str = ""                                      # inline scripts + raw HTML
    headers: list[str] = field(default_factory=list)    # "name: value", lowercased
    gtm: dict[str, str] = field(default_factory=dict)   # container id -> body


def _fetch_web_signals(url: str) -> tuple[_WebSignals | None, str | None]:
    """Homepage signals, or (None, error)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return None, f"Could not load {url}: {e}"

    sig = _WebSignals()
    sig.headers = [f"{k}: {v}".lower() for k, v in resp.headers.items()]
    html = resp.text
    sig.code = html
    soup = BeautifulSoup(html, "html.parser")
    base = resp.url

    for tag, attr in (("script", "src"), ("iframe", "src"), ("img", "src"),
                      ("link", "href"), ("source", "src"), ("embed", "src")):
        for el in soup.find_all(tag):
            val = el.get(attr)
            if not val or val.startswith(("data:", "javascript:", "#")):
                continue
            absolute = urljoin(base, val)
            sig.urls.add(absolute)
            if tag == "script":
                sig.script_srcs.add(absolute)

    for gtm_id in list(dict.fromkeys(_GTM_ID_RE.findall(html)))[:_MAX_GTM_CONTAINERS]:
        try:
            g = requests.get(_GTM_URL.format(gtm_id), headers=HEADERS, timeout=10)
            if g.ok:
                sig.gtm[gtm_id] = g.text
        except Exception:
            pass   # the container is a bonus signal; the page scan stands without it

    return sig, None


def _fetch_dns_signals(domain: str) -> tuple[list[str], list[str], list[str]]:
    """(mx hosts, spf includes, errors). Hosts lowercased, no trailing dot."""
    try:
        import dns.resolver
    except ImportError:
        return [], [], ["DNS lookup unavailable (dnspython not installed)."]

    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    mx, spf, errors = [], [], []
    try:
        mx = sorted(str(r.exchange).rstrip(".").lower() for r in resolver.resolve(domain, "MX"))
    except Exception as e:
        errors.append(f"No MX records found for {domain} ({type(e).__name__}).")
    try:
        for r in resolver.resolve(domain, "TXT"):
            txt = b"".join(r.strings).decode("utf-8", "ignore")
            if txt.lower().startswith("v=spf1"):
                spf += [m.rstrip(".").lower() for m in _SPF_MECHANISM_RE.findall(txt)]
    except Exception:
        pass   # no TXT/SPF is common and not an error worth showing
    return mx, spf, errors


# ── Matching ─────────────────────────────────────────────────────────────

def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _host_matches(host: str, pattern: str) -> bool:
    return host == pattern or host.endswith("." + pattern)


def _url_matches(url: str, pattern: str) -> bool:
    """A pattern with a path ('facebook.com/tr') matches as a substring of
    the URL; a bare host pattern matches the host or any subdomain."""
    if "/" in pattern:
        return pattern in url.lower()
    return _host_matches(_host(url), pattern)


def _code_mentions_host(code: str, pattern: str) -> bool:
    return re.search(r"(?<![a-z0-9.-])" + re.escape(pattern), code, re.IGNORECASE) is not None


def _base_domain(host: str) -> str:
    """Last two labels: mx1.pub.mailpod6-cph3.one.com -> one.com. Naive about
    two-part suffixes like co.uk, which is fine for display grouping."""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _first_party(host: str, site: str) -> bool:
    return bool(host) and (_host_matches(host, site) or _host_matches(site, host))


def _match_pattern(p: dict, web: _WebSignals | None, mx: list[str],
                   spf: list[str], site: str) -> str | None:
    """Evidence text if fingerprint `p` matches, else None. Resources on the
    company's own domain never count: scanning hubspot.com must not suggest
    HubSpot as a vendor of HubSpot."""
    pat, kind = p["pattern"].lower(), p["match_type"]
    if _first_party(pat.split("/")[0], site):
        return None

    if kind == "mx":
        hit = next((h for h in mx if _host_matches(h, pat)), None)
        return f"email (MX) handled by {hit}" if hit else None
    if kind == "spf_include":
        hit = next((h for h in spf if _host_matches(h, pat)), None)
        return f"allowed to send email for the domain (SPF include:{hit})" if hit else None
    if web is None:
        return None

    def third_party(urls):
        return (u for u in urls if not _first_party(_host(u), site))

    def via_gtm():
        gtm = next((g for g, body in web.gtm.items() if pat in body.lower()), None)
        return f"loaded through Google Tag Manager ({gtm})" if gtm else None

    if kind == "script_src":
        hit = next((u for u in third_party(web.script_srcs) if _url_matches(u, pat)), None)
        return f"script loaded from {_host(hit) or hit}" if hit else via_gtm()
    if kind == "domain":
        hit = next((u for u in third_party(web.urls) if _url_matches(u, pat)), None)
        if hit:
            return f"page loads a resource from {_host(hit) or hit}"
        if _code_mentions_host(web.code, pat):
            return f"page code references {pat}"
        return via_gtm()
    if kind == "cookie_name":
        quoted = re.compile(r"""["']""" + re.escape(pat) + r"""["']""")
        if quoted.search(web.code) or any(quoted.search(b) for b in web.gtm.values()):
            return f"cookie '{p['pattern']}' referenced in the page's code"
        return None
    if kind == "header":
        hit = next((h for h in web.headers if pat in h), None)
        return f"response header '{hit}'" if hit else None
    return None


def match_signals(patterns: list[dict], web: _WebSignals | None,
                  mx: list[str], spf: list[str], site: str) -> list[Detection]:
    """Group fingerprint hits by vendor. `patterns` rows carry catalogue_key,
    name, pattern, match_type and confidence. Highest confidence wins."""
    by_key: dict[str, Detection] = {}
    for p in patterns:
        evidence = _match_pattern(p, web, mx, spf, site)
        if not evidence:
            continue
        d = by_key.setdefault(p["catalogue_key"], Detection(
            catalogue_key=p["catalogue_key"], name=p["name"], confidence=p["confidence"]))
        if evidence not in d.evidence:
            d.evidence.append(evidence)
        if CONFIDENCE_RANK[p["confidence"]] > CONFIDENCE_RANK[d.confidence]:
            d.confidence = p["confidence"]
    return sorted(by_key.values(),
                  key=lambda d: (-CONFIDENCE_RANK[d.confidence], d.name.lower()))


def _other_services(web: _WebSignals | None, mx: list[str], spf: list[str],
                    site: str, patterns: list[dict]) -> list[tuple[str, str]]:
    """Services seen but recognised by no fingerprint: third-party hosts the
    page loads scripts from, and the mail hosts in MX and SPF. Images and
    stylesheets are left out: CDNs and font hosts would drown the list."""
    def known(host: str, kinds: tuple[str, ...]) -> bool:
        return any(_host_matches(host, p["pattern"].lower()) for p in patterns
                   if p["match_type"] in kinds and "/" not in p["pattern"])

    out: dict[str, str] = {}
    for u in (web.script_srcs if web else set()):
        h = _host(u).removeprefix("www.")
        if h and not _first_party(h, site) and not known(h, ("domain", "script_src")):
            out.setdefault(h, "script on the website")
    for h in mx:
        if not known(h, ("mx",)):
            out.setdefault(_base_domain(h), "email (MX)")
    for h in spf:
        if not known(h, ("spf_include",)) and not _first_party(h, site):
            out.setdefault(_base_domain(h), "sends email for the domain (SPF)")
    return sorted(out.items())


def result_from_saved(row: dict) -> DetectionResult:
    """Rebuild a DetectionResult from a stored website_scans row, so a past
    scan can be shown and acted on like a fresh one."""
    return DetectionResult(
        domain=row.get("domain") or "",
        detected=[Detection(catalogue_key=d["catalogue_key"], name=d["name"],
                            confidence=d["confidence"], evidence=list(d.get("evidence") or []))
                  for d in row.get("detected") or []],
        other_services=[(o["host"], o["how"]) for o in row.get("other_services") or []],
        errors=list(row.get("errors") or []),
    )


# ── Entry point ──────────────────────────────────────────────────────────

def load_patterns() -> list[dict]:
    """Fingerprints joined to their catalogue vendor (key, name)."""
    from database import get_supabase
    rows = (get_supabase().table("vendor_domain_patterns")
            .select("pattern, match_type, confidence, vendor_catalogue(key, name, active)")
            .execute().data or [])
    return [{"pattern": r["pattern"], "match_type": r["match_type"],
             "confidence": r["confidence"],
             "catalogue_key": r["vendor_catalogue"]["key"],
             "name": r["vendor_catalogue"]["name"]}
            for r in rows if (r.get("vendor_catalogue") or {}).get("active")]


def detect(website: str, patterns: list[dict] | None = None) -> DetectionResult:
    """Scan a company's website and its domain's DNS. Never raises:
    failures come back in `errors`, alongside whatever did work."""
    url = normalise_url(website.strip())
    domain = extract_domain(url).removeprefix("www.")
    result = DetectionResult(domain=domain)
    if not domain:
        result.errors.append("That doesn't look like a website address.")
        return result
    if patterns is None:
        patterns = load_patterns()

    web, err = _fetch_web_signals(url)
    if err:
        result.errors.append(err)
    mx, spf, dns_errors = _fetch_dns_signals(domain)
    result.errors += dns_errors

    result.detected = match_signals(patterns, web, mx, spf, domain)
    result.other_services = _other_services(web, mx, spf, domain, patterns)
    return result
