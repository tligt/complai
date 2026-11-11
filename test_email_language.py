"""
test_email_language.py — S64 emails (D-168)

Run: python test_email_language.py [--show]

Nothing is sent: Brevo and the profile lookup are replaced. What would fail
silently: an email going out in English to a French reader, a mixed team
getting one email in one language, a placeholder left in a subject, and the
incident deadlines staying English inside a Dutch email.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.update({"BREVO_API_KEY": "k", "BREVO_FROM_EMAIL": "f@x.eu", "APP_BASE_URL": "https://app",
                   "NOTIFY_ENABLED": "true"})

import email_sender as ES
import incident_rules as R

failures = []


def check(name, cond, detail=""):
    if not cond:
        failures.append(f"{name} {detail}")


sent = []


class _Resp:
    status_code = 201
    text = ""


def _post(url, headers=None, json=None, timeout=None):
    sent.append(json)
    return _Resp()


ES.requests.post = _post
PROFILES = {"fr@x.eu": "fr", "nl@x.eu": "nl", "en@x.eu": "en"}
ES.languages_of = lambda emails, fallback=None: {
    e: ES._lang(PROFILES.get(e) or fallback) for e in dict.fromkeys(emails) if e}


def one(fn, *a, **k):
    sent.clear()
    ok = fn(*a, **k)
    check(f"{fn.__name__} accepted", ok)
    return list(sent)


def text_of(msg):
    return f'{msg["subject"]}\n{msg.get("textContent", "")}\n{msg["htmlContent"]}'


ENGLISH = ("You have", "Open the", "For confidentiality", "has given you", "Incident open",
           "Reporting deadlines", "Send what you know", "Compliance score", "We checked")

for to, lang in (("fr@x.eu", "fr"), ("nl@x.eu", "nl")):
    for fn, args in ((ES.send_ticket_reply_notification, (to, "abc12345", "T-12")),
                     (ES.send_workspace_invite, (to, "Acme", "boss@x.eu", "https://set")),
                     (ES.send_inbox_nudge, (to,)),
                     (ES.send_training_nudge, (to,)),
                     (ES.send_audit_report, (to, "https://acme.eu", b"%PDF", 72, "Amber", 5, 3, 2))):
        msgs = one(fn, *args)
        body = text_of(msgs[0]) if msgs else ""
        check(f"{fn.__name__}/{lang} in {lang}", not any(w in body for w in ENGLISH), body[:200])
        check(f"{fn.__name__}/{lang} no placeholder", "{" not in msgs[0]["subject"], msgs[0]["subject"])
        if "--show" in sys.argv:
            print(lang, "|", msgs[0]["subject"])

# The caller's language wins over the profile (a new colleague: the inviter's).
msgs = one(ES.send_workspace_invite, "en@x.eu", "Acme", "boss@x.eu", None, lang="nl")
check("invite lang given", "toegang" in msgs[0]["subject"], msgs[0]["subject"])

# A mixed incident team: one email per language; no profile → the fallback.
msgs = one(ES.send_incident_alert, ["fr@x.eu", "nl@x.eu", "new@x.eu"], "Acme", "Phishing",
           datetime(2026, 5, 1, 9, tzinfo=timezone.utc), "logged", fallback_lang="nl")
groups = sorted(sorted(r["email"] for r in m["to"]) for m in msgs)
check("alert grouped", groups == [["fr@x.eu"], ["new@x.eu", "nl@x.eu"]], str(groups))
check("alert fr", any("Incident ouvert" in m["subject"] for m in msgs))

now = datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
d = {"kind": R.GDPR_AUTHORITY, "state": R.OVERDUE, "due": now - timedelta(hours=3),
     "hours_left": -3.0}
msgs = one(ES.send_incident_reminder, ["nl@x.eu", "fr@x.eu"], "Acme", "Phishing",
           lambda lang: [(R.label(d["kind"], lang), R.describe_left(d, lang))], True)
by = {m["to"][0]["email"]: m["htmlContent"] for m in msgs}
check("reminder nl deadline", "gegevensbeschermingsautoriteit" in by.get("nl@x.eu", "")
      and "3 u te laat" in by.get("nl@x.eu", ""), by.get("nl@x.eu", "")[-600:])
check("reminder fr deadline", "en retard de 3 h" in by.get("fr@x.eu", ""))
check("describe_left nl future", R.describe_left({**d, "state": R.RUNNING, "hours_left": 5.5}, "nl")
      == "over 5 u 30")

# English stays English.
msgs = one(ES.send_inbox_nudge, "en@x.eu")
check("en unchanged", msgs[0]["subject"] == "Something new for you in RECOSA")

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f[:300])
    sys.exit(1)
print("All email language tests passed.")
