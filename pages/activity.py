import streamlit as st
from datetime import datetime
from auth import get_user_id
from database import get_supabase, load_clients

# Keyed on event_type, with subtypes overriding where the distinction matters.
# S27 writes everything under event_type "document", which had no entry here at
# all — so adoptions, archivings, discards and legal holds all rendered as a
# bullet with no icon.
EVENT_ICONS = {
    "document_generated": "📄",
    "gap_assessment_run": "📊",
    "audit_run": "🔍",
    "document": "📄",
}

SUBTYPE_ICONS = {
    "adopted":       "✅",
    "archived":      "📁",
    "draft_deleted": "🗑️",
    "hold_set":      "🔒",
    "hold_released": "🔓",
}


def _detail(row: dict) -> str:
    """The reason behind an event, where one was recorded.

    Reasons live in metadata rather than in the summary, so a log that renders
    only the summary shows that something happened and never why. For a legal
    hold that is the whole of the interesting part: releasing a hold is what
    allows a document to be deleted, and the release reason exists ONLY here —
    hold_reason is cleared from the document row on release, because a released
    hold is no longer a property of the document but a decision someone made.
    """
    md = row.get("metadata") or {}
    if not isinstance(md, dict):
        return ""

    parts = []
    if md.get("reason"):
        parts.append(str(md["reason"]))
    # On a release, carry the reason the hold was originally placed so the two
    # read as one story rather than as an unexplained reversal.
    if md.get("hold_reason_at_release"):
        parts.append(f"placed for: {md['hold_reason_at_release']}")
    if md.get("held_days") is not None:
        parts.append(f"held {md['held_days']} day(s)")
    if md.get("supersedes_version"):
        parts.append(f"supersedes v{md['supersedes_version']}")
    if md.get("source_revision"):
        parts.append(f"template revision {md['source_revision']}")
    return " · ".join(parts)


st.title("Activity Log")
st.caption("A record of compliance actions taken on your account.")

user_id = get_user_id()
clients = load_clients(user_id)

# Single-owner model until S38 (Advisory multi-client workspace) — one client per user
client_id = clients[0]["id"] if clients else None

if not client_id:
    st.info("No client profile found yet.")
else:
    supabase = get_supabase()
    try:
        rows = (
            supabase.table("audit_log")
            .select("*")
            .eq("company_id", client_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
    except Exception as e:
        st.error(f"Could not load activity log: {e}")
        rows = []

    if not rows:
        st.info("No activity recorded yet.")
    else:
        for row in rows:
            ts = datetime.fromisoformat(
                row["created_at"].replace("Z", "+00:00")
            ).strftime("%d %b %Y, %H:%M")
            icon = (
                SUBTYPE_ICONS.get(row.get("event_subtype"))
                or EVENT_ICONS.get(row["event_type"], "•")
            )
            st.markdown(f"{icon} **{row['summary']}** — {ts}")
            detail = _detail(row)
            if detail:
                st.caption(detail)
