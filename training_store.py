"""
training_store.py — S60 (D-159). Reading and writing the training register.

The I/O half of training_rules.py, which has none. Through the user's own
session (get_supabase), so RLS applies: has_client_access to read,
can_edit_client to write (read-only members are refused by the database).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from database import get_supabase, log_audit_event
import training_rules as TR


def load_requirements() -> list[dict]:
    """The global requirement definitions (reference data)."""
    try:
        rows = (get_supabase().table("reference_values").select("*")
                .eq("value_type", "training_requirement").eq("active", True)
                .is_("workspace_id", "null").order("sort_order")
                .execute().data or [])
        return [TR.requirement(r) for r in rows]
    except Exception as e:
        print(f"Could not load training requirements: {e}")
        return []


def load_employees(client_id: str) -> list[dict]:
    try:
        return (get_supabase().table("employees").select("*")
                .eq("client_id", client_id).order("name").execute().data or [])
    except Exception as e:
        print(f"Could not load employees: {e}")
        return []


def load_sessions(client_id: str) -> list[dict]:
    try:
        return (get_supabase().table("training_sessions").select("*")
                .eq("client_id", client_id).order("held_on", desc=True)
                .execute().data or [])
    except Exception as e:
        print(f"Could not load training sessions: {e}")
        return []


def load_attendance(client_id: str) -> list[dict]:
    try:
        return (get_supabase().table("training_attendance")
                .select("session_id, employee_id")
                .eq("client_id", client_id).execute().data or [])
    except Exception as e:
        print(f"Could not load attendance: {e}")
        return []


def load_all(client_id: str) -> dict[str, Any]:
    """Everything training_rules needs, read once."""
    return {
        "requirements": load_requirements(),
        "employees": load_employees(client_id),
        "sessions": load_sessions(client_id),
        "attendance": load_attendance(client_id),
    }


# ── Writes ────────────────────────────────────────────────────────────────

_EMP_FIELDS = ("name", "email", "job_title", "department", "handles_personal_data",
               "uses_ai", "management_body", "ai_overseer", "started_on", "left_on", "notes")
_SES_FIELDS = ("title", "requirement_codes", "held_on", "duration_minutes", "format",
               "provider", "trainer", "content", "valid_until")


def _clean(row: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    out = {}
    for k in fields:
        if k not in row:
            continue
        v = row[k]
        if isinstance(v, str):
            v = v.strip() or None
        elif isinstance(v, (date, datetime)):
            v = v.isoformat()
        out[k] = v
    return out


def save_employee(user_id: str, client_id: str, emp: dict[str, Any],
                  employee_id: str | None = None) -> str | None:
    fields = _clean(emp, _EMP_FIELDS)
    try:
        sb = get_supabase()
        if employee_id:
            sb.table("employees").update(
                {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", employee_id).execute()
            return employee_id
        res = sb.table("employees").insert(
            {**fields, "client_id": client_id, "user_id": user_id}).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as e:
        print(f"Could not save employee: {e}")
        return None


def save_employees(user_id: str, client_id: str, rows: list[dict[str, Any]]) -> int:
    """Bulk add (the paste-a-list form). Returns how many were added."""
    payload = [{**_clean(r, _EMP_FIELDS), "client_id": client_id, "user_id": user_id}
               for r in rows if (r.get("name") or "").strip()]
    if not payload:
        return 0
    try:
        res = get_supabase().table("employees").insert(payload).execute()
        n = len(res.data or [])
        log_audit_event(company_id=client_id, user_id=user_id, event_type="training",
                        event_subtype="people_added", summary=f"{n} people added to the training register")
        return n
    except Exception as e:
        print(f"Could not add employees: {e}")
        return 0


def delete_employee(user_id: str, client_id: str, employee_id: str) -> bool:
    """Removes the person and their attendance (the CASCADE). The page offers
    'left on' first, which keeps the record."""
    try:
        get_supabase().table("employees").delete().eq("id", employee_id).execute()
        log_audit_event(company_id=client_id, user_id=user_id, event_type="training",
                        event_subtype="person_deleted", resource_id=employee_id,
                        summary="A person and their training history were deleted")
        return True
    except Exception as e:
        print(f"Could not delete employee: {e}")
        return False


def save_session(user_id: str, client_id: str, session: dict[str, Any],
                 attendee_ids: list[str], session_id: str | None = None) -> str | None:
    """Create or update a session, and set exactly these attendees."""
    fields = _clean(session, _SES_FIELDS)
    try:
        sb = get_supabase()
        if session_id:
            sb.table("training_sessions").update(
                {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", session_id).execute()
            subtype = "session_updated"
        else:
            res = sb.table("training_sessions").insert(
                {**fields, "client_id": client_id, "user_id": user_id}).execute()
            session_id = (res.data or [{}])[0].get("id")
            subtype = "session_recorded"
        if not session_id:
            return None
        current = {r["employee_id"] for r in
                   (sb.table("training_attendance").select("employee_id")
                    .eq("session_id", session_id).execute().data or [])}
        wanted = set(attendee_ids)
        add = wanted - current
        drop = current - wanted
        if add:
            sb.table("training_attendance").insert([
                {"client_id": client_id, "session_id": session_id,
                 "employee_id": e, "user_id": user_id} for e in sorted(add)
            ]).execute()
        if drop:
            sb.table("training_attendance").delete().eq("session_id", session_id) \
                .in_("employee_id", sorted(drop)).execute()
        log_audit_event(company_id=client_id, user_id=user_id, event_type="training",
                        event_subtype=subtype, resource_id=session_id,
                        summary=f"Training session: {(fields.get('title') or '')[:80]} "
                                f"({len(wanted)} attendees)",
                        metadata={"requirements": fields.get("requirement_codes")})
        return session_id
    except Exception as e:
        print(f"Could not save training session: {e}")
        return None


def delete_session(user_id: str, client_id: str, session_id: str) -> bool:
    try:
        get_supabase().table("training_sessions").delete().eq("id", session_id).execute()
        log_audit_event(company_id=client_id, user_id=user_id, event_type="training",
                        event_subtype="session_deleted", resource_id=session_id,
                        summary="A training session was deleted")
        return True
    except Exception as e:
        print(f"Could not delete training session: {e}")
        return False


# ── For the register and the action plan ─────────────────────────────────

def open_findings(client: dict, data: dict[str, Any] | None = None) -> list[dict]:
    """The action-plan tasks for this client's training (tasks.py shape)."""
    try:
        d = data or load_all(client["id"])
        return TR.findings(client, d["requirements"], d["employees"],
                           d["sessions"], d["attendance"])
    except Exception as e:
        print(f"Training findings not loaded: {e}")
        return []
