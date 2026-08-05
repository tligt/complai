"""
RECOSA — Support (client-facing).

Read and continue. Tickets are *created* from the help widget, which is on
every page and captures context for free; this page is where they're
followed, replied to and closed. Brevo reply notifications link here.
"""

import streamlit as st
from auth import get_user_id
from database import (
    load_my_tickets, get_ticket, load_thread_messages,
    post_thread_message, update_ticket, mark_thread_read,
    load_clients, create_ticket,
    TICKET_CATEGORIES, TICKET_SEVERITIES,
)

user_id = get_user_id()

STATUS_LABELS = {
    "open":              ("🔵", "Open"),
    "in_progress":       ("🟡", "Being looked at"),
    "waiting_on_client": ("🟠", "Waiting on you"),
    "resolved":          ("🟢", "Resolved"),
    "closed":            ("⚪", "Closed"),
}

CATEGORY_LABELS = dict(TICKET_CATEGORIES)
SEVERITY_LABELS = {c: l.split("—")[0].strip() for c, l in TICKET_SEVERITIES}

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


def init():
    defaults = {
        "support_open_ticket": None,
        "support_new":         False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init()

st.markdown("## Support")

# Deep links are normally consumed in app.py, which captures the param
# before the auth stop can discard it. This is a fallback for the case where
# the param somehow survives to here — harmless when app.py already handled it.
qp_ticket = st.query_params.get("ticket")
if qp_ticket and not st.session_state.support_open_ticket:
    st.session_state.support_open_ticket = qp_ticket
    del st.query_params["ticket"]


# ── Detail view ───────────────────────────────────────────────
if st.session_state.support_open_ticket:
    ticket = get_ticket(st.session_state.support_open_ticket)

    if not ticket:
        st.warning("That request could not be found.")
        if st.button("← Back to all requests"):
            st.session_state.support_open_ticket = None
            st.rerun()
        st.stop()

    if st.button("← Back to all requests"):
        st.session_state.support_open_ticket = None
        if "ticket" in st.query_params:
            del st.query_params["ticket"]
        st.rerun()

    icon, label = STATUS_LABELS.get(ticket["status"], ("", ticket["status"]))
    st.markdown(f"### {ticket['subject']}")
    st.caption(
        f"{icon} {label} · {CATEGORY_LABELS.get(ticket['category'], ticket['category'])} · "
        f"{CONTEXT_LABELS.get(ticket['context'], ticket['context'])} · "
        f"opened {ticket['created_at'][:10]}"
    )

    mark_thread_read(ticket["thread_id"], "client")

    st.divider()

    messages = load_thread_messages(ticket["thread_id"])
    for m in messages:
        is_admin = m["author_role"] == "admin"
        with st.chat_message("assistant" if is_admin else "user"):
            st.caption("RECOSA" if is_admin else "You")
            st.markdown(m["body"])
            st.caption(m["created_at"][:16].replace("T", " "))

    st.divider()

    if ticket["status"] == "closed":
        st.caption("This request is closed. Open a new one if you need "
                   "anything further.")
    else:
        reply = st.text_area("Reply", key="support_reply", height=110,
                             placeholder="Add to this request…")
        col_send, col_close = st.columns([1, 1])
        with col_send:
            if st.button("Send reply", type="primary",
                         use_container_width=True):
                if reply.strip():
                    post_thread_message(ticket["thread_id"], user_id,
                                        "client", reply)
                    # A client reply reopens a ticket that was parked.
                    if ticket["status"] in ("waiting_on_client", "resolved"):
                        update_ticket(ticket["id"], {"status": "open"},
                                      actor_id=user_id)
                    st.session_state.pop("support_reply", None)
                    st.rerun()
                else:
                    st.warning("Nothing to send.")
        with col_close:
            if st.button("Close request", use_container_width=True):
                update_ticket(ticket["id"], {"status": "closed"},
                              actor_id=user_id)
                st.rerun()

    st.stop()


# ── New request (fallback path) ───────────────────────────────
# Context defaults to 'account': someone who navigates here deliberately
# usually has a billing or account question rather than a feature-specific
# one. Feature-specific reports come through the widget, with real context.
if st.session_state.support_new:
    st.markdown("### New request")
    st.caption("Reporting a problem with a specific feature? Use the **Help** "
               "button on that page instead — it captures the context for you.")

    clients = load_clients(user_id) or []
    client_id = clients[0]["id"] if clients else None

    category = st.selectbox(
        "What kind of request is this?",
        options=[c for c, _ in TICKET_CATEGORIES],
        format_func=lambda c: CATEGORY_LABELS[c],
        key="sn_cat",
    )
    severity = st.selectbox(
        "How much is this affecting you?",
        options=[c for c, _ in TICKET_SEVERITIES],
        format_func=lambda c: dict(TICKET_SEVERITIES)[c],
        index=2,
        key="sn_sev",
    )
    subject = st.text_input("Subject", key="sn_subj")
    body = st.text_area("Details", key="sn_body", height=140)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Send request", type="primary", use_container_width=True):
            if subject.strip() and body.strip():
                tid = create_ticket(
                    user_id=user_id, subject=subject, body=body,
                    category=category, context="account",
                    reported_severity=severity, client_id=client_id,
                )
                if tid:
                    st.session_state.support_new = False
                    st.session_state.support_open_ticket = tid
                    st.rerun()
            else:
                st.warning("A subject and some detail, please.")
    with col_b:
        if st.button("Cancel", use_container_width=True):
            st.session_state.support_new = False
            st.rerun()

    st.stop()


# ── List view ─────────────────────────────────────────────────
col_title, col_new = st.columns([4, 1])
with col_new:
    if st.button("＋ New request", type="primary", use_container_width=True):
        st.session_state.support_new = True
        st.rerun()

tickets = load_my_tickets(user_id)

if not tickets:
    st.info("No support requests yet. Use the **Help** button on any page to "
            "raise one — it'll include what you were doing at the time.")
    st.stop()

open_tickets = [t for t in tickets if t["status"] not in ("closed", "resolved")]
done_tickets = [t for t in tickets if t["status"] in ("closed", "resolved")]


def render_row(t: dict):
    icon, label = STATUS_LABELS.get(t["status"], ("", t["status"]))
    col_s, col_b = st.columns([6, 1])
    with col_s:
        st.markdown(f"**{t['subject']}**")
        st.caption(
            f"{icon} {label} · {CATEGORY_LABELS.get(t['category'], t['category'])} · "
            f"{CONTEXT_LABELS.get(t['context'], t['context'])} · "
            f"updated {t['updated_at'][:10]}"
        )
    with col_b:
        if st.button("Open", key=f"open_{t['id']}", use_container_width=True):
            st.session_state.support_open_ticket = t["id"]
            st.rerun()
    st.divider()


if open_tickets:
    st.markdown("#### Active")
    for t in open_tickets:
        render_row(t)

if done_tickets:
    with st.expander(f"Resolved & closed ({len(done_tickets)})"):
        for t in done_tickets:
            render_row(t)
