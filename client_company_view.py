"""
client_company_view.py — D-170. The customer's own company: who signs and
pays RECOSA.

The client company is the account. Its identity (KYC) is asked before a
paid plan is requested — on the subscribe page and on Account — and never
for the trial. The companies the account follows in RECOSA are monitored
companies, filled in on their Company profile; this form can copy from one
of them when the customer monitors their own company.

Only the account's owner sees it: an invited colleague works under someone
else's account.
"""

from __future__ import annotations

import streamlit as st

from i18n import tr
from database import KYC_FIELDS, missing_kyc, update_account_details

_FIELDS = ("legal_name", "legal_form", "country", "enterprise_number", "vat_number",
           "address_street", "address_postcode", "address_city", "phone")


def _key(acc: dict, f: str) -> str:
    return f"cc_{acc['id']}_{f}"


def _companies(acc: dict) -> list[dict]:
    try:
        from database import get_supabase_admin
        return (get_supabase_admin().table("clients").select("*")
                .eq("account_id", acc["id"]).order("created_at").execute().data or [])
    except Exception as e:
        print(f"Could not load the account's companies: {e}")
        return []


def _copy_from(acc: dict, c: dict) -> None:
    vals = {"legal_name": c.get("legal_name") or c.get("company_name"), "legal_form": c.get("legal_form"),
            "country": c.get("country"), "enterprise_number": c.get("enterprise_number"),
            "vat_number": c.get("vat_number"), "address_street": c.get("address_street"),
            "address_postcode": c.get("address_postcode"), "address_city": c.get("address_city"),
            "phone": c.get("phone")}
    if not vals["address_street"] and c.get("registered_address"):
        lines = [x.strip() for x in str(c["registered_address"]).splitlines() if x.strip()]
        if len(lines) > 1:
            vals["address_street"] = " ".join(lines[:-1])
            vals["address_postcode"], _, vals["address_city"] = lines[-1].partition(" ")
    for f, v in vals.items():
        if v:
            st.session_state[_key(acc, f)] = v


def render_client_company(acc: dict, *, user_id: str) -> bool:
    """The form. Returns True when the client company is complete."""
    from display import COUNTRY_LABELS
    gaps = missing_kyc(acc)
    st.markdown(tr("**Your company** — the one that subscribes to RECOSA"))
    if gaps:
        st.caption(tr("Who signs with us and receives the invoices. We need it before you choose "
                      "a plan; the free trial does not."))
    comps = _companies(acc)
    if comps and gaps:
        c1, c2 = st.columns([3, 1])
        pick = c1.selectbox(tr("Same as a company you follow in RECOSA?"), [None] + [c["id"] for c in comps],
                            format_func=lambda i: tr("— no, I'll fill it in —") if i is None
                            else next(c["company_name"] for c in comps if c["id"] == i),
                            key=f"cc_pick_{acc['id']}")
        c2.write("")
        if c2.button(tr("Copy its details"), disabled=pick is None, key=f"cc_copy_{acc['id']}"):
            _copy_from(acc, next(c for c in comps if c["id"] == pick))
            st.rerun()

    for f in _FIELDS:
        st.session_state.setdefault(_key(acc, f), acc.get(f) or ("" if f != "country" else None))
    with st.form(f"cc_form_{acc['id']}"):
        c1, c2 = st.columns([3, 1])
        c1.text_input(tr("Legal name ✱"), key=_key(acc, "legal_name"))
        c2.text_input(tr("Legal form"), key=_key(acc, "legal_form"), placeholder=tr("SRL, SA, SAS…"))
        c1, c2, c3 = st.columns(3)
        countries = [None] + list(COUNTRY_LABELS)
        if st.session_state.get(_key(acc, "country")) not in countries:
            st.session_state[_key(acc, "country")] = None
        c1.selectbox(tr("Country ✱"), countries, key=_key(acc, "country"),
                     format_func=lambda x: "—" if x is None else tr(COUNTRY_LABELS[x]))
        c2.text_input(tr("Company number"), key=_key(acc, "enterprise_number"))
        c3.text_input(tr("VAT number"), key=_key(acc, "vat_number"))
        st.text_input(tr("Street and number ✱"), key=_key(acc, "address_street"))
        c1, c2, c3 = st.columns([1, 2, 2])
        c1.text_input(tr("Postcode ✱"), key=_key(acc, "address_postcode"))
        c2.text_input(tr("City ✱"), key=_key(acc, "address_city"))
        c3.text_input(tr("Company phone ✱"), key=_key(acc, "phone"))
        save = st.form_submit_button(tr("Save my company"), type="primary" if gaps else "secondary")
    if save:
        vals = {f: st.session_state.get(_key(acc, f)) for f in _FIELDS}
        if vals.get("vat_number"):
            vals["vat_number"] = vals["vat_number"].replace(" ", "").replace(".", "").upper()
        still = missing_kyc(vals)
        if still:
            st.warning(tr("Please fill in: {fields}.").format(
                fields=", ".join(tr(x) for x in still)))
            return False
        changed = {f: v for f, v in vals.items() if (v or None) != (acc.get(f) or None)}
        if changed and not update_account_details(acc["id"], changed, by=user_id):
            st.error(tr("Could not save."))
            return False
        st.session_state["cc_saved"] = True
        st.rerun()
    if st.session_state.pop("cc_saved", False):
        st.success(tr("Saved."))
    return not gaps


def kyc_labels() -> list[str]:
    """For the catalogue: the field names shown in "Please fill in"."""
    return list(KYC_FIELDS.values())
