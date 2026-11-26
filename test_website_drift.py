"""
test_website_drift.py — the website-drift crawl (D-218)

Run: python test_website_drift.py

The cases that would mislead a client: a page showing the version in force
reported as wrong because the site adds its own menu and footer; v2 and v3
that differ by one clause told apart the wrong way round (or not at all); two
identical versions reported as "your site shows the old one"; a catch-all
homepage counted as a policy; a JavaScript site reported as "not found"; and a
finding whose key changes when its state does, which would email the owner
about the same page again.
"""

import sys

import heartbeat as H
import website_drift as W

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


BASE = (
    "creagent SRL is the data controller responsible for the processing of your personal data "
    "under the General Data Protection Regulation. We collect your name, your email address and "
    "the content of your messages when you contact us through the form on this website. We keep "
    "these data for three years after our last exchange and then delete them. You have the right "
    "to access, rectify and erase your data, to restrict or object to their processing, and to "
    "data portability. You may lodge a complaint with the Data Protection Authority in Brussels. "
)
OLD_CLAUSE = "We share your data with our hosting provider in Ireland under standard contractual clauses. "
NEW_CLAUSE = ("We share your data with our hosting provider in France, and with our accounting firm, "
              "which processes invoices on our behalf as a processor. ")
SITE = "Home About Services Contact Menu. " * 3 + " Copyright 2026 all rights reserved, made with love in Liege."

V2 = BASE + OLD_CLAUSE
V3 = BASE + NEW_CLAUSE


def ver(v, status, text, lang="en"):
    return {"version": v, "status": status, "language": lang, "effective_from": "2026-09-01", "text": text}


# ── Text ──────────────────────────────────────────────────────────────────
check("accents and case ignored", W.words("Données PERSONNELLES") == ["donnees", "personnelles"])
check("containment of nothing is 0", W.containment(set(), {"a"}) == 0.0)

# ── compare() ─────────────────────────────────────────────────────────────
vs = [ver(2, "superseded", V2), ver(3, "in_force", V3)]

r = W.compare({"https://x.be/privacy": SITE + V3 + SITE}, vs)
check("in-force text inside the site's own menu and footer matches", r["state"] == W.MATCHES)
check("matches names the version", r["version_shown"] == 3 and r["in_force_version"] == 3)

r = W.compare({"https://x.be/privacy": SITE + V2 + SITE}, vs)
check("one clause apart: the older version is recognised", r["state"] == W.OLDER)
check("older names both versions", r["version_shown"] == 2 and r["in_force_version"] == 3)
check("older keeps the page", r["url"] == "https://x.be/privacy")

r = W.compare({"https://x.be/privacy": V3}, [ver(2, "superseded", V3), ver(3, "in_force", V3)])
check("identical versions are never 'the old one'", r["state"] == W.MATCHES and r["version_shown"] == 3)

r = W.compare({"https://x.be/privacy": SITE + "Our own privacy text written by hand, nothing like the generated one. " * 5}, vs)
check("an unrelated page is not named as the policy", r["state"] == W.NOT_FOUND and r["url"] is None)

HALF = BASE[: len(BASE) // 2] + " Our own rewritten paragraphs about retention, rights and transfers follow here. " * 4
r = W.compare({"https://x.be/privacy": SITE + HALF}, vs)
check("a page carrying part of the policy differs", r["state"] == W.DIFFERS and r["version_shown"] is None)
check("differs keeps the page", r["url"] == "https://x.be/privacy")

r = W.compare({}, vs)
check("no page is not found", r["state"] == W.NOT_FOUND and r["in_force_version"] == 3)

# Two languages in force; the site shows the French one.
FR = ("creagent SRL est le responsable du traitement de vos donnees personnelles au sens du "
      "reglement general sur la protection des donnees. Nous collectons votre nom et votre adresse "
      "email lorsque vous nous contactez par le formulaire de ce site et les gardons trois ans. ")
r = W.compare({"https://x.be/vie-privee": FR}, vs + [ver(1, "in_force", FR, "fr")])
check("the in-force version of another language matches", r["state"] == W.MATCHES and r["language"] == "fr")

# The best page wins when several are found.
r = W.compare({"https://x.be/legal": SITE, "https://x.be/privacy": V3}, vs)
check("the page that carries the policy is the one reported", r["url"] == "https://x.be/privacy")

# ── discover() ────────────────────────────────────────────────────────────
HOME = ('<a href="/legal/notice-3">Privacy</a> <a href="/cookie-settings">Cookies</a> '
        '<a href="https://other.com/privacy">Their privacy</a> <a href="/about">About</a>')
urls = W.discover("privacy_policy", HOME, "https://www.x.be")
check("a link titled Privacy is found whatever its address", urls[0] == "https://www.x.be/legal/notice-3")
check("another site's links are not followed", not any("other.com" in u for u in urls))
check("the usual paths come after", "https://www.x.be/privacy" in urls)
check("no duplicates", len(urls) == len(set(urls)))
check("cookie links go to the cookie policy", W.discover("cookie_policy", HOME, "https://www.x.be")[0]
      == "https://www.x.be/cookie-settings")

# ── heartbeat findings ────────────────────────────────────────────────────
LABELS = {"privacy_policy": "Privacy Policy", "cookie_policy": "Cookie Policy"}


def drift(state, **kw):
    return {"site": "www.x.be", "results": [{"document_type": "privacy_policy", "state": state,
            "url": "https://x.be/privacy", "language": "en", "in_force_version": 3,
            "in_force_since": "2026-09-01", "version_shown": 2, "score": 0.42, **kw}]}


check("matches is no finding", H.website_drift(drift("matches"), LABELS) == [])
check("no stored crawl is no finding", H.website_drift(None, LABELS) == [])
fs = {s: H.website_drift(drift(s), LABELS) for s in ("older", "differs", "not_found", "unreadable")}
check("every other state is one finding", all(len(f) == 1 for f in fs.values()))
check("one key per document type, whatever the state",
      {f[0]["finding_key"] for f in fs.values()} == {"heartbeat:drift:privacy_policy"})
check("older says which versions", "v2" in fs["older"][0]["title"] and "v3" in fs["older"][0]["title"])
check("differs gives the share found", "42%" in fs["differs"][0]["detail"])
check("unreadable never claims it is missing", "not found" not in fs["unreadable"][0]["title"])
check("findings point to Documents", all(f[0]["link"] == "documents" for f in fs.values()))
check("drift reaches findings()", H.findings(drift=drift("older"), doc_labels=LABELS)[0]["finding_key"]
      == "heartbeat:drift:privacy_policy")

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("test_website_drift: all passed")
