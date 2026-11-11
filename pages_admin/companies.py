"""
pages_admin/companies.py — client companies and the companies they monitor
(S59 D-151; split in D-170).

A CLIENT company is an account: RECOSA's customer, the contracting party.
Its identity is on the account and KYC applies to it alone. The companies
inside an account are MONITORED companies: the client follows them in
RECOSA, RECOSA has no business relation with them, and their details are
optional. Starter and Professional monitor one company; Advisory a
consultant's clients; Enterprise a group's.

Two tabs, one table each. Click a client company for a pop-up of its
monitored companies; its ⋮ menu opens the account (contract, subscription,
history, people) or changes the plan. Every plan or status change is a dated
period (account_periods, append-only) written by database.change_account.
"""

from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

from i18n import LANGUAGE_NAMES, account_language, person_language

import table_view as tv
from auth import get_user_id
from database import (
    ACCOUNT_STATUSES, KYC_FIELDS, SUBSCRIPTION_TIERS, TRIAL_DAYS, change_account, get_all_profiles, missing_kyc,
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
st.caption("**Client companies** are RECOSA's customers: they sign and pay, so we need to know "
           "them (KYC). **Monitored companies** are the companies a client follows in RECOSA — "
           "no business relation with us, and their details are optional.")

with st.spinner("Loading accounts…"):
    accounts = load_accounts()
    admin = get_supabase_admin()
    try:
        clients = admin.table("clients").select("*").execute().data or []
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
acc_by_id = {a["id"]: a for a in accounts}


def client_name(a: dict) -> str:
    """A client company by its legal name; the account's own name until it
    has one (accounts start named after the owner's email domain)."""
    return a.get("legal_name") or a["name"]


def kyc_cell(a: dict):
    gaps = missing_kyc(a)
    if not gaps:
        return ("✅ Complete", 0)
    if len(gaps) == len(KYC_FIELDS):
        return ("⚠️ Not given yet", 2)
    return ("⚠️ Missing " + ", ".join(gaps), 1)


def address_of(x: dict) -> str | None:
    town = " ".join(v for v in (x.get("address_postcode"), x.get("address_city")) if v)
    return (", ".join(v for v in (x.get("address_street"), town) if v)
            or (x.get("registered_address") or "").replace("\n", ", ") or None)


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
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Client companies", len(accounts))
m2.metric("Subscribed", sum(a["status"] == "active" for a in accounts))
m3.metric("On trial", sum(a["status"] == "trial" for a in accounts))
m4.metric("Trials ending within 7 days",
          sum(a["status"] == "trial" and (_dt(a.get("trial_ends_at")) or now) <= now + timedelta(days=7)
              for a in accounts))
m5.metric("Monitored companies", len(clients))

f1, f2 = st.columns([2, 3])
status_pick = f1.multiselect("Status", list(ACCOUNT_STATUSES), format_func=ACCOUNT_STATUSES.get,
                             placeholder="All")
search = (f2.text_input("Search", placeholder="Company or email") or "").lower()

tab_clients, tab_monitored = st.tabs(["Client companies", "Monitored companies"])


# ── The forms, used in the panel and in the menu's dialogs ───────────────
def subscription_form(acc: dict, where: str, trial_only: bool = False) -> None:
    with st.form(f"sub_{where}_{acc['id']}"):
        plans, statuses = list(SUBSCRIPTION_TIERS), list(ACCOUNT_STATUSES)
        if trial_only:
            tv.locked("Plan", SUBSCRIPTION_TIERS.get(acc["plan"]), "Change the plan with "
                      "\"Change plan or status\".", key=f"lp_{where}_{acc['id']}")
            new_plan, new_status = acc["plan"], "trial"
        else:
            c1, c2 = st.columns(2)
            new_plan = c1.selectbox("Plan", plans, index=plans.index(acc["plan"]),
                                    format_func=SUBSCRIPTION_TIERS.get)
            new_status = c2.selectbox("Status", statuses, index=statuses.index(acc["status"]),
                                      format_func=ACCOUNT_STATUSES.get)
        cur_end = _dt(acc.get("trial_ends_at"))
        default_end = (cur_end.date() if cur_end and cur_end.date() >= date.today()
                       else date.today() + timedelta(days=TRIAL_DAYS))
        end_day = st.date_input(
            "Trial ends" + ("" if trial_only else " (used when the status is Trial)"),
            value=default_end, min_value=date.today(), format="DD/MM/YYYY",
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
            st.session_state.acc_open = acc["id"]
            st.rerun()
        else:
            st.error(err or "Could not save.")


def contract_form(acc: dict, where: str) -> None:
    """The client company (KYC, D-170) and the contract."""
    from display import COUNTRY_LABELS
    gaps = missing_kyc(acc)
    if gaps:
        st.warning("Missing for KYC: " + ", ".join(gaps) + ". The customer is asked for these "
                   "before subscribing; you can fill them in from the contract.")
    with st.form(f"contract_{where}_{acc['id']}"):
        st.markdown("**The client company** — the contracting party")
        c1, c2 = st.columns([3, 1])
        legal_name = c1.text_input("Legal name ✱", value=acc.get("legal_name") or "")
        legal_form = c2.text_input("Legal form", value=acc.get("legal_form") or "",
                                   placeholder="SRL, SA, BV…")
        c1, c2, c3 = st.columns(3)
        countries = [None] + list(COUNTRY_LABELS)
        country = c1.selectbox("Country ✱", countries,
                               index=countries.index(acc.get("country")) if acc.get("country") in countries else 0,
                               format_func=lambda x: "—" if x is None else COUNTRY_LABELS[x])
        number = c2.text_input("Company number", value=acc.get("enterprise_number") or "")
        vat = c3.text_input("VAT number", value=acc.get("vat_number") or "")
        street = st.text_input("Street and number ✱", value=acc.get("address_street") or "")
        c1, c2, c3 = st.columns([1, 2, 2])
        postcode = c1.text_input("Postcode ✱", value=acc.get("address_postcode") or "")
        city = c2.text_input("City ✱", value=acc.get("address_city") or "")
        phone = c3.text_input("Company phone ✱", value=acc.get("phone") or "")

        st.markdown("**Contract**")
        name = st.text_input("Account name", value=acc["name"],
                             help="How the account is listed. The legal name above is what "
                                  "contracts and invoices use.")
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
        billing = st.text_input("Billing email", value=acc.get("billing_email") or "")
        # S64 (D-167): the language contract and billing mail goes out in.
        _owner_lang = person_language(profiles.get(acc.get("owner_user_id") or ""))
        _lopts = [None] + list(LANGUAGE_NAMES)
        language = st.selectbox(
            "Language we write to this account in", _lopts,
            index=_lopts.index(acc.get("language")) if acc.get("language") in _lopts else 0,
            format_func=lambda l: f"Same as the owner ({LANGUAGE_NAMES.get(_owner_lang, _owner_lang)})"
            if l is None else LANGUAGE_NAMES[l],
            help="Contract, billing and account mail. Each person is written to in their own "
                 "language (Users).")
        notes = st.text_area("Notes", value=acc.get("notes") or "", height=90)
        tv.locked("Owner", (profiles.get(acc.get("owner_user_id") or "") or {}).get("email"),
                  "The person who opened the account and manages it in the app. "
                  "Not changeable here yet.", key=f"lo_{where}_{acc['id']}")
        save = st.form_submit_button("Save", type="primary")
    if save:
        fields = {"name": name, "contact_name": contact_name, "contact_email": contact_email,
                  "contact_phone": contact_phone, "contact_user_id": contact_user,
                  "billing_email": billing, "vat_number": vat, "notes": notes,
                  "language": language, "legal_name": legal_name, "legal_form": legal_form,
                  "enterprise_number": number, "country": country, "address_street": street,
                  "address_postcode": postcode, "address_city": city, "phone": phone}
        changed = {k: v for k, v in fields.items() if (v or None) != (acc.get(k) or None)}
        if not changed:
            st.info("Nothing changed.")
        elif update_account_details(acc["id"], changed, by=admin_id):
            st.session_state.acc_notice = "Saved."
            st.session_state.acc_open = acc["id"]
            st.rerun()
        else:
            st.error("Could not save.")


def company_details(c: dict) -> None:
    """Everything known about a monitored company, grouped as on the
    client's Company profile page. Nothing here is required."""
    from display import country_label, regulations_text
    owner = (profiles.get(c.get("user_id") or "") or {})
    sections = {
        "Identity": [
            ("Company name", c.get("company_name")), ("Legal name", c.get("legal_name")),
            ("Legal form", c.get("legal_form")), ("Company number", c.get("enterprise_number")),
            ("VAT number", c.get("vat_number")), ("Country", country_label(c.get("country"))),
        ],
        "Registered office and contact": [
            ("Street and number", c.get("address_street")),
            ("Postcode and city", " ".join(x for x in (c.get("address_postcode"), c.get("address_city")) if x)),
            ("As printed in documents", (c.get("registered_address") or "").replace("\n", ", ")),
            ("Company phone", c.get("phone")),
            ("Created by", owner.get("email")),
            ("Website", c.get("website_url")),
        ],
        "Activity": [
            ("Sector", c.get("sector")), ("Employees", c.get("company_size")),
            ("Regulations", regulations_text(c.get("regulations"))),
            ("Document languages", ", ".join((x or "").upper() for x in c.get("document_languages") or [])),
            ("Markets served", ", ".join(c.get("target_markets") or [])),
            ("NIS2", {True: "In scope", False: "Not in scope"}.get(c.get("nis2_in_scope"), "Not confirmed")
             + (f" ({c.get('nis2_entity_class')})" if c.get("nis2_entity_class") else "")),
        ],
        "Data protection contacts": [
            ("Contact email for data requests", c.get("contact_email")),
            ("DPO name", c.get("dpo_name")), ("DPO email", c.get("dpo_email")),
        ],
    }
    for title, fields in sections.items():
        st.markdown(f"**{title}**")
        tv.table([{"id": f"{title}_{i}", "cells": {"field": label, "value": value or None}}
                  for i, (label, value) in enumerate(fields)],
                 [{"key": "field", "label": "Field", "sortable": False},
                  {"key": "value", "label": "Value", "sortable": False}],
                 key=f"cd_{c['id']}_{title}")
    st.caption(f"Created {_day(c.get('created_at'))} · changed {_day(c.get('updated_at'))}. "
               "The client edits these on their Company profile page. Nothing here is required: "
               "RECOSA has no relation with a monitored company.")


MONITORED_COLUMNS = [
    {"key": "name", "label": "Company"}, {"key": "legal", "label": "Legal name"},
    {"key": "country", "label": "Country"}, {"key": "number", "label": "Company number"},
    {"key": "vat", "label": "VAT"}, {"key": "address", "label": "Address"},
    {"key": "phone", "label": "Phone"}, {"key": "docs", "label": "Documents in"},
    {"key": "regs", "label": "Regulations"}, {"key": "created", "label": "Added", "kind": "date"},
]


def monitored_cells(c: dict) -> dict:
    return {
        "name": c.get("company_name"), "legal": c.get("legal_name"), "country": c.get("country"),
        "number": c.get("enterprise_number"), "vat": c.get("vat_number"),
        "address": address_of(c), "phone": c.get("phone"),
        "docs": ", ".join((x or "").upper() for x in c.get("document_languages") or []) or None,
        "regs": ", ".join(c.get("regulations") or []) or None,
        "created": _dt(c.get("created_at")),
    }


@st.dialog("Monitored companies", width="large")
def monitored_dialog(acc: dict) -> None:
    """D-170: a client company's monitored companies, in a pop-up."""
    comps = companies_of.get(acc["id"], [])
    st.markdown(f"**{client_name(acc)}** · {SUBSCRIPTION_TIERS.get(acc['plan'], acc['plan'])} · "
                f"{ACCOUNT_STATUSES.get(acc['status'], acc['status'])}")
    st.caption(f"{len(comps)} monitored compan{'y' if len(comps) == 1 else 'ies'}. Click one for "
               "everything we have on it.")
    sel_key = f"mon_sel_{acc['id']}"
    hit = tv.table([{"id": c["id"], "cells": monitored_cells(c),
                     "actions": [{"id": "open", "label": "All details", "icon": "📂"}]} for c in comps],
                   MONITORED_COLUMNS, key=f"mon_{acc['id']}", sort=("name", "asc"),
                   current=st.session_state.get(sel_key), empty="This client monitors no company yet.")
    if hit:
        st.session_state[sel_key] = hit["row"]
    sel = next((c for c in comps if c["id"] == st.session_state.get(sel_key)), None)
    if sel:
        st.divider()
        st.markdown(f"#### {sel.get('company_name')}")
        company_details(sel)
    if st.button("Open the client company's account", icon="📂", key=f"mon_open_{acc['id']}"):
        st.session_state.acc_open = acc["id"]
        st.rerun()


@st.dialog("Change plan or status", width="large")
def plan_dialog(acc: dict) -> None:
    st.caption(client_name(acc))
    subscription_form(acc, "dlg")


@st.dialog("Extend the trial")
def trial_dialog(acc: dict) -> None:
    st.caption(client_name(acc))
    subscription_form(acc, "dlgt", trial_only=True)


@st.dialog("Client company and contract", width="large")
def contract_dialog(acc: dict) -> None:
    st.caption(client_name(acc))
    contract_form(acc, "dlg")


@st.dialog("Monitored company", width="large")
def company_dialog(c: dict) -> None:
    acc = acc_by_id.get(c.get("account_id") or "")
    st.markdown(f"**{c.get('company_name')}**" + (f" · monitored by {client_name(acc)}" if acc else ""))
    company_details(c)


# ══ Client companies ══════════════════════════════════════════════════════
with tab_clients:
    rows, by_id = [], {}
    for a in accounts:
        comps = companies_of.get(a["id"], [])
        ppl = people_of(a)
        hay = " ".join([a["name"], a.get("legal_name") or "", *(c["company_name"] for c in comps),
                        *(p["email"] for p in ppl), a.get("contact_email") or "",
                        a.get("contact_name") or ""]).lower()
        if status_pick and a["status"] not in status_pick:
            continue
        if search and search not in hay:
            continue
        by_id[a["id"]] = a
        rows.append({"id": a["id"], "cells": {
            "name": client_name(a),
            "plan": SUBSCRIPTION_TIERS.get(a["plan"], a["plan"]),
            "status": ACCOUNT_STATUSES.get(a["status"], a["status"]),
            "trial": _dt(a.get("trial_ends_at")) if a["status"] in ("trial", "expired") else None,
            "since": _dt(first_active.get(a["id"])),
            "monitored": len(comps),
            # D-170: KYC of the client company itself, not of what it monitors.
            "kyc": kyc_cell(a),
            "people": len(ppl),
            "contact": a.get("contact_name") or a.get("contact_email"),
            # S64 (D-167): the language we write to the account in.
            "language": (lambda l_set: LANGUAGE_NAMES.get(l_set[0], l_set[0]) + ("" if l_set[1] else " (owner's)"))(
                account_language(a, profiles.get(a.get("owner_user_id") or ""))),
            "opened": _dt(a["created_at"]),
        }, "actions": [
            {"id": "open", "label": "Monitored companies", "icon": "🏢"},
            {"id": "account", "label": "Open the account", "icon": "📂"},
            {"id": "plan", "label": "Change plan or status", "icon": "✏️"},
            {"id": "trial", "label": "Extend the trial", "icon": "⏳",
             "disabled": None if a["status"] in ("trial", "expired")
             else "Only for an account on trial or whose trial ended"},
            {"id": "contract", "label": "Edit client company and contract", "icon": "🧾"},
        ]})

    st.caption(f"{len(rows)} client compan{'y' if len(rows) == 1 else 'ies'} · click a row for its "
               "monitored companies, or use its ⋮ menu · click a column title to sort")
    hit = tv.table(rows, [
        {"key": "name", "label": "Client company"}, {"key": "plan", "label": "Plan"},
        {"key": "status", "label": "Status"}, {"key": "trial", "label": "Trial ends", "kind": "date"},
        {"key": "since", "label": "Customer since", "kind": "date"},
        {"key": "monitored", "label": "Monitored", "kind": "number"}, {"key": "kyc", "label": "KYC"},
        {"key": "people", "label": "People", "kind": "number"},
        {"key": "contact", "label": "Contract contact"}, {"key": "language", "label": "Language"},
        {"key": "opened", "label": "Opened", "kind": "date"},
    ], key="accounts", sort=("opened", "desc"), current=st.session_state.get("acc_open"),
        empty="No client company matches.")

    if hit and hit["row"] in by_id:
        if hit["action"] == "account":
            st.session_state.acc_open = hit["row"]
        else:
            {"open": monitored_dialog, "plan": plan_dialog, "trial": trial_dialog,
             "contract": contract_dialog}.get(hit["action"], lambda a: None)(by_id[hit["row"]])

    acc = by_id.get(st.session_state.get("acc_open") or "")
    if acc:
        # ── One client company ───────────────────────────────────────────
        tv.focus("accounts")
        st.divider()
        st.subheader(client_name(acc))
        st.caption(f"{SUBSCRIPTION_TIERS.get(acc['plan'], acc['plan'])} · "
                   f"{ACCOUNT_STATUSES.get(acc['status'], acc['status'])}"
                   + (f" until {_day(acc.get('trial_ends_at'))}" if acc["status"] == "trial" else "")
                   + f" · opened {_day(acc['created_at'])}"
                   + f" · {len(companies_of.get(acc['id'], []))} monitored")

        notice = st.session_state.pop("acc_notice", None)
        if notice:
            st.success(notice)

        t_contract, t_sub, t_hist, t_people = st.tabs(
            ["Client company and contract", "Subscription", "History", "People"])

        with t_contract:
            contract_form(acc, "tab")

        with t_sub:
            subscription_form(acc, "tab")

        with t_hist:
            periods = load_account_periods(acc["id"])
            tv.table([{"id": p["id"], "cells": {
                "from": _dt(p["starts_at"]), "to": _dt(p.get("ends_at")),
                "plan": SUBSCRIPTION_TIERS.get(p["plan"], p["plan"]),
                "status": ACCOUNT_STATUSES.get(p["status"], p["status"]),
                "trial": _dt(p.get("trial_ends_at")), "note": p.get("note"),
                "by": (profiles.get(p.get("changed_by") or "") or {}).get("email"),
            }} for p in periods], [
                {"key": "from", "label": "From", "kind": "datetime"},
                {"key": "to", "label": "To (empty: current)", "kind": "datetime"},
                {"key": "plan", "label": "Plan"}, {"key": "status", "label": "Status"},
                {"key": "trial", "label": "Trial ends", "kind": "date"},
                {"key": "note", "label": "Note"}, {"key": "by", "label": "By"},
            ], key=f"hist_{acc['id']}", sort=("from", "desc"), empty="No history recorded.")

        with t_people:
            ppl = people_of(acc)
            tv.table([{"id": p.get("id") or p["email"], "cells": {
                "email": p["email"], "role": p["role"],
                "status": {"active": "Active", "pending": "Invited, not signed in yet"}.get(
                    p.get("status"), p.get("status")),
                "companies": "All" if p["companies"] == ["all"] else ", ".join(sorted(p["companies"])),
                "language": LANGUAGE_NAMES.get(person_language(profiles.get(p.get("id") or "")))
                            if p.get("id") else None,
            }} for p in ppl], [
                {"key": "email", "label": "Email"}, {"key": "role", "label": "Role"},
                {"key": "language", "label": "Language"},
                {"key": "status", "label": "Status"}, {"key": "companies", "label": "Monitored companies"},
            ], key=f"people_{acc['id']}", sort=("email", "asc"), empty="Nobody yet.")

# ══ Monitored companies ═══════════════════════════════════════════════════
with tab_monitored:
    st.caption("Every company a client follows in RECOSA, with what we know about it. The details "
               "are the client's to fill in; none is required.")
    mrows = []
    for c in clients:
        acc = acc_by_id.get(c.get("account_id") or "")
        if status_pick and (not acc or acc["status"] not in status_pick):
            continue
        hay = " ".join([c.get("company_name") or "", c.get("legal_name") or "",
                        client_name(acc) if acc else ""]).lower()
        if search and search not in hay:
            continue
        mrows.append({"id": c["id"], "cells": {**monitored_cells(c),
                                               "client": client_name(acc) if acc else None},
                      "actions": [{"id": "open", "label": "All details", "icon": "📂"}]})
    st.caption(f"{len(mrows)} monitored compan{'y' if len(mrows) == 1 else 'ies'} · click one for all "
               "its details")
    mhit = tv.table(mrows, MONITORED_COLUMNS[:1] + [{"key": "client", "label": "Client company"}]
                    + MONITORED_COLUMNS[1:], key="monitored", sort=("name", "asc"),
                    empty="No monitored company matches.")
    if mhit:
        _c = next((c for c in clients if c["id"] == mhit["row"]), None)
        if _c:
            company_dialog(_c)
