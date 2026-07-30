import requests

# Domains known to return 200 OK while being unreadable/paywalled/syndication-only,
# or where the search agent has been observed falling back to the domain
# homepage instead of a real article URL (e.g. afp.com/fr, afp.com/en).
# Add to this list as new problem sources are identified.
KNOWN_UNRELIABLE_DOMAINS = [
    "afp.com",  # covers newsroom.afp.com, www.afp.com, and homepage-fallback links
]


def check_url_reachable(url: str, timeout: int = 8) -> dict:
    """
    Checks whether a URL is reachable and not on the known-unreliable list.

    Returns a dict: {"ok": bool, "status": int|None, "reason": str|None}

    - "ok": True only if the URL returns a clean 2xx AND isn't on the
      known-unreliable domain list.
    - Uses HEAD first (cheap); falls back to GET if the server doesn't
      support HEAD (some sites return 405/501 for HEAD but work fine on GET).
    - Any exception (timeout, DNS failure, connection refused, SSL error)
      is treated as unreachable rather than raising, since this runs inside
      a batch loop and one bad URL shouldn't crash the whole monitor run.
    """
    if not url or not url.startswith(("http://", "https://")):
        return {"ok": False, "status": None, "reason": "missing_or_invalid_url"}

    for domain in KNOWN_UNRELIABLE_DOMAINS:
        if domain in url:
            return {"ok": False, "status": None, "reason": f"known_unreliable_domain:{domain}"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; RECOSA-MonitorBot/1.0; "
            "+https://recosa.eu) URL health check"
        )
    }

    try:
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            # Some sites (esp. news sites) don't support HEAD properly — retry with GET
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
            resp.close()

        if 200 <= resp.status_code < 300:
            return {"ok": True, "status": resp.status_code, "reason": None}
        else:
            return {"ok": False, "status": resp.status_code, "reason": f"http_{resp.status_code}"}

    except requests.exceptions.Timeout:
        return {"ok": False, "status": None, "reason": "timeout"}
    except requests.exceptions.SSLError:
        return {"ok": False, "status": None, "reason": "ssl_error"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "status": None, "reason": "connection_error"}
    except Exception as e:
        return {"ok": False, "status": None, "reason": f"error:{str(e)[:100]}"}


def validate_items_urls(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Splits a list of monitor items into (valid, flagged) based on URL health.

    Each item is expected to have a "url" key. Flagged items get a
    "url_check_reason" key added so the admin BO can display why they
    were held back, rather than silently dropping them.

    Usage in the existing loop (monitoring.py):

        enriched, inp, out = analyse_for_marketing(items, source, api_key)
        valid_items, flagged_items = validate_items_urls(enriched)

        for item in valid_items:
            res = save_marketing_update(item)
            ...

        for item in flagged_items:
            item["status"] = "url_flagged"   # or however status is tracked
            res = save_marketing_update(item)  # still saved, but visibly flagged
            log2(f"  ⚠️ URL flagged ({item['url_check_reason']}): {item['title'][:55]}")
    """
    valid, flagged = [], []
    for item in items:
        result = check_url_reachable(item.get("url", ""))
        if result["ok"]:
            valid.append(item)
        else:
            item["url_check_reason"] = result["reason"]
            flagged.append(item)
    return valid, flagged
