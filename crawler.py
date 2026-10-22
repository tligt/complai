import ipaddress
import re
import socket
from functools import lru_cache

import requests
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise ImportError("beautifulsoup4 not installed")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
TIMEOUT = 15

# Common paths to check for compliance-relevant pages
CANDIDATE_PATHS = [
    # Privacy
    "/privacy", "/privacy-policy", "/privacy_policy", "/privacybeleid",
    "/politique-de-confidentialite", "/politique-confidentialite",
    "/datenschutz", "/gdpr", "/rgpd",
    # Cookies
    "/cookies", "/cookie-policy", "/cookie-beleid", "/politique-cookies",
    # Terms
    "/terms", "/terms-of-service", "/terms-and-conditions", "/tos",
    "/conditions", "/conditions-generales", "/cgu", "/algemene-voorwaarden",
    # Contact
    "/contact", "/contact-us", "/contactez-nous", "/contacteer-ons",
    # Security
    "/security", "/securite", "/beveiliging", "/security-policy",
    "/.well-known/security.txt",
    # Accessibility
    "/accessibility", "/accessibilite", "/toegankelijkheid",
    # Legal
    "/legal", "/mentions-legales", "/wettelijke-vermeldingen",
    "/impressum", "/imprint",
]


@dataclass
class CrawlResult:
    url: str
    homepage_html: str = ""
    homepage_text: str = ""
    found_pages: dict = field(default_factory=dict)  # path -> text content
    all_links: list = field(default_factory=list)
    error: str = ""


def normalise_url(url: str) -> str:
    """Ensure URL has a scheme."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def extract_domain(url: str) -> str:
    """Extract the base domain from a URL."""
    parsed = urlparse(url)
    return parsed.netloc.lower().replace("www.", "")


@lru_cache(maxsize=256)
def _is_public_host(host: str) -> bool:
    """True if every address the host resolves to is a public one.

    S49: the website check is now public (quiz/quiz_app.py), so the URL — and
    every link on the fetched homepage — is chosen by an anonymous visitor.
    Without this, it could point the server at loopback, the cloud metadata
    address or a private network. Unresolvable hosts are refused too.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            return False
    return bool(infos)


def is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)         and _is_public_host(parsed.hostname)


def _get_public(url: str, max_redirects: int = 5) -> requests.Response:
    """GET that follows redirects itself, checking every hop with
    is_public_url — a public site redirecting to a private address would
    otherwise slip past the check on the first URL."""
    for _ in range(max_redirects + 1):
        if not is_public_url(url):
            raise ValueError("Not a public address.")
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False)
        if resp.is_redirect and resp.headers.get("location"):
            url = urljoin(url, resp.headers["location"])
            continue
        return resp
    raise ValueError("Too many redirects.")


def fetch_page(url: str) -> tuple[str, str]:
    """Fetch a page and return (html, plain_text). Returns ('', '') on error."""
    try:
        resp = _get_public(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        text = re.sub(r"\s{2,}", " ", text).strip()
        return str(resp.content), text
    except Exception:
        return "", ""


def fetch_html_raw(url: str) -> str:
    """Fetch raw HTML for structural analysis."""
    try:
        resp = _get_public(url)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract all internal links from a page."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    base_domain = extract_domain(base_url)
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        if extract_domain(full_url) == base_domain:
            links.append(full_url)
    return list(set(links))


def crawl(url: str) -> CrawlResult:
    """
    Crawl a website for compliance audit purposes.
    Fetches the homepage and key compliance-relevant pages.
    """
    url = normalise_url(url)
    result = CrawlResult(url=url)

    # Fetch homepage
    html, text = fetch_page(url)
    if not html:
        result.error = f"Could not reach {url}. Please check the URL and try again."
        return result

    result.homepage_html = html
    result.homepage_text = text
    result.all_links = extract_links(html, url)

    # Parse base
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Check candidate paths
    targets = []
    for path in CANDIDATE_PATHS:
        candidate_url = base + path
        # Also check if it's linked from the homepage (covers non-standard paths)
        linked_match = next(
            (l for l in result.all_links if path.lower() in l.lower()),
            None
        )
        targets.append((path, linked_match or candidate_url))

    # S49: fetched in parallel. One after another took ~70 s on a Framer
    # site — too long for the public check. Results are still read in
    # CANDIDATE_PATHS order, so which page wins a key is unchanged.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(lambda pt: fetch_page(pt[1])[1], targets))

    for (path, _), page_text in zip(targets, texts):
        if page_text and len(page_text) > 100:
            # Use a normalised key
            key = path.strip("/").replace("-", "_").replace("/", "_")
            if key not in result.found_pages:
                result.found_pages[key] = page_text

    return result
