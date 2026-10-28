"""
app_pages/team.py — usability audit batch 2 (M9): who else can work on each
company. Moved from Profile unchanged (S38).

S54: every person has a role on the company — admin, contributor or
read-only. Admins (and the owner) invite, change roles and remove; everyone
else sees who has access. People who reach a company through a group are
managed on the Group page.
"""

import streamlit as st

from auth import get_user_id
from database import (
    CLIENT_ROLES, CLIENT_ROLE_HELP, can_manage_people, role_label,
    invite_workspace_member, list_workspace_members, remove_workspace_member,
    set_workspace_member_role,
)
from cached_reads import load_accessible_clients

st.title("Team")
st.caption("Who can work on each company, and what they can do. Every change "
           "here is recorded in the Activity Log.")

with st.expander("What the roles mean"):
    for _r, _label in CLIENT_ROLES.items():
        st.markdown(f"**{_label}** — {CLIENT_ROLE_HELP[_r]}")
    st.caption("The owner of a company is always an admin, and is the only one "
               "who can delete it.")

user_id = get_user_id()
clients = load_accessible_clients(user_id) or []

# Not tier-gated. D-90's reasoning against inventing gates ahead of a
# billing model that actually checks them applies here too — there is no
# seat pricing yet (S46).

_role_keys = list(CLIENT_ROLES)


def _refresh():
    load_accessible_clients.clear()
    st.rerun()


if not clients:
    st.caption("Set up a company to invite people to work on it with you.")

for c in clients:
    manage = can_manage_people(c.get("role"))
    with st.container(border=True):
        st.markdown(f"**{c['company_name']}** · your role: {role_label(c.get('role'))}")
        members = list_workspace_members(c["id"])
        if not members:
            st.caption("No one else has access to this company directly.")
        for m in members:
            mc1, mc2, mc3 = st.columns([3, 2, 1])
            mc1.write(m["display_name"])
            if m["status"] != "active":
                mc1.caption("Invited — not signed up yet")
            if manage:
                _key = f"role_{m['id']}"
                new_role = mc2.selectbox(
                    "Role", _role_keys, index=_role_keys.index(m.get("role") or "contributor"),
                    format_func=CLIENT_ROLES.get, key=_key, label_visibility="collapsed",
                )
                if new_role != (m.get("role") or "contributor"):
                    ok, err = set_workspace_member_role(m["id"], new_role, user_id)
                    if ok:
                        st.toast(f"{m['display_name']} is now {CLIENT_ROLES[new_role]}.")
                        _refresh()
                    else:
                        st.error(err)
                if mc3.button("Remove", key=f"rm_member_{m['id']}"):
                    if remove_workspace_member(m["id"], user_id):
                        _refresh()
            else:
                mc2.caption(role_label(m.get("role")))
                if m.get("member_user_id") == user_id and mc3.button(
                        "Leave", key=f"leave_{m['id']}"):
                    if remove_workspace_member(m["id"], user_id):
                        st.session_state.pop("selected_client", None)
                        _refresh()

        if not manage:
            continue
        with st.form(f"invite_form_{c['id']}", clear_on_submit=True):
            inv_col1, inv_col2, inv_col3 = st.columns([3, 2, 1])
            inv_email = inv_col1.text_input(
                "Email", key=f"inv_email_{c['id']}", label_visibility="collapsed",
                placeholder="colleague@company.com",
            )
            inv_role = inv_col2.selectbox(
                "Role", _role_keys, index=_role_keys.index("contributor"),
                format_func=CLIENT_ROLES.get, key=f"inv_role_{c['id']}",
                label_visibility="collapsed",
            )
            if inv_col3.form_submit_button("Invite", use_container_width=True):
                if inv_email.strip():
                    ok, err = invite_workspace_member(c["id"], user_id, inv_email, inv_role)
                    if ok:
                        st.success(f"Invited {inv_email.strip()} as {CLIENT_ROLES[inv_role]}.")
                        _refresh()
                    else:
                        st.error(err or "Could not send the invite.")
                else:
                    st.warning("Enter an email address.")

st.caption("People with access to every company of a group are managed on the "
           "**Group** page.")
