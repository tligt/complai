"""
pages/profile.py — Account, password, plan and client management.

The first page in the "Account" nav group, and the first thing on this page
is deliberately account-level, not client-level: your own name, your own
password, your own plan. Client management sits below it because a client is
something an account HAS, not something it IS — same distinction the sidebar
"My clients" selector on Chat already draws, just given a permanent home
instead of a collapsed expander two screens down.
"""

import streamlit as st

import inventory as INV
from auth import get_user_id, change_password
from database import (
    get_user_profile, update_user_profile,
    create_client_record, SUBSCRIPTION_TIERS,
)
from cached_reads import load_clients

# Kept local rather than imported from pages/chat.py — pages are scripts,
# not a module surface meant to be imported from, and these are small
# enough that duplicating them is cheaper than making one page reach into
# another's internals.
COUNTRY_OPTIONS = {
    "BE": "🇧🇪 Belgium",
    "FR": "🇫🇷 France",
    "EU": "🇪🇺 EU (no specific country)",
}
SECTOR_OPTIONS = [
    "SaaS / Technology", "Professional services", "Healthcare / Medtech",
    "Manufacturing", "Finance / Fintech", "Logistics / Transport",
    "Retail / E-commerce", "Education", "Other",
]
SIZE_OPTIONS = ["1-10", "11-50", "51-150", "150+"]
REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT"]

LANGUAGE_LABELS = {
    "en": "English", "fr": "Français", "nl": "Nederlands", "de": "Deutsch",
}

st.title("Profile")

user_id = get_user_id()
profile = get_user_profile(user_id)

# ── Account ──────────────────────────────────────────────────────────────
st.subheader("Account")

st.text_input("Email", value=st.session_state.user.email, disabled=True,
               help="Changing the address you sign in with isn't available "
                    "yet — contact support if you need it updated.")

with st.form("profile_account"):
    # Explicit keys, cleared on a successful save below. Streamlit ignores
    # a fresh value= once a widget's key already exists in session_state —
    # the same gotcha pages/inventory.py documents and works around for its
    # activity-language boxes — so without this the field just saved would
    # keep showing what it held before the save, not what got written.
    full_name = st.text_input(
        "Full name", value=profile.get("full_name") or "", key="profile_full_name",
    )

    _lang_opts = list(INV.LANGUAGES)
    _current_lang = profile.get("ui_language") or "en"
    ui_language = st.selectbox(
        "Interface language",
        options=_lang_opts,
        index=_lang_opts.index(_current_lang) if _current_lang in _lang_opts else 0,
        format_func=lambda c: LANGUAGE_LABELS.get(c, c.upper()),
        key="profile_ui_language",
        help="The language labels, captions and menus are shown in — not "
             "the language your documents are produced in, which is set "
             "per client below.",
    )

    if st.form_submit_button("Save", type="primary"):
        if update_user_profile(user_id, full_name=full_name.strip(),
                                ui_language=ui_language):
            st.success("Saved.")
            st.session_state.pop("profile_full_name", None)
            st.session_state.pop("profile_ui_language", None)
            st.rerun()
        else:
            st.error("Could not save.")

st.divider()

# ── Password ─────────────────────────────────────────────────────────────
st.subheader("Password")

with st.form("profile_password"):
    new_pw = st.text_input("New password (min. 8 characters)", type="password")
    new_pw2 = st.text_input("Confirm new password", type="password")

    if st.form_submit_button("Change password", type="primary"):
        if not new_pw:
            st.warning("Enter a new password.")
        elif new_pw != new_pw2:
            st.error("Passwords do not match.")
        elif len(new_pw) < 8:
            st.error("Password must be at least 8 characters.")
        else:
            ok, err = change_password(new_pw)
            if ok:
                st.success("Password changed.")
            else:
                st.error(f"Could not change password: {err}")

st.divider()

# ── Plan ─────────────────────────────────────────────────────────────────
st.subheader("Plan")

_tier = profile.get("subscription_tier") or "professional"
st.markdown(f"**{SUBSCRIPTION_TIERS.get(_tier, _tier.title())}**")
st.caption(
    "No self-serve upgrade yet — get in touch through Support if you need "
    "a different plan."
)

st.divider()

# ── Your clients ─────────────────────────────────────────────────────────
st.subheader("Your clients")
st.caption(
    "The companies this account manages compliance for. Professional "
    "accounts have one; Advisory accounts can have several."
)

clients = load_clients(user_id)
if clients:
    for c in clients:
        with st.container(border=True):
            st.markdown(f"**{c['company_name']}**")
            st.caption(
                f"{c.get('sector', '')} · {COUNTRY_OPTIONS.get(c.get('country'), c.get('country', ''))} · "
                + ", ".join(c.get("regulations") or [])
            )
else:
    st.info("No clients yet. Add one below.")

with st.expander("➕ New client"):
    with st.form("profile_new_client"):
        nc_name = st.text_input("Company name")
        nc_sector = st.selectbox("Sector", SECTOR_OPTIONS)
        nc_country = st.selectbox(
            "Country", list(COUNTRY_OPTIONS.keys()),
            format_func=lambda x: COUNTRY_OPTIONS[x],
        )
        nc_size = st.selectbox("Size", SIZE_OPTIONS)
        nc_regs = st.multiselect("Regulations", REGULATION_OPTIONS, default=["GDPR"])

        if st.form_submit_button("Create client", type="primary"):
            if nc_name.strip():
                result = create_client_record(user_id, {
                    "company_name": nc_name.strip(),
                    "sector": nc_sector,
                    "country": nc_country,
                    "company_size": nc_size,
                    "regulations": nc_regs,
                })
                if result:
                    st.success(f"{nc_name} created.")
                    st.rerun()
                else:
                    st.error("Could not create client.")
            else:
                st.warning("Give the company a name.")
