"""
app_pages/group.py — S54: an Enterprise group.

A group is one Enterprise owner's account: every company or division that
owner owns belongs to it, including those added later. People invited here
get their role on all of them. The overview shows each company's headline
figure (D-123) side by side, computed the same way as on Home.
"""
from i18n import tr  # S64 interface translation (D-164)

import streamlit as st

import table_view as tv

import obligation_view as OV
from auth import ENTERPRISE_URL, get_user_id
from cached_reads import load_accessible_clients
from database import (
    CLIENT_ROLES, CLIENT_ROLE_HELP, can_manage_people, role_label,
    create_group, get_user_profile, group_companies, invite_group_member,
    list_group_members, load_member_groups, remove_group_member, rename_group,
    set_group_member_role,
)
from display import regulation_label

st.title(tr("Group"))
st.caption(tr("All the companies and divisions of your group in one place, and the "
           "people who work across them."))

user_id = get_user_id()
groups = load_member_groups(user_id)

if not groups:
    tier = (get_user_profile(user_id) or {}).get("subscription_tier")
    if tier != "enterprise":
        st.info(tr("Groups are part of the **Enterprise** plan: several companies or divisions under one account, with people assigned to each and a group overview. [Contact us]({enterprise_url}) to set it up.").format(enterprise_url=ENTERPRISE_URL))
        st.stop()
    st.markdown(tr("Name your group to get started. Every company you own becomes "
                "part of it, and you can invite people to work across all of them."))
    with st.form("create_group"):
        name = st.text_input(tr("Group name"), placeholder=tr("e.g. Acme Group"))
        if st.form_submit_button(tr("Create group"), type="primary"):
            group, err = create_group(user_id, name)
            if group:
                st.rerun()
            st.error(err)
    st.stop()

if len(groups) > 1:
    by_id = {g["id"]: g for g in groups}
    gid = st.selectbox(tr("Group"), list(by_id), format_func=lambda i: by_id[i]["name"])
    group = by_id[gid]
else:
    group = groups[0]

my_role = group["role"]
is_admin = can_manage_people(my_role)
st.subheader(group["name"])
st.caption(tr("Your role in the group: {role_label_my_role}").format(role_label_my_role=role_label(my_role)))

# ── Overview ──────────────────────────────────────────────────────────────
companies = group_companies(group)
role_on = {c["id"]: c.get("role") for c in load_accessible_clients(user_id) or []}

st.markdown(tr("#### Companies"))
if not companies:
    st.caption(tr("No company yet. Add one on **Company profile**."))
else:
    rows = []
    with st.spinner(tr("Working out where each company stands…")):
        for c in companies:
            row = {"Company": c["company_name"], "Your role": role_label(role_on.get(c["id"]))}
            try:
                state = OV.load_state(user_id, c)
                for reg, sc in OV.headline(state).items():
                    pct = sc.get("percent")
                    row[regulation_label(reg)] = (f"{OV.band(pct)} {pct}%" if pct is not None
                                                  else "⚪ —")
                row["Open tasks"] = len(state.get("open_tasks") or [])
            except Exception as e:
                row["Open tasks"] = None
                print(f"Group overview: could not load {c['id']}: {e}")
            rows.append(row)
    cols = ["Company", "Your role"] + sorted(
        {k for r in rows for k in r} - {"Company", "Your role", "Open tasks"}) + ["Open tasks"]
    # The shared table (table_view.py): click a company to open it. It
    # replaced an st.dataframe plus an "Open a company" box and button.
    _g_hit = tv.table(
        [{"id": c["id"], "cells": {k: (None if r.get(k) in ("", "⚪ —") else r.get(k)) for k in cols},
          "actions": [{"id": "open", "label": "Open this company", "icon": "📂"}]}
         for c, r in zip(companies, rows)],
        [{"key": k, "label": k, **({"kind": "number"} if k == "Open tasks" else {})} for k in cols],
        key=f"group_{group['id']}")
    st.caption(tr("% in place per regulation, as on each company's Home page. Click a company "
               "to open it."))
    if _g_hit:
        chosen = next((c for c in companies if c["id"] == _g_hit["row"]), None)
        if chosen:
            st.session_state.selected_client = {**chosen, "role": role_on.get(chosen["id"])}
            st.switch_page("app_pages/dashboard.py")

# ── People across the group ───────────────────────────────────────────────
st.markdown(tr("#### People across the group"))
st.caption(tr("Their role applies to every company of the group, including companies "
           "added later. People on a single company are managed on **Team**. "
           "Every change is recorded in each company's Activity Log."))

with st.expander(tr("What the roles mean")):
    for _r, _label in CLIENT_ROLES.items():
        st.markdown(f"**{_label}** — {CLIENT_ROLE_HELP[_r]}")

_role_keys = list(CLIENT_ROLES)
members = list_group_members(group["id"])
if not members:
    st.caption(tr("No one else has group-wide access yet."))
for m in members:
    mc1, mc2, mc3 = st.columns([3, 2, 1])
    mc1.write(m["display_name"])
    if m["status"] != "active":
        mc1.caption(tr("Invited — not signed up yet"))
    if is_admin:
        cur = m.get("role") or "contributor"
        new_role = mc2.selectbox(tr("Role"), _role_keys, index=_role_keys.index(cur),
                                 format_func=CLIENT_ROLES.get, key=f"grole_{m['id']}",
                                 label_visibility="collapsed")
        if new_role != cur:
            ok, err = set_group_member_role(group, m["id"], new_role, user_id)
            if ok:
                load_accessible_clients.clear()
                st.rerun()
            st.error(err)
        if mc3.button(tr("Remove"), key=f"grm_{m['id']}"):
            if remove_group_member(group, m["id"], user_id):
                load_accessible_clients.clear()
                st.rerun()
    else:
        mc2.caption(role_label(m.get("role")))
        if m.get("member_user_id") == user_id and mc3.button(tr("Leave"), key=f"gleave_{m['id']}"):
            if remove_group_member(group, m["id"], user_id):
                load_accessible_clients.clear()
                st.session_state.pop("selected_client", None)
                st.rerun()

if is_admin:
    with st.form("group_invite", clear_on_submit=True):
        ic1, ic2, ic3 = st.columns([3, 2, 1])
        email = ic1.text_input(tr("Email"), label_visibility="collapsed",
                               placeholder=tr("colleague@company.com"))
        role = ic2.selectbox(tr("Role"), _role_keys, index=_role_keys.index("contributor"),
                             format_func=CLIENT_ROLES.get, label_visibility="collapsed")
        if ic3.form_submit_button(tr("Invite"), use_container_width=True):
            ok, err = invite_group_member(group, user_id, email, role)
            if ok:
                st.success(tr("Invited {email_strip} as {client_roles_role} on every company of the group.").format(email_strip=email.strip(), client_roles_role=CLIENT_ROLES[role]))
                if err:             # D-146: invited, but no email went out
                    st.warning(err)
                load_accessible_clients.clear()
            else:
                st.error(err)

    with st.expander(tr("Rename the group")):
        with st.form("rename_group"):
            new_name = st.text_input(tr("Group name"), value=group["name"])
            if st.form_submit_button(tr("Save")):
                if rename_group(group, new_name, user_id):
                    st.rerun()
