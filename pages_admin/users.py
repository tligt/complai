"""
pages_admin/users.py — the people: accounts they belong to, their companies
and roles, invitation state, last sign-in, and the admin role.

S59 (D-151): plan, status and trial are the customer account's, changed on
the Companies page; here they are shown, read-only, for the account the
person owns or works in. Before S59 they were set here, per person.
"""

from datetime import datetime

import streamlit as st

import table_view as tv
from auth import get_user_id
from database import (
    ACCOUNT_STATUSES, ROLES, SUBSCRIPTION_TIERS, get_all_profiles, get_supabase_admin,
    load_accounts, resend_invite, set_user_role,
)

SOURCES = {"invite": "Invited", "website_check": "Website check", "nis2_quiz": "NIS2 check",
           "gdpr_quiz": "GDPR check", "ai_quiz": "AI Act check", "website": "Website sign-up",
           "direct": "Direct sign-up"}

st.title("Users")
st.caption("People, the accounts and companies they work in, and their role. "
           "Plans are changed on the Companies page.")

admin_id = get_user_id()
admin = get_supabase_admin()

with st.spinner("Loading users…"):
    profiles = get_all_profiles()
    accounts = {a["id"]: a for a in load_accounts()}
    try:
        clients = {c["id"]: c for c in admin.table("clients")
                   .select("id, company_name, user_id, account_id").execute().data or []}
        members = admin.table("workspace_members") \
            .select("client_id, member_user_id, role, status").execute().data or []
    except Exception as e:
        st.error(f"Could not load companies: {e}")
        clients, members = {}, []
    last_sign_in: dict[str, str] = {}
    try:
        page = 1
        while True:
            batch = admin.auth.admin.list_users(page=page, per_page=200)
            for u in batch:
                last_sign_in[u.id] = getattr(u, "last_sign_in_at", None)
            if len(batch) < 200:
                break
            page += 1
    except Exception as e:
        print(f"Could not read sign-ins: {e}")

if not profiles:
    st.info("No accounts found.")
    st.stop()

owned_account = {a["owner_user_id"]: a for a in accounts.values() if a.get("owner_user_id")}


def _when(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def work_of(uid: str) -> tuple[dict | None, list[str]]:
    """(the account whose plan applies to this person, their companies with roles)."""
    comps, acc = [], owned_account.get(uid)
    for c in clients.values():
        if c.get("user_id") == uid:
            comps.append(f"{c['company_name']} (owner)")
    for m in members:
        c = clients.get(m["client_id"])
        if m.get("member_user_id") == uid and c and m.get("status") != "removed":
            comps.append(f"{c['company_name']} ({(m.get('role') or '').replace('_', ' ')})")
            acc = acc or accounts.get(c.get("account_id"))
    return acc, comps


rows = []
for p in profiles:
    acc, comps = work_of(p["id"])
    signed = _when(last_sign_in.get(p["id"]))
    rows.append({
        "_id": p["id"],
        "Email": p.get("email") or "",
        "Name": p.get("full_name") or "",
        "Role": ROLES.get(p.get("role") or "", p.get("role") or ""),
        "Account": (acc or {}).get("name") or "—",
        "Plan": SUBSCRIPTION_TIERS.get((acc or {}).get("plan"), "—") if acc else "—",
        "Status": ACCOUNT_STATUSES.get((acc or {}).get("status"), "—") if acc else "—",
        "Companies": ", ".join(comps) or "—",
        "Last sign-in": signed,
        "Signed in": "Yes" if signed else "Never (invitation pending)" if p.get("signup_source") == "invite" else "Never",
        "Source": SOURCES.get(p.get("signup_source") or "", p.get("signup_source") or "—"),
        "Created": _when(p.get("created_at")),
    })

search = st.text_input("Search", placeholder="Email, name, account or company")
shown = [r for r in rows if not search or search.lower() in
         " ".join(str(v) for k, v in r.items() if k != "_id").lower()]
by_id = {p["id"]: p for p in profiles}

COLS = [("Email", "email", None), ("Name", "name", None), ("Role", "role", None),
        ("Account", "account", None), ("Plan", "plan", None), ("Status", "status", None),
        ("Companies", "companies", None), ("Last sign-in", "last", "datetime"),
        ("Source", "source", None), ("Created", "created", "date")]


def _actions(uid: str) -> list[dict]:
    p = by_id[uid]
    acc, comps = work_of(uid)
    pending = p.get("signup_source") == "invite" and not last_sign_in.get(uid)
    return [
        {"id": "open", "label": "Open", "icon": "📂"},
        {"id": "role", "label": "Change role", "icon": "🛡️",
         "disabled": "You can't change your own role" if uid == admin_id else None},
        {"id": "account", "label": "Open their account on Companies", "icon": "🏢",
         "disabled": None if acc else "No account: owns no company and works in none"},
        {"id": "resend", "label": "Send the invitation again", "icon": "✉️",
         "disabled": None if pending and comps else "Only for an invited person who never signed in"},
    ]


st.caption(f"{len(shown)} user{'s' if len(shown) != 1 else ''} · click a row to open it, "
           "or use its ⋮ menu · click a column title to sort")
hit = tv.table(
    [{"id": r["_id"], "cells": {k: (None if r[label] in ("—", "") else r[label]) for label, k, _ in COLS},
      "actions": _actions(r["_id"])} for r in shown],
    [{"key": k, "label": label, **({"kind": kind} if kind else {})} for label, k, kind in COLS],
    key="users", sort=("created", "desc"), current=st.session_state.get("user_open"),
    empty="Nobody matches.")


def role_form(target: dict, where: str) -> None:
    is_self = target["id"] == admin_id
    _role_codes = list(ROLES.keys())
    _current_role = target.get("role") or "client"
    if is_self:
        # There is exactly one admin account in the database today. Letting
        # it demote itself here has no in-code way back.
        tv.locked("Role", ROLES.get(_current_role, _current_role), "You can't change your own role.",
                  key=f"lr_{where}_{target['id']}")
        return
    new_role = st.selectbox(
        "Role", options=_role_codes,
        index=_role_codes.index(_current_role) if _current_role in _role_codes else 0,
        format_func=lambda c: ROLES[c], key=f"role_{where}_{target['id']}",
        help="Admin gives access to this back office.")
    if st.button("Save role", key=f"save_role_{where}_{target['id']}", type="primary",
                 disabled=new_role == _current_role):
        if set_user_role(target["id"], new_role):
            st.session_state.user_notice = "Role updated."
            st.rerun()
        else:
            st.error("Could not update role.")


@st.dialog("Change role")
def role_dialog(target: dict) -> None:
    st.caption(target.get("email") or "")
    role_form(target, "dlg")


@st.dialog("Send the invitation again")
def resend_dialog(target: dict) -> None:
    acc, comps = work_of(target["id"])
    place = comps[0].rsplit(" (", 1)[0] if comps else "RECOSA"
    st.write(f"A new link to set a password goes to **{target.get('email')}**, "
             f"for **{place}**.")
    if st.button("Send", type="primary"):
        ok, err = resend_invite(target.get("email") or "", place, admin_id)
        if ok:
            st.session_state.user_notice = f"Invitation sent again to {target.get('email')}."
            st.rerun()
        else:
            st.error(err or "Could not send it.")


if hit and hit["row"] in by_id:
    target = by_id[hit["row"]]
    st.session_state.user_open = hit["row"]
    if hit["action"] == "role":
        role_dialog(target)
    elif hit["action"] == "resend":
        resend_dialog(target)
    elif hit["action"] == "account":
        acc, _ = work_of(target["id"])
        if acc:
            st.session_state.acc_open = acc["id"]
            st.switch_page("pages_admin/companies.py")

notice = st.session_state.pop("user_notice", None)
if notice:
    st.success(notice)

target = by_id.get(st.session_state.get("user_open") or "")
if not target:
    st.stop()
acc, comps = work_of(target["id"])

st.divider()
with st.container(border=True):
    st.markdown(f"**{target.get('email') or target['id']}**")
    if acc:
        st.caption(f"Account **{acc['name']}** — "
                   f"{SUBSCRIPTION_TIERS.get(acc['plan'], acc['plan'])}, "
                   f"{ACCOUNT_STATUSES.get(acc['status'], acc['status'])}"
                   + (" (owner)" if acc.get("owner_user_id") == target["id"] else " (member)"))
        tv.locked("Plan", SUBSCRIPTION_TIERS.get(acc["plan"], acc["plan"]),
                  "The plan is the account's: change it on the Companies page.",
                  key=f"lp_{target['id']}")
    else:
        st.caption("No account yet: this person owns no company and works in none.")
    st.caption("Companies: " + (", ".join(comps) or "none"))
    role_form(target, "panel")
