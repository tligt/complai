"""
subscribe_view.py — S49 (D-115). What a free ('registered') or expired
account sees on every page except its free check result.

app.py points every menu item at render_subscribe() for those accounts, so
the menu still shows what RECOSA does, and any click lands here.

Until Stripe (S46), the trial is the only self-service step: choosing a paid
plan, or Advisory, is a request to RECOSA, sent as a billing support ticket,
and an admin sets the plan by hand (pages_admin/users.py).
"""

import streamlit as st

from database import (
    TRIAL_DAYS, start_trial, create_ticket, get_user_profile, record_funnel_event,
)


def render_subscribe() -> None:
    user_id = st.session_state.user.id
    profile = get_user_profile(user_id)
    status = profile.get("subscription_status") or "registered"

    st.title("Unlock RECOSA")

    if status == "expired":
        st.info("Your free trial has ended. Your data is kept — choose a plan to "
                "continue where you left off.")
    else:
        st.markdown(
            "This part of RECOSA is included in every plan. Start a "
            f"**{TRIAL_DAYS}-day free trial** to use all of it — no card needed."
        )

    col_pro, col_adv = st.columns(2)
    with col_pro:
        with st.container(border=True):
            st.subheader("Professional")
            st.caption("For a company managing its own compliance.")
            st.markdown(
                "- Full GDPR, NIS2 and AI Act assessment\n"
                "- Documents generated from your own systems\n"
                "- Obligations register and action plan\n"
                "- Regulatory updates and website monitoring"
            )
            if status == "registered":
                if st.button(f"Start {TRIAL_DAYS}-day free trial", type="primary",
                             use_container_width=True, key="sub_trial"):
                    if start_trial(user_id):
                        record_funnel_event("trial_started", None,
                                            profile.get("signup_source"))
                        st.rerun()
                    else:
                        st.error("Could not start the trial. Please try again.")
            else:
                _request_plan("professional", user_id)
    with col_adv:
        with st.container(border=True):
            st.subheader("Advisory")
            st.caption("For consultants managing several client companies.")
            st.markdown(
                "- Everything in Professional\n"
                "- Several client companies in one account\n"
                "- Switch between clients on every page\n"
                "- Invite your team"
            )
            _request_plan("advisory", user_id)


def render_trial_cta(profile: dict) -> None:
    """The next step under a free check result."""
    status = profile.get("subscription_status") or "registered"
    if status in ("trial", "active"):
        return
    with st.container(border=True):
        st.markdown("### Next: the full assessment")
        st.markdown(
            "Your free check is a first read. The full assessment scores you against "
            "every applicable GDPR, NIS2 and AI Act obligation, generates the documents "
            "you're missing and turns the gaps into an action plan."
        )
        if status == "registered":
            if st.button(f"Start {TRIAL_DAYS}-day free trial — no card", type="primary",
                         key="cta_trial"):
                if start_trial(profile["id"]):
                    record_funnel_event("trial_started", None, profile.get("signup_source"))
                    st.rerun()
                else:
                    st.error("Could not start the trial. Please try again.")
        else:
            st.info("Your trial has ended — open any page in the menu to choose a plan.")


def _request_plan(plan: str, user_id: str) -> None:
    """Until S46: a plan request is a billing ticket the team answers."""
    sent_key = f"sub_requested_{plan}"
    if st.session_state.get(sent_key):
        st.success("Request sent — we'll get back to you by email.")
        return
    if st.button(f"Request {plan.title()}", use_container_width=True,
                 key=f"sub_req_{plan}"):
        ticket = create_ticket(
            user_id=user_id,
            subject=f"Plan request: {plan.title()}",
            body=(f"This account would like the {plan.title()} plan. "
                  f"Sent from the subscribe page."),
            category="billing",
            context="account",
        )
        if ticket:
            st.session_state[sent_key] = True
            st.rerun()
