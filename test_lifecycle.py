"""test_lifecycle.py — D-213: the trial-ending flow (schedule, dates, every
email in every language). No database, no sending. The onboarding flow has
test_onboarding.py.

    python test_lifecycle.py
"""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-key")

import trial_ending as TE
import trial_ending_emails as TEE

failures = []


def check(name, ok):
    if not ok:
        failures.append(name)
        print(f"FAIL  {name}")


# Schedule
check("day 9: onboarding's turn", TE.next_email(9, set()) is None)
check("day 10: four_days", TE.next_email(10, set()) == "four_days")
check("day 11: four_days still due", TE.next_email(11, set()) == "four_days")
check("day 11, sent: nothing", TE.next_email(11, {"four_days"}) is None)
check("day 13: last_day", TE.next_email(13, {"four_days"}) == "last_day")
check("day 13, late start: only last_day", TE.next_email(13, set()) == "last_day")
check("day 13, both sent: nothing", TE.next_email(13, {"four_days", "last_day"}) is None)
check("day 14: trial over", TE.next_email(14, set()) is None)

# Dates
d = datetime(2026, 12, 8, tzinfo=timezone.utc)
check("date en", TEE.long_date(d, "en") == "8 December")
check("date fr", TEE.long_date(d, "fr") == "8 décembre")
check("date nl", TEE.long_date(d, "nl") == "8 december")

# Every email, every language, with and without figures and a company
FULL = {"systems": 6, "activities": 4, "documents": 5, "score": 62, "alerts": 11}
EMPTY = {"systems": 0, "activities": 0, "documents": 0, "score": None, "alerts": 0}
for lang in ("en", "fr", "nl"):
    for company in ("Acme", None):
        for figs in (FULL, EMPTY):
            for key, _ in TE.SCHEDULE:
                try:
                    e = TEE.compose(key, lang=lang, base_url="https://app.example",
                                    stop_url="https://app.example/?stop_emails=x",
                                    company=company, ends_at=d, figures=figs)
                    ok = (bool(e.subject and e.text and e.html) and "stop_emails=x" in e.text
                          and "/subscribe?" in e.text and "utm_campaign=trial_ending" in e.text
                          and "{" not in e.subject and "{" not in e.text)
                    check(f"compose {key} {lang} company={company} figs={bool(figs['systems'])}", ok)
                except Exception as ex:
                    check(f"compose {key} {lang}: {ex}", False)

e = TEE.compose("four_days", lang="en", base_url="b", stop_url="s", company="Acme", ends_at=d,
                figures=FULL)
check("figures shown", "6 systems and 4 processing activities" in e.text and "62%" in e.text)
check("prices shown", "€49" in e.text and "€149" in e.text)
e = TEE.compose("four_days", lang="en", base_url="b", stop_url="s", company="Acme", ends_at=d,
                figures=EMPTY)
check("nothing built: no figure list", "systems and" not in e.text and "still time" in e.text)
check("no promise of read-only", "read-only" not in e.text.lower())

# ── Flow 3: expired trial (D-214) ─────────────────────────────────────────
import expired_trial as ET
import expired_trial_emails as ETE

check("day 0: ended", ET.next_email(0, set()) == "ended")
check("day 3, sent: nothing", ET.next_email(3, {"ended"}) is None)
check("day 7: missing", ET.next_email(7, {"ended"}) == "missing")
check("day 21: why", ET.next_email(21, {"ended", "missing"}) == "why")
check("late (day 9, nothing sent): only the latest", ET.next_email(9, set()) == "missing")
check("day 30, all sent: nothing", ET.next_email(30, {"ended", "missing", "why"}) is None)
check("deletion off: no warning on day 46", ET.next_email(46, {"ended", "missing", "why"}) is None)
check("deletion on: warning on day 46",
      ET.next_email(46, {"ended", "missing", "why"}, deletion_active=True) == "deletion_warning")
check("deletion on: last warning on day 56",
      ET.next_email(56, {"ended", "missing", "why", "deletion_warning"}, deletion_active=True) == "last_warning")
check("opted out: no win-back", ET.next_email(0, set(), opted_out=True) is None)
check("opted out: still the deletion warning",
      ET.next_email(46, set(), opted_out=True, deletion_active=True) == "deletion_warning")
check("day 60: over", ET.next_email(60, set(), deletion_active=True) is None)
check("deletion is off for now", ET.DELETION_ACTIVE is False)
ended = datetime(2026, 12, 8, 10, tzinfo=timezone.utc)
check("deletion 60 days later", ET.deletion_date(ended).date().isoformat() == "2027-02-06")

NOW3 = datetime(2026, 12, 20, tzinfo=timezone.utc)
for lang in ("en", "fr", "nl"):
    for company in ("Acme", None):
        for missed in ((12, 3), (12, 0), (0, 0)):
            for key, _ in ET.SCHEDULE:
                try:
                    e = ETE.compose(key, lang=lang, base_url="https://app.example",
                                    stop_url="https://app.example/?stop_emails=x", company=company,
                                    ended_at=ended, now=NOW3, missed=missed)
                    warning = key in ET.DELETION_EMAILS
                    ok = (bool(e.subject and e.text) and "{" not in e.subject and "{" not in e.text
                          and (e.html is None) == (key == "why")
                          and (("stop_emails=x" in e.text) != warning))
                    check(f"compose {key} {lang} company={company} missed={missed}", ok)
                except Exception as ex:
                    check(f"compose {key} {lang}: {ex}", False)

e = ETE.compose("missing", lang="en", base_url="b", stop_url="s", company="Acme", ended_at=ended,
                now=NOW3, missed=(12, 3))
check("missing: counts shown", "12 regulatory updates" in e.text and "3 of them concern Acme" in e.text)
e = ETE.compose("deletion_warning", lang="en", base_url="b", stop_url="s", company="Acme",
                ended_at=ended, now=NOW3)
check("warning: date with year when next year", "6 February 2027" in e.subject)
e = ETE.compose("why", lang="nl", base_url="b", stop_url="s", company="Acme", ended_at=ended, now=NOW3)
check("why: personal, Dutch", e.sender[1] == "fabrice@recosa.eu" and e.text.startswith("Hallo"))
e = ETE.compose("ended", lang="en", base_url="b", stop_url="s", company="Acme", ended_at=ended, now=NOW3)
check("ended: no read-only promise", "read-only" not in e.text.lower())

print("All lifecycle tests passed." if not failures else f"{len(failures)} failure(s).")
raise SystemExit(1 if failures else 0)
