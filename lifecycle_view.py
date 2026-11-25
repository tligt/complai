"""
lifecycle_view.py — D-216. Where each account is in its lifecycle, for the
back office's Lifecycle page (pages_admin/lifecycle.py). Pure parts tested by
test_lifecycle_view.py; load() reads the database (service role).

Stages, and the day each account is on in its stage:

    registered   signed up, no trial yet (accounts from before D-211)
    trial        day since the trial started (0–13)
    dropout      trial ended without a plan: day since the end (0–59, then deleted)
    customer     paying or on a voucher: day since it became active
    churned      cancelled after paying: day since it was cancelled (0–119)

The emails on each lane come from the flows' own schedules, so the page
shows what the job really sends.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import expired_trial as ET
import onboarding as OB
import trial_ending as TE

TRIAL_DAYS = 14

STAGES = {
    "registered": "Trial not started",
    "trial": "Trial",
    "customer": "Customer",
    "dropout": "Drop-out",
    "churned": "Churned",
}

# Each lane: its length in days, and its emails as (day, label, flow, live).
LANES = {
    "trial": (TRIAL_DAYS, [(d, k, OB.FLOW, True) for k, d in OB.SCHEDULE]
              + [(d, k, TE.FLOW, True) for k, d in TE.SCHEDULE]),
    "dropout": (ET.DELETE_AFTER_DAYS, [(d, k, ET.FLOW, ET.DELETION_ACTIVE or k not in ET.DELETION_EMAILS)
                                       for k, d in ET.SCHEDULE]),
    "churned": (120, [(0, "read_only", "churned", False), (30, "since_you_left", "churned", False),
                      (60, "since_you_left_2", "churned", False), (90, "deletion_warning", "churned", False),
                      (113, "last_warning", "churned", False)]),
    "customer": (30, []),
}


def _ts(v):
    if not v:
        return None
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def stage_of(acc: dict | None, now: datetime, since: datetime | None = None) -> tuple[str, int | None]:
    """(stage, day in it). `acc` None: a person who signed up and has no
    account yet. `since`: when the current status began (the open period)."""
    if not acc:
        return "registered", None
    status = acc.get("status")
    ends = _ts(acc.get("trial_ends_at"))
    if status == "trial" and ends:
        if ends > now:
            return "trial", max(0, (now - (ends - timedelta(days=TRIAL_DAYS))).days)
        return "dropout", (now - ends).days
    if status == "expired":
        return "dropout", (now - ends).days if ends else None
    if status == "active":
        return "customer", (now - since).days if since else None
    if status == "cancelled":
        return "churned", (now - since).days if since else None
    return "registered", None


def next_planned(stage: str, day: int | None, sent: set[str]) -> tuple[int, str] | None:
    """The next email the lane plans for this account (its day and name), or
    None. Like the job: an email due and not sent goes first (the most recent
    due — older missed ones are passed over); else the next one ahead. The
    job also paces them 20 h apart."""
    if day is None or stage not in LANES:
        return None
    if stage == "trial" and day < OB.FLOW_END_DAY and "welcome" not in sent:
        return 0, "welcome"                      # the job always sends it first
    live = sorted((d, k) for d, k, _f, on in LANES[stage][1] if on)
    due = [(d, k) for d, k in live if d <= day]
    if due and due[-1][1] not in sent:
        return due[-1]
    ahead = [(d, k) for d, k in live if d > day and k not in sent]
    return ahead[0] if ahead else None


# ── Data ──────────────────────────────────────────────────────────────────

def load(sb, include_internal: bool = False) -> list[dict]:
    """One row per account (and per sign-up with no account yet)."""
    now = datetime.now(timezone.utc)
    accounts = sb.table("accounts").select("*").execute().data or []
    profiles = {p["id"]: p for p in sb.table("profiles").select(
        "id, email, role, signup_source, created_at, lifecycle_emails_off_at, ui_language")
        .execute().data or []}
    clients = sb.table("clients").select("id, account_id, company_name, created_at") \
        .order("created_at").execute().data or []
    emails = sb.table("lifecycle_emails").select("account_id, flow, email_key, detail, sent_at") \
        .order("sent_at").execute().data or []
    periods = sb.table("account_periods").select("account_id, status, starts_at, ends_at, note") \
        .order("starts_at").execute().data or []

    company_by_acc: dict[str, dict] = {}
    for c in clients:
        company_by_acc.setdefault(c.get("account_id"), c)
    emails_by_acc: dict[str, list] = {}
    for e in emails:
        emails_by_acc.setdefault(e["account_id"], []).append(e)
    open_period = {p["account_id"]: p for p in periods if not p.get("ends_at")}

    rows = []
    owners = set()
    for acc in accounts:
        owner = profiles.get(acc.get("owner_user_id")) or {}
        owners.add(acc.get("owner_user_id"))
        internal = owner.get("role") == "admin" or owner.get("signup_source") == "test"
        if internal and not include_internal:
            continue
        since = _ts((open_period.get(acc["id"]) or {}).get("starts_at"))
        stage, day = stage_of(acc, now, since)
        sent = emails_by_acc.get(acc["id"], [])
        company = company_by_acc.get(acc["id"])
        rows.append({
            "id": acc["id"], "account": acc, "owner": owner, "company": company,
            "name": (company or {}).get("company_name") or acc.get("name") or owner.get("email") or "—",
            "stage": stage, "day": day, "internal": internal,
            "emails": sent, "opted_out": owner.get("lifecycle_emails_off_at"),
            "next": next_planned(stage, day, {e["email_key"] for e in sent}),
        })
    # Signed up, never got an account (free check sign-ups before D-211).
    for pid, p in profiles.items():
        if pid in owners or p.get("signup_source") == "invite":
            continue
        internal = p.get("role") == "admin" or p.get("signup_source") == "test"
        if internal and not include_internal:
            continue
        rows.append({"id": f"profile:{pid}", "account": None, "owner": p, "company": None,
                     "name": p.get("email") or "—", "stage": "registered", "day": None,
                     "internal": internal, "emails": [], "opted_out": p.get("lifecycle_emails_off_at"),
                     "next": None})
    return rows


def history(sb, row: dict) -> list[tuple[datetime, str]]:
    """What happened to one account, oldest first."""
    out = []
    owner = row.get("owner") or {}
    if owner.get("created_at"):
        out.append((_ts(owner["created_at"]),
                    f"Signed up ({owner.get('signup_source') or 'direct'})"))
    if row.get("company"):
        out.append((_ts(row["company"]["created_at"]), f"Company created: {row['company']['company_name']}"))
    acc = row.get("account")
    if acc:
        for p in sb.table("account_periods").select("status, plan, starts_at, note, trial_ends_at") \
                .eq("account_id", acc["id"]).order("starts_at").execute().data or []:
            label = f"Status: {p['status']} ({p.get('plan')})"
            if p.get("trial_ends_at"):
                label += f", trial until {_ts(p['trial_ends_at']):%d %b %Y}"
            if p.get("note"):
                label += f" — {p['note']}"
            out.append((_ts(p["starts_at"]), label))
    for e in row.get("emails") or []:
        out.append((_ts(e["sent_at"]), f"Email sent: {e['flow']} / {e['email_key']}"
                    + (f" ({e['detail']})" if e.get("detail") else "")))
    if row.get("opted_out"):
        out.append((_ts(row["opted_out"]), "Used the \"stop these emails\" link"))
    if owner.get("id"):
        s = sb.table("app_sessions").select("created_at").eq("user_id", owner["id"]) \
            .order("created_at", desc=True).limit(1).execute().data
        if s:
            out.append((_ts(s[0]["created_at"]), "Last sign-in"))
    return sorted([x for x in out if x[0]], key=lambda x: x[0])


def prospects(sb, days: int = 30) -> dict[str, int]:
    """Free-check visits in the last `days` days, by how far they got."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = sb.table("funnel_events").select("event, visit").gte("created_at", since) \
        .in_("event", ["check_landing", "scope_completed", "results_viewed", "signup"]) \
        .execute().data or []
    out = {}
    for ev in ("check_landing", "scope_completed", "results_viewed", "signup"):
        visits = {r.get("visit") for r in rows if r["event"] == ev}
        visits.discard(None)
        out[ev] = len(visits) or sum(1 for r in rows if r["event"] == ev)
    return out
