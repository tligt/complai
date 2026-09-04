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

EVENT_LABELS = {
    "document_generated": "Document generated",
    "gap_assessment_run": "Gap assessment",
    "audit_run":          "Website audit",
    "document":           "Document",
}

SUBTYPE_LABELS = {
    "adopted":       "Put in force",
    "archived":      "Archived",
    "draft_deleted": "Draft discarded",
    "hold_set":      "Legal hold placed",
    "hold_released": "Legal hold released",
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
st.caption(
    "A record of compliance actions taken on your account. "
    f"All times in {TZ_LABEL}."
)

user_id = get_user_id()
clients = load_clients(user_id)

# Single-owner model until S38 (Advisory multi-client workspace) — one client per user
client_id = clients[0]["id"] if clients else None

if not client_id:
    st.info("No client profile found yet.")
    st.stop()

supabase = get_supabase()
try:
    rows = (
        supabase.table("audit_log")
        .select("*")
        .eq("company_id", client_id)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
        .data
    ) or []
except Exception as e:
    st.error(f"Could not load activity log: {e}")
    rows = []

if not rows:
    st.info("No activity recorded yet.")
    st.stop()


def _action(row: dict) -> str:
    """A readable name for what happened.

    audit_log stores event_type and event_subtype, which are internal codes.
    A client reading their own compliance history should not have to know that
    "document / hold_released" means a legal hold was lifted.
    """
    sub = row.get("event_subtype")
    if sub:
        return SUBTYPE_LABELS.get(sub, sub.replace("_", " ").capitalize())
    return EVENT_LABELS.get(
        row.get("event_type", ""),
        str(row.get("event_type", "")).replace("_", " ").capitalize(),
    )


# ── Filters ───────────────────────────────────────────────────────────────
# A register that only scrolls is one nobody checks a specific thing in. An
# auditor arrives with a question — what happened to the DPA, who released
# that hold — not to read 200 rows in order.
actions = sorted({_action(r) for r in rows})
f1, f2 = st.columns([2, 3])
chosen = f1.multiselect("Action", actions, default=[], placeholder="All actions")
search = f2.text_input("Search", placeholder="Document name, reason, version…")

filtered = [
    r for r in rows
    if (not chosen or _action(r) in chosen)
    and (
        not search
        or search.lower() in (
            f"{r.get('summary', '')} {_detail(r)} {_action(r)}".lower()
        )
    )
]

table = [
    {
        "": (
            SUBTYPE_ICONS.get(r.get("event_subtype"))
            or EVENT_ICONS.get(r.get("event_type", ""), "•")
        ),
        "When": _local(r["created_at"]),
        "Action": _action(r),
        "What": r.get("summary", ""),
        # Reasons live in metadata, which is why a log rendering only the
        # summary showed that something happened and never why. For a legal
        # hold that is the interesting half: releasing one is what allows the
        # document to be deleted.
        "Details": _detail(r),
    }
    for r in filtered
]

st.caption(
    f"{len(filtered)} of {len(rows)} events"
    + (" — filtered" if len(filtered) != len(rows) else "")
)

st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    column_config={
        "": st.column_config.TextColumn(width="small"),
        "When": st.column_config.TextColumn(width="small"),
        "Action": st.column_config.TextColumn(width="small"),
        "What": st.column_config.TextColumn(width="large"),
        "Details": st.column_config.TextColumn(width="medium"),
    },
)

# The log is evidence, and evidence gets handed over. A client asked for their
# activity history by an auditor should not be screenshotting a table.
import csv
import io

_buf = io.StringIO()
_w = csv.DictWriter(_buf, fieldnames=["When", "Action", "What", "Details"])
_w.writeheader()
for _r in table:
    _w.writerow({k: _r[k] for k in ("When", "Action", "What", "Details")})

st.download_button(
    "Download as CSV",
    _buf.getvalue().encode("utf-8"),
    file_name=f"RECOSA_activity_log_{datetime.now(DISPLAY_TZ).strftime('%Y%m%d')}.csv",
    mime="text/csv",
)
