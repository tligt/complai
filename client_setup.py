"""
client_setup.py — S48: the one "new client" form.

Used by the first-run welcome screen (app.py) and the "➕ New client" boxes
on Chat and Profile. Those were three copies of the same five fields; S48
adds a company-number lookup and a website scan, which would otherwise have
had to be added three times.

Flow, all suggestions the user can overwrite before saving:
  1. Company number + Look up (BE, FR): fills legal name, sector and, where
     the register has it, the website (company_registry.py).
  2. Name, sector, country, size, regulations, website.
  3. Create client: saves the client (with the registry details), then, if
     a website was given, scans it and stores the scan (detection.py), so
     its suggestions are waiting on the Systems page. Nothing is added to
     the inventory from here; that stays a user confirmation (S48 scope).

Streamlit-dependent, like active_client.py. Not an st.form: the Look up
button has to rerun the page to prefill the fields below it.
"""

from __future__ import annotations

import streamlit as st

import company_registry as REG
import detection
import inventory_store as STORE
from cached_reads import load_accessible_clients, load_clients
from database import create_client_record

COUNTRY_OPTIONS = {
    "EU": "🇪🇺 EU only",
    "BE": "🇧🇪 Belgium",
    "FR": "🇫🇷 France",
    "nl": "🇳🇱 Netherlands",
    "de": "🇩🇪 Germany",
    "lu": "🇱🇺 Luxembourg",
}
SECTOR_OPTIONS = [
    "SaaS / Technology", "Professional services", "Healthcare / Medtech",
    "Manufacturing", "Finance / Fintech", "Logistics / Transport",
    "Retail / E-commerce", "Education", "Other",
]
SIZE_OPTIONS = ["1-10", "11-50", "51-150", "150+"]
REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT"]

_LOOKUP_COUNTRIES = {"BE": "Enterprise number (e.g. 0783.225.609)",
                     "FR": "SIREN or SIRET (e.g. 552 032 534)"}


def render_new_client_form(user_id: str, key: str) -> dict | None:
    """Render the form under widget-key prefix `key` (unique per page).
    Returns the created client row on the run it is created, else None."""
    k = lambda name: f"{key}_{name}"
    reg_key = k("registry")
    flash_key = k("flash")

    for kind, msg in st.session_state.pop(flash_key, []):
        getattr(st, kind)(msg)

    country = st.selectbox(
        "Country", list(COUNTRY_OPTIONS.keys()), index=1,
        format_func=lambda x: COUNTRY_OPTIONS[x], key=k("country"),
    )

    # ── 1. Registry lookup ──────────────────────────────────────────────
    rec = st.session_state.get(reg_key)
    if country in _LOOKUP_COUNTRIES:
        c1, c2 = st.columns([3, 1])
        number = c1.text_input(
            "Company number (optional)", key=k("number"),
            placeholder=_LOOKUP_COUNTRIES[country],
            help="We look the company up in the official register and fill in "
                 "what we find. You can change everything before saving.",
        )
        c2.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if c2.button("Look up", key=k("lookup"), use_container_width=True,
                     disabled=not number.strip()):
            with st.spinner("Looking the company up…"):
                rec = REG.lookup(country, number)
            st.session_state[reg_key] = rec
            if not rec.error:
                # Prefill before the widgets below are created in this run
                st.session_state[k("name")] = rec.legal_name.title() if rec.legal_name.isupper() else rec.legal_name
                if rec.sector in SECTOR_OPTIONS:
                    st.session_state[k("sector")] = rec.sector
                if rec.website:
                    st.session_state[k("website")] = rec.website

        if rec and rec.country == country:
            if rec.error:
                st.warning(rec.error)
            else:
                st.success(
                    f"**{rec.legal_name}**"
                    + (f" · {rec.legal_form}" if rec.legal_form else "")
                    + ("" if rec.active in (None, True) else " · ⚠️ not active in the register")
                    + f"  \n{rec.registered_address.replace(chr(10), ', ')}"
                    + (f"  \nActivity {rec.nace_code}"
                       + (f": {rec.nace_label}" if rec.nace_label else "")
                       if rec.nace_code else "")
                )
    else:
        rec = None

    # ── 2. Details (prefilled where the register had them) ──────────────
    name = st.text_input("Company name", key=k("name"))
    sector = st.selectbox("Sector", SECTOR_OPTIONS, key=k("sector"))
    size = st.selectbox("Size", SIZE_OPTIONS, key=k("size"))
    regs = st.multiselect("Regulations", REGULATION_OPTIONS, default=["GDPR"], key=k("regs"))
    website = st.text_input(
        "Website (optional)", key=k("website"), placeholder="yourcompany.com",
        help="Scanned when the client is created, to suggest the tools you use. "
             "Nothing is added to your inventory until you confirm it.",
    )

    # ── 3. Create ───────────────────────────────────────────────────────
    if not st.button("Create client", type="primary", use_container_width=True,
                     key=k("create")):
        return None
    if not name.strip():
        st.warning("Give the company a name.")
        return None

    profile = {
        "company_name": name.strip(),
        "sector": sector,
        "country": country,
        "company_size": size,
        "regulations": regs,
        "website_url": website.strip() or None,
    }
    if rec and not rec.error and rec.country == country:
        profile.update({
            "enterprise_number": rec.number,
            "legal_name": rec.legal_name,
            "legal_form": rec.legal_form or None,
            "registered_address": rec.registered_address or None,
        })
    created = create_client_record(user_id, profile)
    if not created:
        return None
    load_clients.clear()
    load_accessible_clients.clear()

    msgs = [("success", f"✅ {profile['company_name']} created.")]
    if profile["website_url"]:
        with st.spinner("Scanning the website for the tools you use…"):
            scan = detection.detect(profile["website_url"])
        STORE.save_website_scan(scan, profile["website_url"], user_id, created["id"])
        if scan.detected:
            msgs.append(("info",
                f"The website scan suggests {len(scan.detected)} tool"
                f"{'s' if len(scan.detected) != 1 else ''} "
                f"({', '.join(d.name for d in scan.detected)}). "
                "Confirm them on the **Systems** page."))
        elif scan.other_services:
            msgs.append(("info", "The website scan found services to review on the **Systems** page."))
    # Reset the form for the next client
    for name_ in ("registry", "number", "name", "website"):
        st.session_state.pop(k(name_), None)
    st.session_state[flash_key] = msgs
    return created
