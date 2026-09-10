"""
risk_store.py — S30. Supabase access for risk assessments and their registers.

The I/O half of risk_assessment.py, which has none. That module decides what
things mean; this one fetches and writes.

Same split as register.py / database.py and obligation_register.py /
obligation_store.py, for the same two reasons: the compliance logic stays
testable without a database, and moving off Supabase later rewrites this file
rather than the rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from database import get_supabase, log_audit_event


def load_assessments(
    client_id: str, user_id: str, regulation: str | None = None,
) -> list[dict[str, Any]]:
    """Assessments for a client, newest first."""
    try:
        q = (get_supabase().table("risk_assessments").select("*")
             .eq("client_id", client_id).eq("user_id", user_id))
        if regulation:
            q = q.eq("regulation", regulation)
        return q.order("created_at", desc=True).execute().data or []
    except Exception as e:
        print(f"Could not load assessments: {e}")
        return []


def load_items(assessment_id: str, user_id: str) -> list[dict[str, Any]]:
    try:
        return (get_supabase().table("risk_items").select("*")
                .eq("assessment_id", assessment_id).eq("user_id", user_id)
                .order("created_at").execute().data or [])
    except Exception as e:
        print(f"Could not load risk items: {e}")
        return []


def create_assessment(
    user_id: str, client_id: str, regulation: str, title: str,
    activity_ids: list[str] | None = None,
    system_ids: list[str] | None = None,
    scope_note: str | None = None,
) -> str | None:
    try:
        res = get_supabase().table("risk_assessments").insert({
            "user_id": user_id, "client_id": client_id,
            "regulation": regulation, "title": title,
            "activity_ids": activity_ids or [],
            "system_ids": system_ids or [],
            "scope_note": scope_note,
        }).execute()
        aid = (res.data or [{}])[0].get("id")
        if aid:
            log_audit_event(
                company_id=client_id, user_id=user_id,
                event_type="assessment", event_subtype="created",
                resource_id=aid,
                summary=f"{regulation} risk assessment started: {title}",
                metadata={"regulation": regulation},
            )
        return aid
    except Exception as e:
        print(f"Could not create assessment: {e}")
        return None


def save_item(
    user_id: str, client_id: str, assessment_id: str,
    item_id: str | None = None, **fields: Any,
) -> str | None:
    """Create or update one risk item. Only what is passed is written."""
    payload = {k: v for k, v in fields.items() if v is not None or k in (
        "likelihood", "severity", "residual_likelihood", "residual_severity",
    )}
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    # A name AND a date, or neither — the CHECK enforces it, and this is what
    # keeps the two in step when a client clears the name.
    if "accepted_by" in payload:
        who = (payload.get("accepted_by") or "").strip()
        payload["accepted_by"] = who or None
        payload["accepted_at"] = (
            datetime.now(timezone.utc).isoformat() if who else None
        )

    try:
        supabase = get_supabase()
        if item_id:
            supabase.table("risk_items").update(payload) \
                .eq("id", item_id).eq("user_id", user_id).execute()
            return item_id
        payload.update({
            "user_id": user_id, "client_id": client_id,
            "assessment_id": assessment_id,
        })
        res = supabase.table("risk_items").insert(payload).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as e:
        print(f"Could not save risk item: {e}")
        return None


def delete_item(item_id: str, user_id: str) -> bool:
    """Remove a risk item.

    Deletable, unlike an adopted document or a task event: a risk added by
    mistake is not a historical fact about the organisation, and an assessment
    cluttered with entries someone did not mean to add is one nobody rereads.
    """
    try:
        get_supabase().table("risk_items").delete() \
            .eq("id", item_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"Could not delete risk item: {e}")
        return False


def complete_assessment(
    assessment_id: str, user_id: str, client_id: str,
    consultation_required: bool,
) -> bool:
    """Mark an assessment complete, recording the Art. 36 position.

    `consultation_required` is DERIVED — risk_assessment.consultation_needed()
    over the items — never entered. It is the conclusion the whole document
    exists to reach, and a client should not be able to assert it either way.

    Audited with that conclusion in the metadata, because "we decided we did
    not need to consult" is exactly the decision an authority asks about
    afterwards.
    """
    try:
        get_supabase().table("risk_assessments").update({
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", assessment_id).eq("user_id", user_id).execute()

        log_audit_event(
            company_id=client_id, user_id=user_id,
            event_type="assessment", event_subtype="completed",
            resource_id=assessment_id,
            summary=(
                "Risk assessment completed — prior consultation required"
                if consultation_required
                else "Risk assessment completed"
            ),
            metadata={"art36_consultation_required": consultation_required},
        )
        return True
    except Exception as e:
        print(f"Could not complete assessment: {e}")
        return False


def set_dpo_advice(
    assessment_id: str, user_id: str, consulted: bool, advice: str | None,
) -> bool:
    """Art. 35(2): the controller shall seek the DPO's advice.

    Recorded as a tri-state — True, False, or never answered — because "we did
    not ask" and "we have not said whether we asked" are different, and the
    document says which.
    """
    try:
        get_supabase().table("risk_assessments").update({
            "dpo_consulted": consulted,
            "dpo_advice": (advice or "").strip() or None,
        }).eq("id", assessment_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"Could not record DPO advice: {e}")
        return False
