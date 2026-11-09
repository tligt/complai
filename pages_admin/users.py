"""
pages_admin/users.py — the people: accounts they belong to, their companies
and roles, invitation state, last sign-in, and the admin role.

S59 (D-151): plan, status and trial are the customer account's, changed on
the Companies page; here they are shown, read-only, for the account the
person owns or works in. Before S59 they were set here, per person.
"""

from datetime import datetime

import streamlit as st

from auth import get_user_id
from database import (
    ACCOUNT_STATUSES, ROLES, SUBSCRIPTION_TIERS, get_all_profiles, get_supabase_admin,
    load_accounts, set_user_role,
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
         " ".join(str(v) for v in r.values()).lower()]
st.caption(f"{len(shown)} user{'s' if len(shown) != 1 else ''} · click a row to open it")
event = st.dataframe(
    shown, hide_index=True, width="stretch", on_select="rerun",
    selection_mode="single-row", key="users_table",
    column_config={
        "Email": st.column_config.TextColumn(width=220),
        "Companies": st.column_config.TextColumn(width=240),
        "Last sign-in": st.column_config.DatetimeColumn(format="DD MMM YYYY, HH:mm"),
        "Created": st.column_config.DateColumn(format="DD MMM YYYY"),
    },
)
picked = (event.selection.rows if event and event.selection else []) or []
if not picked:
    st.stop()

target = next(p for p in profiles if (p.get("email") or "") == shown[picked[0]]["Email"])
is_self = target["id"] == admin_id
acc, comps = work_of(target["id"])

st.divider()
with st.container(border=True):
    st.markdown(f"**{target.get('email') or target['id']}**")
    if acc:
        st.caption(f"Account **{acc['name']}** — "
                   f"{SUBSCRIPTION_TIERS.get(acc['plan'], acc['plan'])}, "
                   f"{ACCOUNT_STATUSES.get(acc['status'], acc['status'])}"
                   + (" (owner)" if acc.get("owner_user_id") == target["id"] else " (member)"))
        st.page_link("pages_admin/companies.py", label="Change the plan on the Companies page →")
    else:
        st.caption("No account yet: this person owns no company and works in none.")

    _role_codes = list(ROLES.keys())
    _current_role = target.get("role") or "client"
    new_role = st.selectbox(
        "Role", options=_role_codes,
        index=_role_codes.index(_current_role) if _current_role in _role_codes else 0,
        format_func=lambda c: ROLES[c], key=f"role_{target['id']}",
        # There is exactly one admin account in the database today.
        # Letting it demote itself here has no in-code way back.
        disabled=is_self,
        help=("You can't change your own role." if is_self else
              "Admin gives access to this back office."),
    )
    if not is_self and st.button("Save role", key=f"save_role_{target['id']}",
                                 disabled=new_role == _current_role):
        if set_user_role(target["id"], new_role):
            st.success("Role updated.")
            st.rerun()
        else:
            st.error("Could not update role.")
