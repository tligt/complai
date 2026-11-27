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
check("opted out: no win-back", ET.next_email(0, set(), opted_out=True) is None)
WB = {"ended", "missing", "why"}
# D-222: the first notice, dates not fixed yet
check("day 38: access_closing", ET.next_email(38, WB) == "access_closing")
check("day 38, opted out: still the notice", ET.next_email(38, set(), opted_out=True) == "access_closing")
check("day 70, never noticed: the notice first, no skipping", ET.next_email(70, WB) == "access_closing")
ended = datetime(2026, 12, 8, 10, tzinfo=timezone.utc)
from datetime import timedelta as _td
on_time = ended + _td(days=38)
c, g = ET.plan_dates(ended, on_time)
check("on time: closes day 45, deleted day 60", (c - ended).days == 45 and (g - ended).days == 60)
late = ended + _td(days=50)
c2, g2 = ET.plan_dates(ended, late)
check("late notice: closes 7 days after it, deleted 15 days after that",
      (c2 - late).days == 7 and (g2 - c2).days == 15)
S1 = WB | {"access_closing"}
check("before closing: nothing", ET.next_email(40, S1, False, c, g, ended + _td(days=40)) is None)
check("closed: access_closed", ET.next_email(45, S1, False, c, g, c) == "access_closed")
check("closed, opted out: still sent", ET.next_email(45, S1, True, c, g, c) == "access_closed")
S2 = S1 | {"access_closed"}
check("day 50: nothing", ET.next_email(50, S2, False, c, g, ended + _td(days=50)) is None)
check("day 55: no reminder (the user, 27 Nov)", ET.next_email(55, S2, False, c, g, g - _td(days=5)) is None)
S3 = S2
check("access open before the date", not ET.access_closed(c, c - _td(seconds=1)))
check("access closed on the date", ET.access_closed(c, c))
check("no date: never closed", not ET.access_closed(None, ended + _td(days=400)))
_ts = lambda v: v
acc = {"status": "expired", "delete_after": g}
check("deletion due: date reached, all notices", ET.deletion_due(acc, S3, g, _ts))
check("not due: a notice missing", not ET.deletion_due(acc, S1, g + _td(days=9), _ts))
check("not due: before the date", not ET.deletion_due(acc, S3, g - _td(seconds=1), _ts))
check("not due: no date", not ET.deletion_due({"status": "expired"}, S3, g, _ts))
check("not due: subscribed", not ET.deletion_due({**acc, "status": "active"}, S3, g, _ts))
check("deletion is on", ET.DELETION_ACTIVE is True)
check("deletion 60 days later", ET.deletion_date(ended).date().isoformat() == "2027-02-06")

NOW3 = datetime(2026, 12, 20, tzinfo=timezone.utc)
for lang in ("en", "fr", "nl"):
    for company in ("Acme", None):
        for missed in ((12, 3), (12, 0), (0, 0)):
            for key in [k for k, _ in ET.SCHEDULE] + ["deleted"]:
                try:
                    e = ETE.compose(key, lang=lang, base_url="https://app.example",
                                    stop_url="https://app.example/?stop_emails=x", company=company,
                                    ended_at=ended, now=NOW3, missed=missed)
                    warning = key in ET.DELETION_EMAILS + ("deleted",)
                    ok = (bool(e.subject and e.text) and "{" not in e.subject and "{" not in e.text
                          and (e.html is None) == (key == "why")
                          and (("stop_emails=x" in e.text) != warning))
                    check(f"compose {key} {lang} company={company} missed={missed}", ok)
                except Exception as ex:
                    check(f"compose {key} {lang}: {ex}", False)

e = ETE.compose("missing", lang="en", base_url="b", stop_url="s", company="Acme", ended_at=ended,
                now=NOW3, missed=(12, 3))
check("missing: counts shown", "12 regulatory updates" in e.text and "3 of them concern Acme" in e.text)
e = ETE.compose("access_closed", lang="en", base_url="b", stop_url="s", company="Acme",
                ended_at=ended, now=NOW3, closes_at=c, delete_after=g)
check("notice: date with year when next year", "6 February 2027" in e.subject)
check("notice: what is kept", "accepted our terms" in e.text and "stop" not in e.text.split("privacy")[-1])
e = ETE.compose("access_closing", lang="fr", base_url="b", stop_url="s", company="Acme",
                ended_at=ended, now=NOW3, closes_at=c, delete_after=g)
check("access_closing: French, both dates", "22 janvier" in e.text and "6 février" in e.text)
e = ETE.compose("deleted", lang="nl", base_url="b", stop_url="", company="Acme",
                ended_at=ended, now=NOW3, closes_at=c, delete_after=g)
check("deleted: Dutch, no stop link", "verwijderd" in e.subject and "stop_emails" not in e.text)
e = ETE.compose("why", lang="nl", base_url="b", stop_url="s", company="Acme", ended_at=ended, now=NOW3)
check("why: personal, Dutch", e.sender[1] == "fabrice@recosa.eu" and e.text.startswith("Hallo"))
e = ETE.compose("ended", lang="en", base_url="b", stop_url="s", company="Acme", ended_at=ended, now=NOW3)
check("ended: says read-only meanwhile (D-222)", "read-only" in e.text.lower())

print("All lifecycle tests passed." if not failures else f"{len(failures)} failure(s).")
raise SystemExit(1 if failures else 0)
