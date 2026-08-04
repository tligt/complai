"""
RECOSA — S22 help widget.

Mounted on every page. Submission only: context is captured automatically
from wherever the user is standing, which is the whole reason tickets are
raised here rather than from the support page.

Reading and replying live on pages/support.py — a popover is a bad place to
work through a thread, and Brevo reply notifications need a URL to land on.

Streamlit note: there is no true floating overlay in pure Streamlit (HTML
injected via st.markdown cannot call back into Python). st.popover is the
closest native equivalent — anchored, dismissible, and it keeps the form
inside Streamlit's own state model rather than fighting it.
"""

import streamlit as st
from database import (
    create_ticket, count_unread_replies,
    TICKET_CATEGORIES, TICKET_SEVERITIES,
)

# Where the widget is allowed to say it came from. Must match the
# support_tickets.context check constraint in the S22 migration.
VALID_CONTEXTS = {
    "chat", "document_generation", "gap_assessment", "website_audit",
    "compliance_pulse", "dashboard", "onboarding", "account", "other",
}


def render_help_widget(user_id: str,
                       context: str = "other",
                       context_ref: str | None = None,
                       client_id: str | None = None,
                       label: str = "Help"):
    """Render the help popover.

    context     — the surface the user is on, captured not asked
    context_ref — chat_session_id, document_id etc. where one exists
    """
    if context not in VALID_CONTEXTS:
        context = "other"

    unread = count_unread_replies(user_id)
    button_label = f"💬 {label}" + (f" ({unread})" if unread else "")

    with st.popover(button_label, use_container_width=True):
        if unread:
            st.info(f"You have {unread} unread "
                    f"repl{'y' if unread == 1 else 'ies'} — "
                    f"see **Support** in the menu.")

        st.markdown("**Get help**")
        st.caption("We'll pick this up and reply in the app.")

        category = st.selectbox(
            "What kind of request is this?",
            options=[code for code, _ in TICKET_CATEGORIES],
            format_func=lambda c: dict(TICKET_CATEGORIES)[c],
            key=f"hw_cat_{context}",
        )

        severity = st.selectbox(
            "How much is this affecting you?",
            options=[code for code, _ in TICKET_SEVERITIES],
            format_func=lambda c: dict(TICKET_SEVERITIES)[c],
            index=2,  # normal
            key=f"hw_sev_{context}",
            help="Pick honestly — it helps us order the queue.",
        )

        subject = st.text_input(
            "Subject",
            key=f"hw_subj_{context}",
            placeholder="One line summary",
        )

        body = st.text_area(
            "Details",
            key=f"hw_body_{context}",
            height=120,
            placeholder="What happened, and what did you expect instead?",
        )

        st.caption(f"We'll automatically include which page you were on "
                   f"({context.replace('_', ' ')}), so you don't have to explain it.")

        if st.button("Send request", type="primary",
                     use_container_width=True, key=f"hw_send_{context}"):
            if not subject.strip():
                st.warning("A subject helps us route this — even a few words.")
            elif not body.strip():
                st.warning("Please add some detail.")
            else:
                ticket_id = create_ticket(
                    user_id=user_id,
                    subject=subject,
                    body=body,
                    category=category,
                    context=context,
                    context_ref=context_ref,
                    reported_severity=severity,
                    client_id=client_id,
                )
                if ticket_id:
                    # Clear the form on the next rerun rather than writing to
                    # widget state directly — direct overwrite conflicts.
                    st.session_state[f"hw_clear_{context}"] = True
                    st.success("Sent. You can follow it under **Support**.")

    # Deferred form reset
    if st.session_state.get(f"hw_clear_{context}"):
        for suffix in ("subj", "body"):
            st.session_state.pop(f"hw_{suffix}_{context}", None)
        st.session_state[f"hw_clear_{context}"] = False
