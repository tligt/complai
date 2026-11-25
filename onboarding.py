"""
onboarding.py — D-212. The onboarding email flow (flow 1 of the five agreed
on 25 Nov), and the five setup steps it follows, shared with Home's guide.

The flow runs during the trial's first 10 days (trial ending, flow 2, takes
over at day 10). Days count from the trial's start (its end minus TRIAL_DAYS).

    day 0   welcome    first step: the company profile
    day 1   personal   plain text from Fabrice: "what do you need it for?"
    day 2   step_a  ┐
    day 4   step_b  ├  the first setup step not done yet
    day 6   step_c  ┘
    day 8   wrapup     "you're set up" (5 of 5), or "3 of 5 done, 2 to go"

Rules (next_email):
- one email per run, and none within MIN_GAP of the last one;
- the welcome always goes first;
- otherwise the most recent email that is due — an older one that was missed
  (a trial started late, a job that did not run) is passed over, not sent
  days late in a row;
- all five steps done: the step emails are skipped and the wrap-up ("you're
  set up") goes at the next slot from day 2.

Pure parts here are tested by test_onboarding.py; monitor_onboarding.py
loads the data and sends.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

FLOW = "onboarding"
FLOW_END_DAY = 10
MIN_GAP = timedelta(hours=20)

# (key, day): the order is the order they go out.
SCHEDULE = [("welcome", 0), ("personal", 1), ("step_a", 2), ("step_b", 4),
            ("step_c", 6), ("wrapup", 8)]
STEP_EMAILS = ("step_a", "step_b", "step_c")

# The five setup steps, in the order the product works (each feeds the next).
# Home's guide (app_pages/dashboard.py) shows the same five.
# key: (label, page file, url path, one-line description)
STEPS = {
    "profile":   ("Complete the company profile", "app_pages/company.py", "company",
                  "Legal name and a contact email are what documents need most."),
    "inventory": ("Add your systems and activities", "app_pages/inventory.py", "inventory",
                  "The tools you use and what you do with personal data. Start with a scan "
                  "of your website."),
    "gap":       ("Run a gap assessment", "app_pages/gap.py", "gap",
                  "A first score per regulation, and findings for the action plan."),
    "documents": ("Generate your documents", "app_pages/documents.py", "documents",
                  "Privacy policy, register of processing, and the rest your regulations require."),
    "adopt":     ("Adopt them (mark in force)", "app_pages/compliance_record.py", "compliance_record",
                  "A document counts once your company operates under it."),
}
STEP_ORDER = list(STEPS)


# ── Pure ──────────────────────────────────────────────────────────────────

def trial_day(trial_ends_at: datetime, now: datetime, trial_days: int = 14) -> int:
    """Whole days since the trial started (0 on the first day)."""
    return (now - (trial_ends_at - timedelta(days=trial_days))).days


def first_pending(done: dict[str, bool]) -> str | None:
    return next((k for k in STEP_ORDER if not done.get(k)), None)


def next_email(day: int, sent: dict[str, datetime], now: datetime,
               all_done: bool) -> str | None:
    """The onboarding email to send now, or None. `sent`: key → when."""
    if day < 0 or day >= FLOW_END_DAY:
        return None
    if sent and now - max(sent.values()) < MIN_GAP:
        return None
    if "welcome" not in sent:
        return "welcome"
    if all_done:
        return "wrapup" if "wrapup" not in sent and day >= 2 else None
    due = [k for k, d in SCHEDULE if d <= day and k not in sent]
    return due[-1] if due else None


# ── The stop link ─────────────────────────────────────────────────────────
# Signed, so it works without logging in and cannot be forged for someone
# else. Keyed on the service key, which only the server has.

def _secret() -> bytes:
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY") or ""
    return hmac.new(key.encode(), b"recosa-lifecycle-stop", hashlib.sha256).digest()


def stop_token(user_id: str) -> str:
    sig = hmac.new(_secret(), user_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{sig}"


def user_from_stop_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    user_id, sig = token.rsplit(".", 1)
    good = hmac.new(_secret(), user_id.encode(), hashlib.sha256).hexdigest()[:32]
    return user_id if hmac.compare_digest(sig, good) else None


# ── Data (service role) ───────────────────────────────────────────────────

def step_status(sb, client: dict | None) -> dict[str, bool]:
    """The five steps for a company, as Home works them out. No company yet:
    nothing is done."""
    if not client:
        return {k: False for k in STEP_ORDER}
    cid = client["id"]

    def _any(table: str, **eq) -> bool:
        q = sb.table(table).select("id").eq("client_id", cid)
        for k, v in eq.items():
            q = q.in_(k, v) if isinstance(v, list) else q.eq(k, v)
        return bool(q.limit(1).execute().data)

    in_force = _any("client_documents", status="in_force")
    return {
        "profile": bool(client.get("contact_email") and client.get("legal_name")),
        "inventory": _any("systems") and _any("processing_activities"),
        "gap": _any("gap_assessments"),
        "documents": in_force or _any("documents") or _any("client_documents",
                                                            status=["draft", "in_force"]),
        "adopt": in_force,
    }
