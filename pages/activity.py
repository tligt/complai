import streamlit as st
from datetime import datetime, timezone
from auth import get_user_id
from database import get_supabase, load_clients

# Timestamps are stored in UTC. Streamlit runs server-side, so there is no
# browser timezone to fall back on — the zone has to be chosen here.
#
# Brussels for everyone, for now. Correct for the current market and wrong the
# moment there is a client outside it, so this becomes a per-client setting
# rather than a constant when that happens. Named and labelled rather than
# silently applied: an auditor comparing this log against an email header needs
# to know which zone they are reading.
DISPLAY_TZ_NAME = "Europe/Brussels"

try:
    from zoneinfo import ZoneInfo
    DISPLAY_TZ = ZoneInfo(DISPLAY_TZ_NAME)
    TZ_LABEL = "Brussels time"
except Exception:
    # No tzdata on the image. UTC, said out loud — a mislabelled timestamp in
    # an audit log is worse than an honest one in the wrong zone.
    DISPLAY_TZ = timezone.utc
    TZ_LABEL = "UTC"


def _local(raw: str) -> str:
    """Render a stored timestamp in the display timezone."""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return str(raw)
    if dt.tzinfo is None:
        # Written before the offset fix: naive, and meant to be UTC. Assumed so
        # rather than dropped, which is the best available answer for rows
        # whose intended offset was never recorded.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ).strftime("%d %b %Y, %H:%M")

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
        # Matches the summary wording: "held 0 day(s)" is accurate and reads
        # like a defect.
        parts.append(
            "held the same day" if md["held_days"] == 0
            else f"held {md['held_days']} day(s)"
        )
    if md.get("supersedes_version"):
        parts.append(f"supersedes v{md['supersedes_version']}")
    if md.get("source_revision"):
        parts.append(f"template revision {md['source_revision']}")
    return " · ".join(parts)


st.title("Activity Log")
st.caption(f"A record of compliance actions taken on your account. All times in {TZ_LABEL}.")

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
            ts = _local(row["created_at"])
            icon = (
                SUBTYPE_ICONS.get(row.get("event_subtype"))
                or EVENT_ICONS.get(row["event_type"], "•")
            )
            st.markdown(f"{icon} **{row['summary']}** — {ts}")
            detail = _detail(row)
            if detail:
                st.caption(detail)
