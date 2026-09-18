"""
pages_admin/users.py — accounts, roles and subscription tiers.

The only code path that ever sets profiles.role. Every admin account until
now was made one by hand, directly in the database — there was nothing else
to make it here with. Also where a subscription tier is actually assigned
today: there is no billing integration yet (S43), so an admin flipping this
by hand IS the assignment mechanism, not a stopgap for one.

Table-plus-detail-panel, same shape as pages/obligations.py: a summary grid
to scan, one detail form for whichever account is selected.
"""

import streamlit as st

from auth import get_user_id
from database import (
    get_all_profiles, get_supabase_admin,
    set_user_role, set_user_tier, SUBSCRIPTION_TIERS, ROLES,
)

st.title("Users")
st.caption("Accounts, roles and subscription tiers.")

admin_id = get_user_id()

profiles = get_all_profiles()
if not profiles:
    st.info("No accounts found.")
    st.stop()

# One client-count / first-company lookup per account, client-side — same
# pattern pages_admin/dashboard.py already uses for its per-client table
# rather than a SQL join PostgREST doesn't offer here.
try:
    _clients = get_supabase_admin().table("clients") \
        .select("user_id, company_name").execute().data or []
except Exception:
    _clients = []
_companies_by_user: dict[str, list[str]] = {}
for c in _clients:
    _companies_by_user.setdefault(c["user_id"], []).append(c["company_name"])

st.dataframe(
    [
        {
            "Email": p.get("email") or "",
            "Name": p.get("full_name") or "",
            "Role": ROLES.get(p.get("role") or "", p.get("role") or ""),
            "Plan": SUBSCRIPTION_TIERS.get(
                p.get("subscription_tier") or "professional",
                p.get("subscription_tier") or "",
            ),
            "Clients": ", ".join(_companies_by_user.get(p["id"], [])) or "—",
            "Created": (p.get("created_at") or "")[:10],
        }
        for p in profiles
    ],
    hide_index=True,
    width="stretch",
    column_config={
        "Email": st.column_config.TextColumn(width=280),
        "Name": st.column_config.TextColumn(width=160),
        "Role": st.column_config.TextColumn(width=90),
        "Plan": st.column_config.TextColumn(width=110),
        "Clients": st.column_config.TextColumn(width=220),
        "Created": st.column_config.TextColumn(width=100),
    },
)

_profiles_by_id = {p["id"]: p for p in profiles}
_sel_id = st.selectbox(
    "Select an account",
    options=list(_profiles_by_id.keys()),
    format_func=lambda i: _profiles_by_id[i].get("email") or i,
    key="admin_user_select",
)
target = _profiles_by_id[_sel_id]
is_self = target["id"] == admin_id

with st.container(border=True):
    st.markdown(f"**{target.get('email') or target['id']}**")
    if is_self:
        st.caption("This is your own account.")

    col_role, col_tier = st.columns(2)
    with col_role:
        _role_codes = list(ROLES.keys())
        _current_role = target.get("role") or "client"
        new_role = st.selectbox(
            "Role", options=_role_codes,
            index=_role_codes.index(_current_role) if _current_role in _role_codes else 0,
            format_func=lambda c: ROLES[c],
            key=f"role_{target['id']}",
            # There is exactly one admin account in the database today.
            # Letting it demote itself here has no in-code way back.
            disabled=is_self,
            help=("You can't change your own role." if is_self else None),
        )
        if not is_self and st.button("Save role", key=f"save_role_{target['id']}"):
            if set_user_role(target["id"], new_role):
                st.success("Role updated.")
                st.rerun()
            else:
                st.error("Could not update role.")

    with col_tier:
        _tier_codes = list(SUBSCRIPTION_TIERS.keys())
        _current_tier = target.get("subscription_tier") or "professional"
        new_tier = st.selectbox(
            "Plan", options=_tier_codes,
            index=_tier_codes.index(_current_tier) if _current_tier in _tier_codes else 0,
            format_func=lambda c: SUBSCRIPTION_TIERS[c],
            key=f"tier_{target['id']}",
        )
        if st.button("Save plan", key=f"save_tier_{target['id']}"):
            if set_user_tier(target["id"], new_tier):
                st.success("Plan updated.")
                st.rerun()
            else:
                st.error("Could not update plan.")
