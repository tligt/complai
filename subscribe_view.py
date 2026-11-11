"""
subscribe_view.py — S49 (D-115). What a free ('registered') or expired
account sees on every page except its free check result.

app.py points every menu item at render_subscribe() for those accounts, so
the menu still shows what RECOSA does, and any click lands here.

Until Stripe (S46), the trial is the only self-service step: choosing a paid
plan, or Advisory, is a request to RECOSA, sent as a billing support ticket,
and an admin sets the plan by hand (pages_admin/users.py).

D-170: requesting a plan needs the client company's details (who signs and
pays: client_company_view.py). Starting the trial does not.
"""
from i18n import tr  # S64 interface translation (D-164)

import streamlit as st

from database import (
    TRIAL_DAYS, start_trial, create_ticket, get_user_profile, record_funnel_event,
    SIGNUP_PLANS, SUBSCRIPTION_TIERS,
)


def render_subscribe() -> None:
    user_id = st.session_state.user.id
    profile = get_user_profile(user_id)
    status = profile.get("subscription_status") or "registered"

    st.title(tr("Unlock RECOSA"))

    if status == "expired":
        st.info(tr("Your free trial has ended. Your data is kept — choose a plan to "
                "continue where you left off."))
    else:
        st.markdown(
            tr("This part of RECOSA is included in every plan. Start a **{trial_days}-day free trial** to use all of it — no card needed.").format(trial_days=TRIAL_DAYS)
        )

    # D-170: the company that subscribes, before any plan request.
    from database import account_for_user, missing_kyc
    from client_company_view import render_client_company
    acc = account_for_user(user_id)
    ready = bool(acc) and not missing_kyc(acc)
    if acc:
        with st.expander(tr("Your company — needed to request a plan"),
                         expanded=status == "expired" and not ready):
            ready = render_client_company(acc, user_id=user_id)

    # D-126: the website's plans, as on the sign-up form. Advisory stays a
    # request, for consultants.
    from auth import PLAN_INFO, ENTERPRISE_URL
    cols = st.columns(len(SIGNUP_PLANS))
    for col, plan in zip(cols, SIGNUP_PLANS):
        with col, st.container(border=True):
            st.subheader(SUBSCRIPTION_TIERS[plan])
            st.markdown(tr("**{plan_info_plan_0}** excl. VAT").format(plan_info_plan_0=PLAN_INFO[plan][0]))
            st.caption(PLAN_INFO[plan][1])
            if status == "registered":
                if st.button(tr("Start {trial_days}-day free trial").format(trial_days=TRIAL_DAYS), type="primary" if plan == "professional" else "secondary",
                             use_container_width=True, key=f"sub_trial_{plan}"):
                    if start_trial(user_id, plan):
                        record_funnel_event("trial_started", None,
                                            profile.get("signup_source"))
                        st.rerun()
                    else:
                        st.error(tr("Could not start the trial. Please try again."))
            else:
                _request_plan(plan, user_id, ready)
    st.caption(tr("Larger organisation? [Contact us]({enterprise_url}) about Enterprise. Consultant managing several client companies? Ask for Advisory:").format(enterprise_url=ENTERPRISE_URL))
    _request_plan("advisory", user_id, ready)


def render_trial_cta(profile: dict) -> None:
    """The next step under a free check result."""
    status = profile.get("subscription_status") or "registered"
    if status in ("trial", "active"):
        return
    with st.container(border=True):
        st.markdown(tr("### Next: the full assessment"))
        st.markdown(
            tr("Your free check is a first read. The full assessment scores you against "
            "every applicable GDPR, NIS2 and AI Act obligation, generates the documents "
            "you're missing and turns the gaps into an action plan.")
        )
        if status == "registered":
            if st.button(tr("Start {trial_days}-day free trial — no card").format(trial_days=TRIAL_DAYS), type="primary",
                         key="cta_trial"):
                if start_trial(profile["id"]):
                    record_funnel_event("trial_started", None, profile.get("signup_source"))
                    st.rerun()
                else:
                    st.error(tr("Could not start the trial. Please try again."))
        else:
            st.info(tr("Your trial has ended — open any page in the menu to choose a plan."))


def _request_plan(plan: str, user_id: str, ready: bool = True) -> None:
    """Until S46: a plan request is a billing ticket the team answers.
    D-170: only once the client company's details are in (ready)."""
    sent_key = f"sub_requested_{plan}"
    if st.session_state.get(sent_key):
        st.success(tr("Request sent — we'll get back to you by email."))
        return
    if st.button(tr("Request {plan_title}").format(plan_title=plan.title()), use_container_width=True,
                 key=f"sub_req_{plan}", disabled=not ready,
                 help=None if ready else tr("Fill in your company first (above).")):
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
