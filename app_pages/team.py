"""
app_pages/team.py — usability audit batch 2 (M9): who else can work on each
company you own. Moved from Profile unchanged (S38).
"""

import streamlit as st

from auth import get_user_id
from database import (
    invite_workspace_member, list_workspace_members, remove_workspace_member,
)
from cached_reads import load_accessible_clients

st.title("Team")
st.caption("Invite colleagues to work on a company with you. They get the "
           "same access you have, except deleting the company.")

user_id = get_user_id()
clients = load_accessible_clients(user_id) or []

# ── Team (S38) ───────────────────────────────────────────────────────────
# Not tier-gated. D-90's reasoning against inventing gates ahead of a
# billing model that actually checks them applies here too — there is no
# seat pricing yet, and "Multi-user for Professional" is the sprint's own
# name for a reason: a one-client Professional account benefits from this
# exactly as much as an Advisory one does.

owned_clients = [c for c in clients if c.get("role") == "owner"]
if not owned_clients:
    st.caption("Own a client to invite people to work on it with you.")
else:
    for c in owned_clients:
        with st.container(border=True):
            st.markdown(f"**{c['company_name']}**")
            members = list_workspace_members(c["id"])
            if members:
                for m in members:
                    mc1, mc2, mc3 = st.columns([3, 2, 1])
                    mc1.write(m["display_name"])
                    mc2.caption("Active" if m["status"] == "active" else "Invited — not signed up yet")
                    if mc3.button("Remove", key=f"rm_member_{m['id']}"):
                        if remove_workspace_member(m["id"], user_id):
                            st.rerun()
            else:
                st.caption("No one else has access yet.")

            with st.form(f"invite_form_{c['id']}", clear_on_submit=True):
                inv_col1, inv_col2 = st.columns([3, 1])
                inv_email = inv_col1.text_input(
                    "Email", key=f"inv_email_{c['id']}", label_visibility="collapsed",
                    placeholder="colleague@company.com",
                )
                if inv_col2.form_submit_button("Invite", use_container_width=True):
                    if inv_email.strip():
                        ok, err = invite_workspace_member(c["id"], user_id, inv_email)
                        if ok:
                            st.success(f"Invited {inv_email.strip()}.")
                            st.rerun()
                        else:
                            st.error(err or "Could not send the invite.")
                    else:
                        st.warning("Enter an email address.")
