"""
pages_admin/companies.py — customer accounts (S59, D-151): the companies
that have a RECOSA subscription, their plan and status, the history of every
change, their companies and people, and the contract contact.

An account is the contracting party. Starter and Professional hold one
company; Advisory a consultant's client companies; Enterprise a group's.
Every plan or status change is a dated period (account_periods, append-only)
written by database.change_account.

Click a row to open it. (The ⋮ row menu comes with the shared table
component — BO review, points 4–6.)
"""

from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

from auth import get_user_id
from database import (
    ACCOUNT_STATUSES, SUBSCRIPTION_TIERS, TRIAL_DAYS, change_account, get_all_profiles,
    get_supabase_admin, load_account_periods, load_accounts, update_account_details,
)

admin_id = get_user_id()


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _day(v: str | None) -> str:
    d = _dt(v)
    return d.strftime("%d %b %Y") if d else ""


st.title("Companies")
st.caption("Customer accounts: plan, status, history, companies, people and contract contact.")

with st.spinner("Loading accounts…"):
    accounts = load_accounts()
    admin = get_supabase_admin()
    try:
        clients = admin.table("clients").select("id, company_name, user_id, account_id").execute().data or []
        members = admin.table("workspace_members") \
            .select("client_id, member_user_id, invited_email, role, status").execute().data or []
        first_active = {}
        for p in admin.table("account_periods").select("account_id, starts_at") \
                .eq("status", "active").order("starts_at").execute().data or []:
            first_active.setdefault(p["account_id"], p["starts_at"])
    except Exception as e:
        st.error(f"Could not load the companies: {e}")
        clients, members, first_active = [], [], {}
    profiles = {p["id"]: p for p in get_all_profiles() or []}

if not accounts:
    st.info("No customer accounts yet.")
    st.stop()

companies_of: dict[str, list[dict]] = {}
for c in clients:
    if c.get("account_id"):
        companies_of.setdefault(c["account_id"], []).append(c)


def people_of(acc: dict) -> list[dict]:
    """The owner, then everyone invited to one of its companies."""
    out = {}
    if acc.get("owner_user_id"):
        out[acc["owner_user_id"]] = {"id": acc["owner_user_id"], "role": "Owner",
                                     "status": "active", "companies": ["all"]}
    names = {c["id"]: c["company_name"] for c in companies_of.get(acc["id"], [])}
    for m in members:
        if m["client_id"] not in names or m.get("status") == "removed":
            continue
        key = m.get("member_user_id") or m.get("invited_email")
        e = out.setdefault(key, {"id": m.get("member_user_id"), "email": m.get("invited_email"),
                                 "role": (m.get("role") or "").replace("_", " ").capitalize(),
                                 "status": m.get("status"), "companies": []})
        if e["companies"] != ["all"]:
            e["companies"].append(names[m["client_id"]])
    for e in out.values():
        e["email"] = (profiles.get(e.get("id") or "") or {}).get("email") or e.get("email") or ""
    return list(out.values())


# ── Overview ──────────────────────────────────────────────────────────────
now = datetime.now(timezone.utc)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Accounts", len(accounts))
m2.metric("Subscribed", sum(a["status"] == "active" for a in accounts))
m3.metric("On trial", sum(a["status"] == "trial" for a in accounts))
m4.metric("Trials ending within 7 days",
          sum(a["status"] == "trial" and (_dt(a.get("trial_ends_at")) or now) <= now + timedelta(days=7)
              for a in accounts))

f1, f2 = st.columns([2, 3])
status_pick = f1.multiselect("Status", list(ACCOUNT_STATUSES), format_func=ACCOUNT_STATUSES.get,
                             placeholder="All")
search = f2.text_input("Search", placeholder="Account, company or email")

rows = []
for a in accounts:
    comps = companies_of.get(a["id"], [])
    ppl = people_of(a)
    hay = " ".join([a["name"], *(c["company_name"] for c in comps), *(p["email"] for p in ppl),
                    a.get("contact_email") or "", a.get("contact_name") or ""]).lower()
    if status_pick and a["status"] not in status_pick:
        continue
    if search and search.lower() not in hay:
        continue
    rows.append((a, {
        "Account": a["name"],
        "Plan": SUBSCRIPTION_TIERS.get(a["plan"], a["plan"]),
        "Status": ACCOUNT_STATUSES.get(a["status"], a["status"]),
        "Trial ends": _dt(a.get("trial_ends_at")) if a["status"] in ("trial", "expired") else None,
        "Customer since": _dt(first_active.get(a["id"])),
        "Companies": ", ".join(sorted(c["company_name"] for c in comps)) or "—",
        "People": len(ppl),
        "Contract contact": a.get("contact_name") or a.get("contact_email") or "—",
        "Opened": _dt(a["created_at"]),
    }))

st.caption(f"{len(rows)} account{'s' if len(rows) != 1 else ''} · click a row to open it")
event = st.dataframe(
    [r for _, r in rows], hide_index=True, width="stretch",
    on_select="rerun", selection_mode="single-row", key="accounts_table",
    column_config={
        "Account": st.column_config.TextColumn(width=180),
        "Trial ends": st.column_config.DateColumn(format="DD MMM YYYY"),
        "Customer since": st.column_config.DateColumn(format="DD MMM YYYY"),
        "Opened": st.column_config.DateColumn(format="DD MMM YYYY"),
        "Companies": st.column_config.TextColumn(width=220),
        "People": st.column_config.NumberColumn(width=70),
    },
)
picked = (event.selection.rows if event and event.selection else []) or []
if not picked:
    st.stop()
acc = rows[picked[0]][0]

# ── One account ───────────────────────────────────────────────────────────
st.divider()
st.subheader(acc["name"])
st.caption(f"{SUBSCRIPTION_TIERS.get(acc['plan'], acc['plan'])} · "
           f"{ACCOUNT_STATUSES.get(acc['status'], acc['status'])}"
           + (f" until {_day(acc.get('trial_ends_at'))}" if acc["status"] == "trial" else "")
           + f" · opened {_day(acc['created_at'])}")

notice = st.session_state.pop("acc_notice", None)
if notice:
    st.success(notice)

t_sub, t_hist, t_people, t_contract = st.tabs(
    ["Subscription", "History", "Companies and people", "Contract and billing"])

with t_sub:
    with st.form(f"sub_{acc['id']}"):
        c1, c2 = st.columns(2)
        plans = list(SUBSCRIPTION_TIERS)
        new_plan = c1.selectbox("Plan", plans, index=plans.index(acc["plan"]),
                                format_func=SUBSCRIPTION_TIERS.get)
        statuses = list(ACCOUNT_STATUSES)
        new_status = c2.selectbox("Status", statuses, index=statuses.index(acc["status"]),
                                  format_func=ACCOUNT_STATUSES.get)
        cur_end = _dt(acc.get("trial_ends_at"))
        default_end = (cur_end.date() if cur_end and cur_end.date() >= date.today()
                       else date.today() + timedelta(days=TRIAL_DAYS))
        end_day = st.date_input(
            "Trial ends (used when the status is Trial)", value=default_end,
            min_value=date.today(), format="DD/MM/YYYY",
            help=f"{TRIAL_DAYS} days by default. A later date extends the trial.")
        note = st.text_input("Note for the history",
                             placeholder="e.g. upgraded on request, trial extended a week")
        go = st.form_submit_button("Save", type="primary")
    st.caption("Every change is kept in the history with its date, who made it and the note. "
               "Moving from Advisory or Enterprise to a one-company plan is refused while the "
               "account holds several companies.")
    if go:
        ends = datetime.combine(end_day, time(23, 59), tzinfo=timezone.utc)
        ok, err = change_account(acc["id"], plan=new_plan, status=new_status,
                                 trial_ends_at=ends if new_status == "trial" else None,
                                 note=note, by=admin_id)
        if ok:
            st.session_state.acc_notice = "Saved."
            st.rerun()
        else:
            st.error(err or "Could not save.")

with t_hist:
    periods = load_account_periods(acc["id"])
    if not periods:
        st.info("No history recorded.")
    else:
        st.dataframe([{
            "From": _dt(p["starts_at"]),
            "To": _dt(p.get("ends_at")),
            "Plan": SUBSCRIPTION_TIERS.get(p["plan"], p["plan"]),
            "Status": ACCOUNT_STATUSES.get(p["status"], p["status"]),
            "Trial ends": _dt(p.get("trial_ends_at")),
            "Note": p.get("note") or "",
            "By": (profiles.get(p.get("changed_by") or "") or {}).get("email") or "—",
        } for p in periods], hide_index=True, width="stretch", column_config={
            "From": st.column_config.DatetimeColumn(format="DD MMM YYYY, HH:mm"),
            "To": st.column_config.DatetimeColumn(format="DD MMM YYYY, HH:mm", help="Empty: current"),
            "Trial ends": st.column_config.DateColumn(format="DD MMM YYYY"),
            "Note": st.column_config.TextColumn(width="large"),
        })

with t_people:
    comps = companies_of.get(acc["id"], [])
    st.markdown(f"**Companies ({len(comps)})**")
    st.write(", ".join(sorted(c["company_name"] for c in comps)) or "None yet.")
    ppl = people_of(acc)
    st.markdown(f"**People ({len(ppl)})**")
    st.dataframe([{
        "Email": p["email"], "Role": p["role"],
        "Status": {"active": "Active", "pending": "Invited, not signed in yet"}.get(p.get("status"), p.get("status") or ""),
        "Companies": "All" if p["companies"] == ["all"] else ", ".join(sorted(p["companies"])),
    } for p in ppl], hide_index=True, width="stretch")

with t_contract:
    with st.form(f"contract_{acc['id']}"):
        name = st.text_input("Account name", value=acc["name"],
                             help="The customer, i.e. the contracting party.")
        c1, c2, c3 = st.columns(3)
        contact_name = c1.text_input("Contract contact", value=acc.get("contact_name") or "")
        contact_email = c2.text_input("Contact email", value=acc.get("contact_email") or "")
        contact_phone = c3.text_input("Contact phone", value=acc.get("contact_phone") or "")
        ppl_ids = [p["id"] for p in people_of(acc) if p.get("id")]
        cur = acc.get("contact_user_id")
        opts = [None] + ppl_ids + ([cur] if cur and cur not in ppl_ids else [])
        contact_user = st.selectbox(
            "Contact is also a user (optional)", opts, index=opts.index(cur) if cur in opts else 0,
            format_func=lambda u: "— not a user —" if u is None
            else (profiles.get(u) or {}).get("email") or u[:8])
        c4, c5 = st.columns(2)
        billing = c4.text_input("Billing email", value=acc.get("billing_email") or "")
        vat = c5.text_input("VAT number", value=acc.get("vat_number") or "")
        notes = st.text_area("Notes", value=acc.get("notes") or "", height=90)
        save = st.form_submit_button("Save", type="primary")
    if save:
        fields = {"name": name, "contact_name": contact_name, "contact_email": contact_email,
                  "contact_phone": contact_phone, "contact_user_id": contact_user,
                  "billing_email": billing, "vat_number": vat, "notes": notes}
        changed = {k: v for k, v in fields.items() if (v or None) != (acc.get(k) or None)}
        if not changed:
            st.info("Nothing changed.")
        elif update_account_details(acc["id"], changed, by=admin_id):
            st.session_state.acc_notice = "Saved."
            st.rerun()
        else:
            st.error("Could not save.")
