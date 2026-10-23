"""
incident_store.py — S53. Reading and writing incidents and their timeline.

Through the user's own session (get_supabase), so RLS applies:
has_client_access(client_id, ...) — owners and workspace members (S38).
Incidents are updated as the assessment fills in but never deleted; the
timeline is append-only (migration_s53_incidents.sql).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from database import get_supabase, log_audit_event


def load_incidents(client_id: str) -> list[dict]:
    try:
        return (get_supabase().table("incidents").select("*")
                .eq("client_id", client_id).order("discovered_at", desc=True)
                .execute().data or [])
    except Exception as e:
        print(f"Could not load incidents: {e}")
        return []


def load_events(client_id: str, incident_ids: list[str] | None = None) -> dict[str, list[dict]]:
    """{incident_id: [event, ...]} oldest first."""
    try:
        q = get_supabase().table("incident_events").select("*").eq("client_id", client_id)
        if incident_ids is not None:
            if not incident_ids:
                return {}
            q = q.in_("incident_id", incident_ids)
        rows = q.order("occurred_at").execute().data or []
    except Exception as e:
        print(f"Could not load incident events: {e}")
        return {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["incident_id"], []).append(r)
    return out


def create_incident(user_id: str, client_id: str, *, title: str, description: str,
                    discovered_at: datetime, reported_by: str,
                    system_ids: list[str]) -> dict | None:
    try:
        row = get_supabase().table("incidents").insert({
            "user_id": user_id, "client_id": client_id,
            "title": title.strip()[:200], "description": description.strip() or None,
            "discovered_at": discovered_at.astimezone(timezone.utc).isoformat(),
            "reported_by": reported_by.strip() or None,
            "system_ids": system_ids,
        }).execute().data[0]
        log_audit_event(
            company_id=client_id, user_id=user_id, event_type="incident",
            event_subtype="opened", resource_id=row["id"],
            summary=f"Incident opened: {row['title'][:80]}",
            metadata={"discovered_at": row["discovered_at"]},
        )
        return row
    except Exception as e:
        print(f"Could not create incident: {e}")
        return None


def update_incident(incident_id: str, changes: dict[str, Any]) -> bool:
    try:
        get_supabase().table("incidents").update(
            {**changes, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", incident_id).execute()
        return True
    except Exception as e:
        print(f"Could not update incident: {e}")
        return False


def add_event(user_id: str, incident: dict, event_type: str, *, kind: str | None = None,
              occurred_at: datetime | None = None, reference: str | None = None,
              body: str | None = None) -> bool:
    try:
        get_supabase().table("incident_events").insert({
            "incident_id": incident["id"], "client_id": incident["client_id"],
            "user_id": user_id, "event_type": event_type, "kind": kind,
            "occurred_at": (occurred_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
            "reference": (reference or "").strip() or None,
            "body": (body or "").strip() or None,
        }).execute()
        if event_type in ("notification", "status", "followup", "alert"):
            log_audit_event(
                company_id=incident["client_id"], user_id=user_id, event_type="incident",
                event_subtype=f"{event_type}:{kind}" if kind else event_type,
                resource_id=incident["id"],
                summary=f"Incident {event_type}: {kind or body or ''}"[:120],
                metadata={"reference": reference},
            )
        return True
    except Exception as e:
        print(f"Could not record incident event: {e}")
        return False


def processor_context(user_id: str, client_id: str) -> dict[str, list[dict]]:
    """What incident_rules.affected_controllers needs, read once per page."""
    import inventory_store as INVS
    try:
        sb = get_supabase()
        activity_systems = (sb.table("activity_systems").select("activity_id, system_id")
                            .eq("client_id", client_id).execute().data or [])
    except Exception:
        activity_systems = []
    return {
        "activities": INVS.load_activities(user_id, client_id),
        "activity_systems": activity_systems,
        "activity_counterparties": INVS.load_counterparty_links(user_id, client_id),
        "counterparties": INVS.load_counterparties(user_id, client_id),
    }


def load_jurisdiction(code: str | None) -> dict:
    """The country's metadata: authorities and reporting channels (D-83)."""
    try:
        rows = (get_supabase().table("reference_values").select("metadata")
                .eq("value_type", "jurisdiction").eq("code", code or "BE")
                .execute().data or [])
        return (rows[0].get("metadata") or {}) if rows else {}
    except Exception as e:
        print(f"Could not load jurisdiction: {e}")
        return {}


def open_findings(user_id: str, client: dict) -> list[dict]:
    """The action-plan tasks for this client's open incidents (tasks.py
    shape), for the Obligations page and the Dashboard banner."""
    import incident_rules as R
    incidents = [i for i in load_incidents(client["id"]) if i["status"] != "closed"]
    if not incidents:
        return []
    events = load_events(client["id"], [i["id"] for i in incidents])
    ctx = processor_context(user_id, client["id"])
    processor = {i["id"]: bool(R.affected_controllers(i.get("system_ids") or [], **ctx))
                 for i in incidents}
    return R.findings(incidents, client, events, processor,
                      contacts=load_contacts(client["id"]))


# ── The incident team (S53 part 2, D-118) ────────────────────────────────

def load_contacts(client_id: str, include_inactive: bool = False) -> list[dict]:
    try:
        q = get_supabase().table("incident_contacts").select("*").eq("client_id", client_id)
        if not include_inactive:
            q = q.eq("active", True)
        return q.order("sort_order").order("name").execute().data or []
    except Exception as e:
        print(f"Could not load the incident team: {e}")
        return []


def save_contact(user_id: str, client_id: str, contact: dict[str, Any],
                 contact_id: str | None = None) -> bool:
    """Create, or update when contact_id is given. No delete: a contact is
    deactivated, so past alerts still name them."""
    fields = {k: contact.get(k) for k in
              ("name", "role", "email", "phone", "alert_on", "deadline_hours", "notes",
               "sort_order", "active") if k in contact}
    try:
        if contact_id:
            get_supabase().table("incident_contacts").update(
                {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", contact_id).execute()
        else:
            get_supabase().table("incident_contacts").insert(
                {**fields, "client_id": client_id, "user_id": user_id}
            ).execute()
        return True
    except Exception as e:
        print(f"Could not save the team member: {e}")
        return False


def alert_team(user_id: str, incident: dict, client: dict, targets: list[dict],
               reason: str) -> list[dict]:
    """Email the incident alert to these team members and record who was
    told, when, and why. Returns the members actually emailed."""
    if not targets:
        return []
    from email_sender import send_incident_alert
    try:
        ok = send_incident_alert(
            [t["email"] for t in targets], client.get("company_name") or "",
            incident["title"], incident.get("discovered_at"), reason,
        )
    except Exception as e:
        print(f"Incident alert failed: {e}")
        ok = False
    if not ok:
        return []
    add_event(user_id, incident, "alert", kind=reason,
              reference=",".join(t["id"] for t in targets),
              body="; ".join(f"{t['name']} <{t['email']}>" for t in targets))
    return targets
