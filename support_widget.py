"""
RECOSA — S22 help widget.

Mounted on every page. Submission only: context is captured automatically
from wherever the user is standing, which is the whole reason tickets are
raised here rather than from the support page.

Reading and replying live on pages/support.py — a popover is a bad place to
work through a thread, and Brevo reply notifications need a URL to land on.

Positioning: st.container(key=...) renders with a `st-key-{key}` class, so
a real Streamlit widget can be position:fixed without falling back to raw
HTML (which cannot call into Python). Anchored top-right, below the account
menu — bottom-right would collide with st.chat_input, which is itself fixed
to the bottom of the viewport.
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

_FLOAT_CSS = """
<style>
.st-key-recosa_help_widget {
    position: fixed;
    top: 3.75rem;          /* clears the account menu at top: 0.75rem */
    right: 1rem;
    z-index: 998;          /* under the account menu (9999), above content */
    width: auto;
    min-width: 0;
}
.st-key-recosa_help_widget button {
    border-radius: 20px !important;
    box-shadow: 0 2px 10px rgba(0,51,102,0.15) !important;
    white-space: nowrap;
}
/* The popover panel itself needs room and its own stacking context. */
.st-key-recosa_help_widget [data-testid="stPopoverBody"] {
    min-width: 320px;
}
@media (max-width: 640px) {
    .st-key-recosa_help_widget { top: 3.25rem; right: 0.5rem; }
    .st-key-recosa_help_widget [data-testid="stPopoverBody"] {
        min-width: 260px;
    }
}
</style>
"""


def render_help_widget(user_id: str,
                       context: str = "other",
                       context_ref: str | None = None,
                       client_id: str | None = None,
                       label: str = "Help",
                       placement: str = "sidebar"):
    """Render the help popover.

    context     — the surface the user is on, captured not asked
    context_ref — chat_session_id, document_id etc. where one exists
    placement   — "sidebar" | "fixed" | "inline"

    "sidebar" is the default because it is the only one that reliably stays
    in view: Streamlit's sidebar scrolls independently of page content, with
    no CSS or version dependency.

    "fixed" pins the widget to the viewport via st.container(key=...), which
    renders a `st-key-{key}` class. That requires Streamlit >= 1.42 — on
    older versions the key is not applied, the CSS has nothing to hook onto,
    and the widget silently falls back to scrolling inline.
    """
    if context not in VALID_CONTEXTS:
        context = "other"

    if placement == "sidebar":
        with st.sidebar:
            st.divider()
            _render_form(user_id, context, context_ref, client_id, label)
        return

    if placement == "fixed":
        st.markdown(_FLOAT_CSS, unsafe_allow_html=True)
        try:
            container = st.container(key="recosa_help_widget")
        except TypeError:
            # Streamlit < 1.42 — no key support, so no targetable class.
            container = st.container()
    else:
        container = st.container()

    with container:
        _render_form(user_id, context, context_ref, client_id, label)


def _render_form(user_id, context, context_ref, client_id, label):
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
