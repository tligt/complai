"""
app_pages/company.py — Company profile (usability audit batch 2, H9).

The one place to edit a company: identity, regulations, languages, website,
contacts. Every other page reads these from the clients row — Documents
prefills its form from them, Chat and the obligations register scope on the
regulations. Before this page there was nowhere to edit a company once
created: Profile listed companies, Chat's sidebar only created them, and
document_languages could not be set at all.

NIS2 scope stays on Obligations, next to the obligations it changes; this
page links there.
"""

import streamlit as st

from active_client import get_active_client
from auth import get_user_id
from cached_reads import load_accessible_clients, load_clients
from client_setup import COUNTRY_OPTIONS, SECTOR_OPTIONS, SIZE_OPTIONS, REGULATION_OPTIONS
from database import update_client_fields
from display import country_label, regulation_label, regulations_text
from tier_gates import client_limit_reached, upsell_dialog

DOC_LANGUAGES = {"en": "English", "fr": "French", "nl": "Dutch", "de": "German"}

st.title("Company profile")
st.caption("Who the company is and what applies to it. Documents, obligations "
           "and the assistant all read from here.")

user_id = get_user_id()
clients = load_accessible_clients(user_id) or []

if clients:
    client = get_active_client(user_id)
    cid = client["id"]
    k = lambda name: f"co_{name}_{cid}"

    def _opt_index(options, value, default=0):
        return options.index(value) if value in options else default

    with st.form(f"company_form_{cid}"):
        st.markdown("**Identity**")
        c1, c2 = st.columns(2)
        name = c1.text_input("Company name ✱", value=client.get("company_name") or "", key=k("name"))
        legal_name = c2.text_input("Legal name", value=client.get("legal_name") or "",
                                   key=k("legal"), help="As in the company register, if different.")
        c3, c4 = st.columns(2)
        legal_form = c3.text_input("Legal form", value=client.get("legal_form") or "",
                                   key=k("form"), placeholder="SRL, SA, SAS…")
        number = c4.text_input("Company number", value=client.get("enterprise_number") or "",
                               key=k("number"), help="BCE/KBO in Belgium, SIREN or SIRET in France.")
        address = st.text_area("Registered address", value=client.get("registered_address") or "",
                               key=k("addr"), height=80)
        _countries = list(COUNTRY_OPTIONS.keys())
        c5, c6, c7 = st.columns(3)
        country = c5.selectbox("Country", _countries,
                               index=_opt_index(_countries, client.get("country"), 0),
                               format_func=lambda x: COUNTRY_OPTIONS[x], key=k("country"))
        sector = c6.selectbox("Sector", SECTOR_OPTIONS,
                              index=_opt_index(SECTOR_OPTIONS, client.get("sector"), len(SECTOR_OPTIONS) - 1),
                              key=k("sector"))
        size = c7.selectbox("Employees", SIZE_OPTIONS,
                            index=_opt_index(SIZE_OPTIONS, client.get("company_size"), 0),
                            key=k("size"))
        website = st.text_input("Website", value=client.get("website_url") or "",
                                key=k("web"), placeholder="https://yourcompany.com")

        st.markdown("**What applies**")
        regs = st.multiselect(
            "Regulations", REGULATION_OPTIONS,
            default=[r for r in (client.get("regulations") or []) if r in REGULATION_OPTIONS],
            format_func=regulation_label, key=k("regs"),
            help="Decides which obligations, documents and alerts you see.",
        )
        langs = st.multiselect(
            "Document languages", list(DOC_LANGUAGES),
            default=[l for l in (client.get("document_languages") or ["en"]) if l in DOC_LANGUAGES],
            format_func=lambda l: DOC_LANGUAGES[l], key=k("langs"),
            help="Every language your documents must exist in — for example "
                 "French and Dutch for a company serving both communities.",
        )

        st.markdown("**Contacts**")
        c8, c9, c10 = st.columns(3)
        contact = c8.text_input("Contact email for data requests", value=client.get("contact_email") or "",
                                key=k("contact"))
        dpo_name = c9.text_input("DPO name (if appointed)", value=client.get("dpo_name") or "",
                                 key=k("dpo"))
        dpo_email = c10.text_input("DPO email", value=client.get("dpo_email") or "", key=k("dpomail"))

        if st.form_submit_button("Save", type="primary"):
            if not name.strip():
                st.warning("Give the company a name.")
            elif not regs:
                st.warning("Choose at least one regulation.")
            elif not langs:
                st.warning("Choose at least one document language.")
            else:
                fields = {
                    "company_name": name.strip(), "legal_name": legal_name.strip() or None,
                    "legal_form": legal_form.strip() or None,
                    "enterprise_number": number.strip() or None,
                    "registered_address": address.strip() or None,
                    "country": country, "sector": sector, "company_size": size,
                    "website_url": website.strip() or None, "regulations": regs,
                    "document_languages": langs, "contact_email": contact.strip() or None,
                    "dpo_name": dpo_name.strip() or None, "dpo_email": dpo_email.strip() or None,
                }
                if update_client_fields(cid, fields):
                    load_clients.clear()
                    load_accessible_clients.clear()
                    st.session_state.selected_client = {**client, **fields}
                    st.success("Saved.")
                    st.rerun()

    if "NIS2" in (client.get("regulations") or []):
        _n1, _n2 = st.columns([3, 1])
        _scope = client.get("nis2_in_scope")
        _n1.caption("NIS2 scope: " + ("in scope" if _scope else "not in scope" if _scope is False
                                      else "not confirmed yet")
                    + ". It is set on the Obligations page, next to the obligations it changes.")
        if _n2.button("Set NIS2 scope", key="co_nis2", use_container_width=True):
            st.switch_page("app_pages/obligations.py")

st.divider()

# ── All companies ─────────────────────────────────────────────────────────
st.subheader("Your companies")
if len(clients) > 1:
    st.caption("Switch between them with the company box at the top of the menu.")
for c in clients:
    st.markdown(
        f"**{c['company_name']}** · " + ("Owner" if c.get("role") == "owner" else "Member")
        + "  \n:gray[" + " · ".join(p for p in (
            c.get("sector", ""), country_label(c.get("country")),
            regulations_text(c.get("regulations")),
        ) if p) + "]"
    )

with st.expander("➕ Add a company", expanded=not clients):
    if client_limit_reached(user_id):
        st.info("Professional includes one company. Upgrade to Advisory to add more.")
        if st.button("Upgrade to add another company"):
            upsell_dialog("Professional accounts manage one company. Upgrade to "
                          "Advisory to add more.")
    else:
        # S48: shared form (client_setup.py), with lookup and website scan
        from client_setup import render_new_client_form
        created = render_new_client_form(user_id, key="conc")
        if created:
            st.session_state.selected_client = created
            st.rerun()
