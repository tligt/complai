"""test_onboarding.py — D-212: the onboarding email schedule, the stop link,
and that every email composes in every language. No database, no sending.

    python test_onboarding.py
"""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-key")

import onboarding as OB
import onboarding_emails as OE

failures = []


def check(name, ok):
    if not ok:
        failures.append(name)
        print(f"FAIL  {name}")


NOW = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)
ago = lambda h: NOW - timedelta(hours=h)
NONE_DONE = {k: False for k in OB.STEP_ORDER}

# trial_day
check("day 0 on the first day", OB.trial_day(NOW + timedelta(days=14), NOW) == 0)
check("day 3", OB.trial_day(NOW + timedelta(days=11), NOW) == 3)

# The normal path: one a day as scheduled.
check("welcome first", OB.next_email(0, {}, NOW, False) == "welcome")
check("nothing else on day 0", OB.next_email(0, {"welcome": ago(2)}, NOW, False) is None)
check("personal on day 1", OB.next_email(1, {"welcome": ago(24)}, NOW, False) == "personal")
check("step_a on day 2", OB.next_email(2, {"welcome": ago(48), "personal": ago(24)}, NOW, False) == "step_a")
check("nothing on day 3", OB.next_email(3, {"welcome": ago(72), "personal": ago(48), "step_a": ago(24)}, NOW, False) is None)
check("wrapup on day 8", OB.next_email(8, {k: ago(30) for k in ("welcome", "personal", "step_a", "step_b", "step_c")}, NOW, False) == "wrapup")
check("all sent: nothing", OB.next_email(9, {k: ago(30) for k, _ in OB.SCHEDULE}, NOW, False) is None)

# Pacing
check("not within 20 h", OB.next_email(1, {"welcome": ago(10)}, NOW, False) is None)

# Late start (the visitor: trial counted from sign-up, first login on day 7)
check("late: welcome first even on day 7", OB.next_email(7, {}, NOW, False) == "welcome")
check("late: then the most recent due, not the missed ones",
      OB.next_email(7, {"welcome": ago(24)}, NOW, False) == "step_c")
check("late: then wrapup on day 8",
      OB.next_email(8, {"welcome": ago(48), "step_c": ago(24)}, NOW, False) == "wrapup")

# All five done: straight to the wrap-up from day 2
check("all done day 1: nothing", OB.next_email(1, {"welcome": ago(24)}, NOW, True) is None)
check("all done day 2: wrapup", OB.next_email(2, {"welcome": ago(48)}, NOW, True) == "wrapup")
check("all done, wrapup sent: nothing", OB.next_email(5, {"welcome": ago(99), "wrapup": ago(30)}, NOW, True) is None)

# The flow's window
check("day 10: flow 2's turn", OB.next_email(10, {}, NOW, False) is None)
check("before the trial: nothing", OB.next_email(-1, {}, NOW, False) is None)

# Steps
check("first pending", OB.first_pending({**NONE_DONE, "profile": True}) == "inventory")
check("none pending", OB.first_pending({k: True for k in OB.STEP_ORDER}) is None)

# Stop link
tok = OB.stop_token("abc-123")
check("token round trip", OB.user_from_stop_token(tok) == "abc-123")
check("forged token refused", OB.user_from_stop_token("other-user." + tok.split(".")[1]) is None)
check("garbage refused", OB.user_from_stop_token("nonsense") is None)

# Every email, every language, with and without a company
for lang in ("en", "fr", "nl"):
    for company in ("Acme", None):
        for done in (NONE_DONE, {**NONE_DONE, "profile": True, "inventory": True},
                     {k: True for k in OB.STEP_ORDER}):
            for key, _ in OB.SCHEDULE:
                try:
                    e = OE.compose(key, lang=lang, base_url="https://app.example", stop_url="https://app.example/?stop_emails=x",
                                   company=company, done=done)
                    # The day-1 note has no footer (the user, 27 Nov).
                    ok = bool(e.subject and e.text
                              and ("stop_emails=x" in e.text) == (key != "personal")
                              and (e.html is None) == (key == "personal")
                              and "{" not in e.subject and "{" not in e.text)
                    check(f"compose {key} {lang} company={company} done={sum(done.values())}", ok)
                except Exception as ex:
                    check(f"compose {key} {lang}: {ex}", False)

e = OE.compose("step_a", lang="en", base_url="https://app.example", stop_url="s", company="Acme",
               done={**NONE_DONE, "profile": True})
check("step email links to the first pending step", "https://app.example/inventory?" in e.text)
e = OE.compose("personal", lang="fr", base_url="b", stop_url="s", company="Acme", done=NONE_DONE)
check("personal is from fabrice@recosa.eu", e.sender == ("Fabrice from RECOSA", "fabrice@recosa.eu"))
check("personal in French", e.text.startswith("Bonjour"))
check("personal: no footer, no stop link", "--" not in e.text and "stop" not in e.text.lower())

# The user's review, 27 Nov
from datetime import timedelta as _td
ENDS = NOW + _td(days=12, hours=3)
e = OE.compose("welcome", lang="en", base_url="https://app.example", stop_url="s", company="Acme",
               done=NONE_DONE, ends_at=ENDS, now=NOW)
check("welcome: thanks, date, features, button, nothing lost, reply",
      e.text.startswith("Thank you for choosing RECOSA") and "until" in e.text
      and "Your systems, mapped:" in e.text and "Complete my profile: https://app.example/company?" in e.text
      and "Nothing you do now is lost." in e.text and "Just reply to this email" in e.text)
check("welcome: footer says signed up, not subscribed",
      "signed up for RECOSA" in e.text and "you subscribe to" not in e.text)
check("welcome: header tagline", "your AI-powered EU compliance co-pilot" in e.html)
check("welcome: copyright", "CREAGENT SRL" in e.html)
e = OE.compose("step_a", lang="en", base_url="https://app.example", stop_url="s", company="Acme",
               done={**NONE_DONE, "profile": True}, ends_at=ENDS, now=NOW)
check("step: days left in subject and text", e.subject.startswith("13 days left")
      and e.text.startswith("Don't forget: your 14-day RECOSA trial is running, with 13 days left"))
check("step: progress after the button", e.text.index("Add my systems:") < e.text.index("1 of 5"))
e = OE.compose("welcome", lang="nl", base_url="b", stop_url="s", company="Acme", done=NONE_DONE,
               ends_at=ENDS, now=NOW)
check("welcome: Dutch tagline", "uw AI-copiloot voor EU-compliance" in e.html)
import os as _os
_os.environ["SUPPORT_REPLY_TO"] = "support@recosa.eu"
e = OE.compose("welcome", lang="en", base_url="b", stop_url="s", company="Acme", done=NONE_DONE)
check("replies to support when set", e.reply_to == ("RECOSA support", "support@recosa.eu"))
del _os.environ["SUPPORT_REPLY_TO"]
e = OE.compose("welcome", lang="en", base_url="b", stop_url="s", company="Acme", done=NONE_DONE)
check("no reply-to when not set", e.reply_to is None)

print("All onboarding tests passed." if not failures else f"{len(failures)} failure(s).")
raise SystemExit(1 if failures else 0)
