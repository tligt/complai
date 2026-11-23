"""
test_owner_alerts.py — D-201

Run: python test_owner_alerts.py

The cases that would fail quietly: a visit announced twice because it
reloaded the results page, a beta invitation counted as a paying client, an
old event without a visit id swallowed, and a sign-up not tied to its visit.
"""

import sys

import owner_alerts as O

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


ev = [
    {"id": 1, "event": "results_viewed", "tool": "nis2", "source": None,
     "utm": {"utm_source": "linkedin", "utm_medium": "dm", "utm_campaign": "beta"},
     "visit": "abcDEF123", "created_at": "2026-11-23T10:00:00+00:00"},
    {"id": 2, "event": "results_viewed", "tool": "nis2,gdpr", "source": None, "utm": None,
     "visit": "abcDEF123", "created_at": "2026-11-23T10:05:00+00:00"},
    {"id": 3, "event": "signup", "tool": "nis2_quiz", "source": None, "utm": None,
     "visit": "abcDEF123", "created_at": "2026-11-23T10:06:00+00:00"},
    {"id": 4, "event": "results_viewed", "tool": "website", "source": "website", "utm": None,
     "visit": None, "created_at": "2026-11-23T09:00:00+00:00"},
]
items = O.finished_checks(ev)
check("one item per visit", len(items) == 2)
check("oldest first, and an old event without visit kept", items[0]["key"] == "check:event-4")
check("first results event of the visit", items[1]["checks"] == "NIS2")
check("sign-up tied to its visit", items[1]["signed_up"] and not items[0]["signed_up"])
check("origin from UTM tags", items[1]["origin"] == "source=linkedin, medium=dm, campaign=beta")
check("origin from src", items[0]["origin"] == "src=website")
check("no origin is direct", O.origin_label(None, None) == "direct")
check("check names", O.checks_label("website,gdpr,ai") == "Website check, GDPR, AI Act")
check("no checks", O.checks_label(None) == "—")

check("active Professional is paying", O.is_paying({"status": "active", "plan": "professional", "note": None}))
check("beta invitation is not paying", not O.is_paying(
    {"status": "active", "plan": "professional", "note": "Beta invitation BETA-X-ABCD: full access"}))
check("trial is not paying", not O.is_paying({"status": "trial", "plan": "starter"}))
check("registered is not paying", not O.is_paying({"status": "registered", "plan": "starter"}))

s = O.subject_for([1, 2], [1], [1])
check("subject lists paying first", s == "RECOSA: 1 paying client, 1 new account, 2 free checks finished")
lines = O.body_lines(items, [], [])
check("body has the section and a line per check", lines[0].startswith("FREE CHECKS") and len(lines) == 4)

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All owner alert tests passed.")
