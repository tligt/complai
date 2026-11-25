"""
trial_ending.py — D-213. The trial-ending email flow (flow 2 of the five
agreed on 25 Nov): takes over from onboarding (onboarding.py) at day 10.

    day 10   four_days   "4 days left": what they built, in figures; the plans
    day 13   last_day    "your trial ends tomorrow": everything is kept

Rules (next_email): only while the trial runs (days 10–13); the most recent
due, so a late start does not get both on consecutive days. The pacing
across flows (none within 20 h of the last lifecycle email) is the job's:
monitor_lifecycle.py.

Pure parts are tested by test_lifecycle.py.
"""

from __future__ import annotations

FLOW = "trial_ending"
SCHEDULE = [("four_days", 10), ("last_day", 13)]
FLOW_START_DAY, FLOW_END_DAY = 10, 14


def next_email(day: int, sent: set[str]) -> str | None:
    if day < FLOW_START_DAY or day >= FLOW_END_DAY:
        return None
    due = [k for k, d in SCHEDULE if d <= day and k not in sent]
    return due[-1] if due else None


def figures(sb, client: dict | None) -> dict[str, int | None]:
    """What the company built during its trial, for the day-10 email."""
    out = {"systems": 0, "activities": 0, "documents": 0, "score": None, "alerts": 0}
    if not client:
        return out
    cid = client["id"]

    def _count(table: str, **eq) -> int:
        q = sb.table(table).select("id", count="exact").eq("client_id", cid)
        for k, v in eq.items():
            q = q.in_(k, v) if isinstance(v, list) else q.eq(k, v)
        return q.limit(1).execute().count or 0

    out["systems"] = _count("systems")
    out["activities"] = _count("processing_activities")
    docs = sb.table("client_documents").select("document_type").eq("client_id", cid) \
        .in_("status", ["draft", "in_force"]).execute().data or []
    gen = sb.table("documents").select("document_type").eq("client_id", cid).execute().data or []
    out["documents"] = len({d["document_type"] for d in docs + gen if d.get("document_type")})
    gap = sb.table("gap_assessments").select("score_overall").eq("client_id", cid) \
        .order("created_at", desc=True).limit(1).execute().data
    out["score"] = gap[0].get("score_overall") if gap else None
    out["alerts"] = _count("client_alerts")
    return out
