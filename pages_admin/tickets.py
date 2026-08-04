"""
RECOSA — Support tickets (admin BO).

No auth guard here by design: admin_app.py handles auth at the app level,
and pages in pages_admin/ must not carry their own guards.

Severity vs priority: severity is impact (seeded from what the client
reported, overridable), priority is queue order. They start correlated and
deliberately diverge — a low-severity bug from a large account can outrank a
high-severity one from a trial. reported_severity keeps the original claim,
so the gap between claimed and actual urgency stays measurable.
"""

import streamlit as st
from auth import get_user_id
from database import (
    load_all_tickets, get_ticket, load_thread_messages,
    post_thread_message, update_ticket, mark_thread_read,
    get_all_profiles,
    TICKET_CATEGORIES, TICKET_SEVERITIES, TICKET_STATUSES, TICKET_PRIORITIES,
)

admin_id = get_user_id()

CATEGORY_LABELS = dict(TICKET_CATEGORIES)
SEVERITY_SHORT = {c: l.split("—")[0].strip() for c, l in TICKET_SEVERITIES}

STATUS_LABELS = {
    "open":              "🔵 Open",
    "in_progress":       "🟡 In progress",
    "waiting_on_client": "🟠 Waiting on client",
    "resolved":          "🟢 Resolved",
    "closed":            "⚪ Closed",
}

PRIORITY_BADGE = {
    "urgent": "🔴 Urgent",
    "high":   "🟠 High",
    "normal": "⚪ Normal",
    "low":    "⚫ Low",
}

CONTEXT_LABELS = {
    "chat":                "Compliance chat",
    "document_generation": "Document generation",
    "gap_assessment":      "Gap assessment",
    "website_audit":       "Website audit",
    "compliance_pulse":    "Compliance Pulse",
    "dashboard":           "Dashboard",
    "onboarding":          "Onboarding",
    "account":             "Account",
    "other":               "Other",
}

# Queue ordering. Priority first, then client-reported severity as tiebreak.
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
SEVERITY_RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def init():
    if "admin_open_ticket" not in st.session_state:
        st.session_state.admin_open_ticket = None


init()

st.markdown("## Support tickets")


# ── Detail view ───────────────────────────────────────────────
if st.session_state.admin_open_ticket:
    t = get_ticket(st.session_state.admin_open_ticket)

    if not t:
        st.warning("Ticket not found.")
        if st.button("← Back"):
            st.session_state.admin_open_ticket = None
            st.rerun()
        st.stop()

    if st.button("← Back to queue"):
        st.session_state.admin_open_ticket = None
        st.rerun()

    st.markdown(f"### {t['subject']}")
    st.caption(
        f"{CATEGORY_LABELS.get(t['category'], t['category'])} · "
        f"{CONTEXT_LABELS.get(t['context'], t['context'])} · "
        f"opened {t['created_at'][:16].replace('T', ' ')}"
    )

    if t.get("context_ref"):
        st.caption(f"Linked reference: `{t['context_ref']}`")
        if t["context"] == "chat":
            st.caption("↑ chat session id — the conversation that produced this.")

    # Reported vs actual severity: surface the gap rather than hiding it.
    if t["reported_severity"] != t["severity"]:
        st.caption(f"Client reported: **{SEVERITY_SHORT.get(t['reported_severity'])}** "
                   f"· reassessed as **{SEVERITY_SHORT.get(t['severity'])}**")

    mark_thread_read(t["thread_id"], "admin")

    # ── Triage controls ───────────────────────────────────────
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            new_status = st.selectbox(
                "Status", TICKET_STATUSES,
                index=TICKET_STATUSES.index(t["status"]),
                format_func=lambda s: STATUS_LABELS.get(s, s),
                key="adm_status",
            )
        with c2:
            new_priority = st.selectbox(
                "Priority", TICKET_PRIORITIES,
                index=TICKET_PRIORITIES.index(t["priority"]),
                format_func=lambda p: PRIORITY_BADGE.get(p, p),
                key="adm_priority",
            )
        with c3:
            sev_codes = [c for c, _ in TICKET_SEVERITIES]
            new_severity = st.selectbox(
                "Severity", sev_codes,
                index=sev_codes.index(t["severity"]),
                format_func=lambda s: SEVERITY_SHORT.get(s, s),
                key="adm_severity",
            )
        with c4:
            profiles = get_all_profiles() or []
            options = [None] + [p["id"] for p in profiles]
            labels = {p["id"]: (p.get("email") or p["id"][:8]) for p in profiles}
            current = t.get("assigned_to")
            new_assignee = st.selectbox(
                "Assigned to", options,
                index=options.index(current) if current in options else 0,
                format_func=lambda u: "— unassigned —" if u is None
                else labels.get(u, str(u)[:8]),
                key="adm_assignee",
            )

        changes = {}
        if new_status != t["status"]:
            changes["status"] = new_status
        if new_priority != t["priority"]:
            changes["priority"] = new_priority
        if new_severity != t["severity"]:
            changes["severity"] = new_severity
        if new_assignee != current:
            changes["assigned_to"] = new_assignee

        if st.button("Apply changes", type="primary", disabled=not changes):
            update_ticket(t["id"], changes, actor_id=admin_id)
            st.rerun()

    st.divider()

    for m in load_thread_messages(t["thread_id"]):
        is_admin = m["author_role"] == "admin"
        with st.chat_message("assistant" if is_admin else "user"):
            st.caption("RECOSA" if is_admin else "Client")
            st.markdown(m["body"])
            st.caption(m["created_at"][:16].replace("T", " "))

    st.divider()

    reply = st.text_area("Reply to client", key="adm_reply", height=130)
    col_r, col_rs = st.columns([1, 1])
    with col_r:
        if st.button("Send reply", type="primary", use_container_width=True):
            if reply.strip():
                post_thread_message(t["thread_id"], admin_id, "admin", reply)
                if t["status"] == "open":
                    update_ticket(t["id"], {"status": "in_progress"},
                                  actor_id=admin_id)
                st.session_state.pop("adm_reply", None)
                st.rerun()
            else:
                st.warning("Nothing to send.")
    with col_rs:
        if st.button("Send & mark resolved", use_container_width=True):
            if reply.strip():
                post_thread_message(t["thread_id"], admin_id, "admin", reply)
            update_ticket(t["id"], {"status": "resolved"}, actor_id=admin_id)
            st.session_state.pop("adm_reply", None)
            st.rerun()

    st.caption("Reply notifications to the client are content-free — "
               "subject and link only, never the body.")
    st.stop()


# ── Queue view ────────────────────────────────────────────────
all_tickets = load_all_tickets()

if not all_tickets:
    st.info("No tickets yet.")
    st.stop()

open_count = sum(1 for t in all_tickets if t["status"] == "open")
progress_count = sum(1 for t in all_tickets if t["status"] == "in_progress")
waiting_count = sum(1 for t in all_tickets if t["status"] == "waiting_on_client")
urgent_count = sum(1 for t in all_tickets
                   if t["priority"] == "urgent"
                   and t["status"] not in ("resolved", "closed"))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Open", open_count)
m2.metric("In progress", progress_count)
m3.metric("Waiting on client", waiting_count)
m4.metric("Urgent", urgent_count)

st.divider()

f1, f2, f3 = st.columns(3)
with f1:
    status_filter = st.selectbox(
        "Status", ["Active only", "All"] + TICKET_STATUSES,
        format_func=lambda s: STATUS_LABELS.get(s, s), key="f_status")
with f2:
    cat_filter = st.selectbox(
        "Category", ["All"] + [c for c, _ in TICKET_CATEGORIES],
        format_func=lambda c: CATEGORY_LABELS.get(c, c), key="f_cat")
with f3:
    ctx_filter = st.selectbox(
        "Context", ["All"] + list(CONTEXT_LABELS.keys()),
        format_func=lambda c: CONTEXT_LABELS.get(c, c), key="f_ctx")

rows = all_tickets
if status_filter == "Active only":
    rows = [t for t in rows if t["status"] not in ("resolved", "closed")]
elif status_filter != "All":
    rows = [t for t in rows if t["status"] == status_filter]
if cat_filter != "All":
    rows = [t for t in rows if t["category"] == cat_filter]
if ctx_filter != "All":
    rows = [t for t in rows if t["context"] == ctx_filter]

rows.sort(key=lambda t: (
    PRIORITY_RANK.get(t["priority"], 9),
    SEVERITY_RANK.get(t["severity"], 9),
    t["created_at"],
))

st.caption(f"{len(rows)} ticket{'s' if len(rows) != 1 else ''}")

for t in rows:
    col_a, col_b = st.columns([6, 1])
    with col_a:
        st.markdown(f"**{t['subject']}**")
        st.caption(
            f"{PRIORITY_BADGE.get(t['priority'], '')} · "
            f"{STATUS_LABELS.get(t['status'], t['status'])} · "
            f"{CATEGORY_LABELS.get(t['category'], t['category'])} · "
            f"{CONTEXT_LABELS.get(t['context'], t['context'])} · "
            f"sev {SEVERITY_SHORT.get(t['severity'], t['severity'])} · "
            f"updated {t['updated_at'][:10]}"
        )
    with col_b:
        if st.button("Open", key=f"adm_open_{t['id']}",
                     use_container_width=True):
            st.session_state.admin_open_ticket = t["id"]
            st.rerun()
    st.divider()
