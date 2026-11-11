"""
app_pages/profile.py — the Account page: your name, interface language,
password and plan.

Usability audit batch 2 (M9): this page also held the client list, the new-
client form and team invitations. Companies moved to Company profile
(app_pages/company.py), invitations to Team (app_pages/team.py).
"""
from i18n import tr  # S64 interface translation (D-164)

import streamlit as st

import inventory as INV
from auth import get_user_id, change_password
from database import (
    get_user_profile, update_user_profile,
    SUBSCRIPTION_TIERS, set_user_tier,
)

LANGUAGE_LABELS = {
    "en": "English", "fr": "Français", "nl": "Nederlands", "de": "Deutsch",
}

st.title(tr("Account"))

user_id = get_user_id()
profile = get_user_profile(user_id)

# ── Account ──────────────────────────────────────────────────────────────
st.subheader(tr("Account"))

st.text_input(tr("Email"), value=st.session_state.user.email, disabled=True,
               help=tr("Changing the address you sign in with isn't available "
                    "yet — contact support if you need it updated."))

with st.form("profile_account"):
    # Explicit keys, cleared on a successful save below. Streamlit ignores
    # a fresh value= once a widget's key already exists in session_state —
    # the same gotcha pages/inventory.py documents and works around for its
    # activity-language boxes — so without this the field just saved would
    # keep showing what it held before the save, not what got written.
    full_name = st.text_input(
        tr("Full name"), value=profile.get("full_name") or "", key="profile_full_name",
    )

    _lang_opts = list(INV.LANGUAGES)
    _current_lang = profile.get("ui_language") or "en"
    ui_language = st.selectbox(
        tr("Interface language"),
        options=_lang_opts,
        index=_lang_opts.index(_current_lang) if _current_lang in _lang_opts else 0,
        format_func=lambda c: LANGUAGE_LABELS.get(c, c.upper()),
        key="profile_ui_language",
        help=tr("The language labels, captions and menus are shown in — not "
             "the language your documents are produced in, which is set "
             "per company on Company profile."),
    )

    if st.form_submit_button(tr("Save"), type="primary"):
        if update_user_profile(user_id, full_name=full_name.strip(),
                                ui_language=ui_language):
            st.success(tr("Saved."))
            st.session_state.pop("profile_full_name", None)
            st.session_state.pop("profile_ui_language", None)
            st.rerun()
        else:
            st.error(tr("Could not save."))

st.divider()

# ── Password ─────────────────────────────────────────────────────────────
st.subheader(tr("Password"))

with st.form("profile_password"):
    new_pw = st.text_input(tr("New password (min. 8 characters)"), type="password")
    new_pw2 = st.text_input(tr("Confirm new password"), type="password")

    if st.form_submit_button(tr("Change password"), type="primary"):
        if not new_pw:
            st.warning(tr("Enter a new password."))
        elif new_pw != new_pw2:
            st.error(tr("Passwords do not match."))
        elif len(new_pw) < 8:
            st.error(tr("Password must be at least 8 characters."))
        else:
            ok, err = change_password(new_pw)
            if ok:
                st.success(tr("Password changed."))
            else:
                st.error(tr("Could not change password: {err}").format(err=err))

st.divider()

# ── Plan (usability audit M10) ────────────────────────────────────────────
# What you have, what it includes, trial days left, and how to change — the
# old section showed the plan name and "downgrading isn't self-serve" only.
st.subheader(tr("Plan"))

_tier = profile.get("subscription_tier") or "professional"
_status = profile.get("subscription_status") or "active"

# S59: the plan is the customer account's. Someone who owns no account (an
# invited colleague) works under the account of the company they are in:
# they see its plan, and its owner changes it.
_managed_by = None
if not profile.get("account"):
    from active_client import get_active_client
    from database import account_for_client
    _acc = account_for_client((get_active_client(user_id) or {}).get("id"))
    if _acc:
        _tier, _status, _managed_by = _acc["plan"], _acc["status"], _acc["name"]
        profile = {**profile, "trial_ends_at": _acc.get("trial_ends_at")}

PLAN_INCLUDES = {
    "starter": "One company · GDPR, NIS2 and the EU AI Act · obligations and "
               "action plan, systems, the core documents, incidents, web audit, "
               "assistant and regulatory alerts",
    "enterprise": "Everything in Professional · custom templates · a dedicated "
                  "contact · terms agreed with you",
    "professional": "One company · every module: obligations and action plan, "
                    "systems, documents, incidents, risk assessments, web audit, "
                    "assistant and regulatory alerts · your team as members",
    "advisory": "Everything in Professional · several companies from one account, "
                "switched from the menu · documents for an outside company",
}

with st.container(border=True):
    p1, p2 = st.columns([3, 2])
    if _status in ("registered", "expired"):
        p1.markdown(tr("**Free account**"))
        p1.caption(tr("The free compliance check and your company profile. The rest "
                   "of RECOSA opens with a subscription."))
        if _status == "expired":
            p2.warning(tr("Your free trial has ended."))
    else:
        p1.markdown(f"**{SUBSCRIPTION_TIERS.get(_tier, _tier.title())}**")
        p1.caption(PLAN_INCLUDES.get(_tier, ""))
        if _status == "trial" and profile.get("trial_ends_at"):
            from datetime import datetime, timezone
            from display import fmt_date, plural
            _ends = datetime.fromisoformat(profile["trial_ends_at"].replace("Z", "+00:00"))
            _left = max((_ends - datetime.now(timezone.utc)).days + 1, 0)
            p2.info(tr("Free trial — **{plural_left_day} left**, until {fmt_date_profile_trial_e}.").format(plural_left_day=plural(_left, 'day'), fmt_date_profile_trial_e=fmt_date(profile['trial_ends_at'])))

    if _managed_by:
        p1.caption(tr("The plan of **{managed_by}**, the account this company belongs to.").format(managed_by=_managed_by))

st.markdown(tr("**Changing plan**"))
if _managed_by:
    st.caption(tr("The plan is managed by the owner of {managed_by}.").format(managed_by=_managed_by))
elif _status in ("registered", "expired"):
    st.caption(tr("To subscribe, write to us through Support."))
    if st.button(tr("Contact support"), key="plan_support"):
        st.switch_page("app_pages/support.py")
elif _tier == "starter":
    # Upgrade only, same reasoning as below: Starter's shape is a subset of
    # Professional's, so gaining room cannot invalidate anything.
    st.caption(tr("Professional adds several users, unlimited website audits and the "
               "full document library."))
    if st.button(tr("Upgrade to Professional"), type="primary", key="plan_up_pro"):
        ok, err = set_user_tier(user_id, "professional")
        if ok:
            st.success(tr("You're on Professional now."))
            st.rerun()
        else:
            st.error(err or "Could not upgrade.")
elif _tier == "professional":
    # Upgrade only. Self-serve DOWNGRADE stays out of this page on
    # purpose — it's a support conversation, not a button, both for the
    # revenue reason (don't make it easy to pay less) and the technical
    # one (an Advisory account can hold several clients; Professional
    # can't, and nothing here should decide which one survives). Upgrade
    # carries neither risk: Professional's shape is a strict subset of
    # what Advisory allows, so gaining room can't invalidate anything.
    st.caption("Advisory adds: " + PLAN_INCLUDES["advisory"].split(" · ", 1)[1] + ".")
    if st.button(tr("Upgrade to Advisory"), type="primary"):
        ok, err = set_user_tier(user_id, "advisory")
        if ok:
            st.success(tr("You're on Advisory now."))
            st.rerun()
        else:
            st.error(err or "Could not upgrade.")
elif _tier == "enterprise":
    st.caption(tr("Your terms are agreed with us: write to us through Support for any change."))
else:
    st.caption(
        tr("Moving back to Professional keeps one company, so we do it with you: "
        "write to us through Support and say which company to keep.")
    )
    if st.button(tr("Contact support"), key="plan_support"):
        st.switch_page("app_pages/support.py")

st.divider()
st.subheader(tr("Page tips"))
st.caption(tr("The \"What is this page for?\" panels you closed with Got it."))
if st.button(tr("Show page tips again"), key="tips_reset"):
    from guide import reset_tips
    reset_tips()
    st.success(tr("Tips are back on every page."))
