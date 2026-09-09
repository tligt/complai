"""
obligation_store.py — S29. Supabase access for the obligation and task
registers.

The I/O half of obligation_register.py and tasks.py, which have none. Those two
decide what things mean; this one fetches and writes.

Same split as register.py / database.py in S27, and for the same two reasons:
the compliance logic stays testable without a database, and moving off
Streamlit or Supabase later is a rewrite of this file rather than of the rules.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

from database import get_supabase, log_audit_event


# ── Obligation responses ──────────────────────────────────────────────────

def load_responses(client_id: str, user_id: str) -> dict[str, dict[str, Any]]:
    """{obligation_id: row} for one client. Absent means nothing recorded."""
    try:
        rows = (get_supabase().table("obligation_responses").select("*")
                .eq("client_id", client_id).eq("user_id", user_id)
                .execute().data or [])
        return {r["obligation_id"]: r for r in rows}
    except Exception as e:
        print(f"Could not load obligation responses: {e}")
        return {}


def save_response(
    user_id: str,
    client_id: str,
    obligation_id: str,
    *,
    status: str | None = None,
    statement_en: str | None = None,
    evidence_path: str | None = None,
    evidence_filename: str | None = None,
    acknowledged_by: str | None = None,
    review_due: date | None = None,
    not_applicable_reason: str | None = None,
) -> bool:
    """Create or update one response. Only what is passed is written.

    Upsert on (client_id, obligation_id), which is a plain UNIQUE index and can
    therefore serve as an ON CONFLICT arbiter — unlike the partial index in
    S27, which could not (42P10) and forced an explicit two-step transition.
    """
    try:
        supabase = get_supabase()
        before = (supabase.table("obligation_responses").select("*")
                  .eq("client_id", client_id)
                  .eq("obligation_id", obligation_id)
                  .execute().data or [None])[0]

        payload: dict[str, Any] = {
            "user_id": user_id,
            "client_id": client_id,
            "obligation_id": obligation_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if status is not None:
            payload["status"] = status
            # Recording an answer IS reviewing it. Without this, review_due
            # would be the only thing that ever moved reviewed_at, and an
            # obligation someone updated last week would show as never
            # reviewed.
            payload["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        if statement_en is not None:
            existing = (before or {}).get("statement_i18n") or {}
            payload["statement_i18n"] = {**existing, "en": statement_en}
        if evidence_path is not None:
            payload["evidence_path"] = evidence_path
            payload["evidence_filename"] = evidence_filename
        if acknowledged_by is not None:
            # A name AND a date, or neither — the CHECK constraint enforces it.
            # An unattributed tick is not evidence of anything.
            payload["acknowledged_by"] = acknowledged_by or None
            payload["acknowledged_at"] = (
                datetime.now(timezone.utc).isoformat() if acknowledged_by else None
            )
        if review_due is not None:
            payload["review_due"] = review_due.isoformat()
        if not_applicable_reason is not None:
            payload["not_applicable_reason"] = not_applicable_reason or None

        supabase.table("obligation_responses").upsert(
            payload, on_conflict="client_id,obligation_id"
        ).execute()

        # Only when something changed. An audit trail that records every page
        # save is one nobody reads.
        if (before or {}).get("status") != payload.get("status", (before or {}).get("status")):
            log_audit_event(
                company_id=client_id, user_id=user_id,
                event_type="obligation", event_subtype="status_changed",
                resource_id=obligation_id,
                summary=(
                    f"{obligation_id}: "
                    f"{(before or {}).get('status') or 'not recorded'} → "
                    f"{payload.get('status')}"
                ),
                metadata={
                    "obligation_id": obligation_id,
                    "from": (before or {}).get("status"),
                    "to": payload.get("status"),
                    "reason": not_applicable_reason,
                },
            )
        return True
    except Exception as e:
        print(f"Could not save obligation response: {e}")
        return False


# ── Task history ──────────────────────────────────────────────────────────

def load_events(client_id: str, user_id: str, limit: int = 2000) -> list[dict]:
    """Every task event for a client. Ordered oldest first.

    The whole history, not a page of it: tasks.apply_history and
    tasks.closures both need to know the LATEST event per finding, and a
    truncated read would silently produce wrong answers rather than fewer.
    The limit is a safety valve, not a paging mechanism.
    """
    try:
        return (get_supabase().table("task_events").select("*")
                .eq("client_id", client_id).eq("user_id", user_id)
                .order("created_at").limit(limit)
                .execute().data or [])
    except Exception as e:
        print(f"Could not load task events: {e}")
        return []


def record_events(
    user_id: str, client_id: str, events: Iterable[Mapping[str, Any]],
) -> int:
    """Append events. Returns how many were written.

    Never updates: task_events is a history and has no UPDATE policy. An event
    written in error is corrected by writing another, the same way a ledger is.
    """
    rows = [
        {
            "user_id": user_id,
            "client_id": client_id,
            "producer": e["producer"],
            "finding_key": e["finding_key"],
            "event": e["event"],
            "actor": e.get("actor"),
            "note": e.get("note"),
        }
        for e in events
    ]
    if not rows:
        return 0
    try:
        get_supabase().table("task_events").insert(rows).execute()
        return len(rows)
    except Exception as e:
        print(f"Could not record task events: {e}")
        return 0


def reconcile(
    user_id: str, client_id: str,
    findings: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[int, int]:
    """Write the opened and closed events implied by the current findings.

    Called on every read of the task register. Idempotent by construction:
    tasks.openings only returns findings with no open event, and
    tasks.closures only returns keys that were open and are no longer
    reported, so a second call in the same state writes nothing.

    THIS IS WHAT MAKES THE HISTORY TRUE without anything reconciling state.
    The producer stopping IS the closure. Recording it here is the only durable
    trace that the work happened at all — the task itself leaves nothing
    behind, because it was never stored.

    Returns (opened, closed).
    """
    import tasks as T  # noqa: PLC0415

    to_open = [
        {"producer": f["producer"], "finding_key": f["finding_key"],
         "event": "opened"}
        for f in T.openings(findings, events)
    ]
    by_key = {f["finding_key"]: f for f in findings}
    to_close = [
        {"producer": (by_key.get(k) or {}).get("producer") or k.split(":", 1)[0],
         "finding_key": k, "event": "closed"}
        for k in T.closures(findings, events)
    ]
    return (
        record_events(user_id, client_id, to_open),
        record_events(user_id, client_id, to_close),
    )


def dismiss(
    user_id: str, client_id: str, producer: str, finding_key: str, note: str,
) -> bool:
    """Dismiss a finding. A reason is required — the CHECK enforces it.

    The dismissal holds only while the finding is CONTINUOUSLY reported. If it
    disappears and returns, tasks.apply_history will not carry it over: the
    situation changed, and a decision about the old finding should not silently
    apply to the new one.
    """
    if not (note or "").strip():
        return False
    return record_events(user_id, client_id, [{
        "producer": producer, "finding_key": finding_key,
        "event": "dismissed", "actor": user_id, "note": note.strip(),
    }]) == 1
