"""
expired_trial.py — D-214, D-222. The expired-trial flow (flow 3 of the five
agreed on 25 Nov): a trial that ended without a plan. Days count from the
trial's end.

    day 0    ended           "your trial has ended": everything is kept
    day 7    missing         the regulatory updates since, and how many concern them
    day 21   why             plain text from Fabrice: "what stopped you?"
    day 38   access_closing  "access closes on [date]: download what you need"  ┐ notices: sent
    day 45   access_closed   "access closed; deleted on [date]"                 ┘ even if opted out
    day 60   deleted         the account is deleted (account_deletion.py), and a last email

No reminder between day 45 and the deletion (the user, 27 Nov): the day-45
notice gives the date, and a second warning would make it look less certain.

Phases (agreed 27 Nov, D-222): read-only from the trial's end, no access from
day 45 (the subscribe page only), deleted on day 60.

The dates are fixed when the first notice goes out, and stored on the account
(accounts.access_closes_at, accounts.delete_after): access closes no sooner
than ACCESS_NOTICE_DAYS after that notice, and the deletion follows
NO_ACCESS_DAYS later. So nobody loses access or data without the notices,
even an account the job reaches late, and the emails, the app and the
deletion all read the same dates. An account the job never emails (admins,
test accounts, no owner email) gets no dates: never closed, never deleted.

Rules (next_email): the most recent due. The win-back emails (ended, missing,
why) respect the "stop these emails" link; the notices do not. Pacing across
flows is the job's (monitor_lifecycle.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta

FLOW = "expired_trial"
ACCESS_DAYS = 45            # read-only until then
DELETE_AFTER_DAYS = 60      # no access from ACCESS_DAYS until then
NO_ACCESS_DAYS = DELETE_AFTER_DAYS - ACCESS_DAYS
ACCESS_NOTICE_DAYS = 7      # the "access closes" notice comes at least this long before
DELETION_ACTIVE = True
SCHEDULE = [("ended", 0), ("missing", 7), ("why", 21),
            ("access_closing", ACCESS_DAYS - ACCESS_NOTICE_DAYS),
            ("access_closed", ACCESS_DAYS)]
DELETION_EMAILS = ("access_closing", "access_closed")
WINBACK_EMAILS = ("ended", "missing", "why")


def days_since(ended_at: datetime, now: datetime) -> int:
    return (now - ended_at).days


def plan_dates(ended_at: datetime, now: datetime) -> tuple[datetime, datetime]:
    """(access closes, deleted after), fixed when the first notice is sent:
    day 45 and day 60, pushed back if the notice goes out late."""
    closes = max(ended_at + timedelta(days=ACCESS_DAYS), now + timedelta(days=ACCESS_NOTICE_DAYS))
    return closes, closes + timedelta(days=NO_ACCESS_DAYS)


def deletion_date(ended_at: datetime) -> datetime:
    """The nominal date (day 60), for the back office before dates are fixed."""
    return ended_at + timedelta(days=DELETE_AFTER_DAYS)


def access_closed(closes_at: datetime | None, now: datetime) -> bool:
    return bool(closes_at) and now >= closes_at


def next_email(day: int, sent: set[str], opted_out: bool = False,
               closes_at: datetime | None = None, delete_after: datetime | None = None,
               now: datetime | None = None) -> str | None:
    """The email due, or None. Notices follow the stored dates once fixed."""
    if day < 0:
        return None
    if closes_at and delete_after and now:
        due = "access_closed" if now >= closes_at else None
        if due and due not in sent:
            return due
        if due:
            return None
    elif day >= ACCESS_DAYS - ACCESS_NOTICE_DAYS:
        # Dates not fixed yet: the first notice, whatever the day.
        return None if "access_closing" in sent else "access_closing"
    if opted_out:
        return None
    due = [k for k, d in SCHEDULE if k in WINBACK_EMAILS and d <= day]
    if not due or due[-1] in sent:
        return None
    return due[-1]


def deletion_due(acc: dict, sent: set[str], now: datetime, ts) -> bool:
    """Every notice sent and the date reached. `ts` parses the stored dates."""
    delete_after = ts(acc.get("delete_after"))
    return (acc.get("status") == "expired" and bool(delete_after) and now >= delete_after
            and all(k in sent for k in DELETION_EMAILS))


def missed_updates(sb, client: dict | None, since: datetime) -> tuple[int, int]:
    """(regulatory updates approved since `since`, of which for this company)."""
    total = sb.table("regulatory_updates").select("id", count="exact") \
        .eq("status", "approved").gte("approved_at", since.isoformat()).limit(1).execute().count or 0
    mine = 0
    if client:
        mine = sb.table("client_alerts").select("id", count="exact").eq("client_id", client["id"]) \
            .gte("notified_at", since.isoformat()).limit(1).execute().count or 0
    return total, mine
