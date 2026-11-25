"""
expired_trial.py — D-214. The expired-trial email flow (flow 3 of the five
agreed on 25 Nov): a trial that ended without a plan. Days count from the
trial's end.

    day 0    ended             "your trial has ended": everything is kept
    day 7    missing           the regulatory updates since, and how many concern them
    day 21   why               plain text from Fabrice: "what stopped you?"
    day 45   deletion_warning  "deleted on [day 60]"            ┐ off until the
    day 55   last_warning      "5 days before it is deleted"    ┘ deletion exists

The two deletion warnings are written and tested but not sent while
DELETION_ACTIVE is False: nothing deletes an account yet, and an expired
account cannot open its documents to download them (read-only access after
the trial is agreed, not built). Announcing a deletion that does not happen,
or asking to download what cannot be reached, would be untrue.

Rules (next_email): days 0–59; the most recent due. The win-back emails
(ended, missing, why) respect the "stop these emails" link; the deletion
warnings, which concern the service itself, do not. Pacing across flows is
the job's (monitor_lifecycle.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta

FLOW = "expired_trial"
DELETE_AFTER_DAYS = 60
DELETION_ACTIVE = False
SCHEDULE = [("ended", 0), ("missing", 7), ("why", 21),
            ("deletion_warning", 45), ("last_warning", 55)]
DELETION_EMAILS = ("deletion_warning", "last_warning")


def days_since(ended_at: datetime, now: datetime) -> int:
    return (now - ended_at).days


def deletion_date(ended_at: datetime) -> datetime:
    return ended_at + timedelta(days=DELETE_AFTER_DAYS)


def next_email(day: int, sent: set[str], opted_out: bool = False,
               deletion_active: bool = DELETION_ACTIVE) -> str | None:
    if day < 0 or day >= DELETE_AFTER_DAYS:
        return None
    allowed = [(k, d) for k, d in SCHEDULE
               if (k in DELETION_EMAILS and deletion_active)
               or (k not in DELETION_EMAILS and not opted_out)]
    due = [k for k, d in allowed if d <= day]
    if not due or due[-1] in sent:
        return None
    return due[-1]


def missed_updates(sb, client: dict | None, since: datetime) -> tuple[int, int]:
    """(regulatory updates approved since `since`, of which for this company)."""
    total = sb.table("regulatory_updates").select("id", count="exact") \
        .eq("status", "approved").gte("approved_at", since.isoformat()).limit(1).execute().count or 0
    mine = 0
    if client:
        mine = sb.table("client_alerts").select("id", count="exact").eq("client_id", client["id"]) \
            .gte("notified_at", since.isoformat()).limit(1).execute().count or 0
    return total, mine
