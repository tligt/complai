"""
pages_admin/countries.py — S64 (D-163). What is done, per country.

The ten-item checklist every country goes through before RECOSA serves it
(3b localization note): languages, regulators, law, breach channels, sources,
company data, templates, interface, commercial, support. One row per country
and item in country_checklists; admin only.
"""

import streamlit as st

from datetime import datetime, timezone

from database import get_supabase_admin
from auth import get_user_id

ITEMS = {
    "languages": ("Languages", "Official and business languages; locales offered for documents and interface."),
    "regulators": ("Regulators", "GDPR authority, NIS2 authority and CSIRT, AI Act authorities, sector regulators; channels verified."),
    "law": ("Law", "National GDPR act, NIS2 transposition and registration, AI Act designations, ePrivacy, retention periods."),
    "breach": ("Breach notification", "Authority form or portal, deadlines, language of filing."),
    "sources": ("Local sources", "Authority news, official journal, national CERT, for monitoring."),
    "company_data": ("Company data", "Business registry lookup, number format, legal forms."),
    "templates": ("Templates and wording", "Documents per locale, reviewed by a local lawyer; inserts translated."),
    "interface": ("Interface and emails", "Screens, free check, result and sign-up emails, support replies."),
    "commercial": ("Commercial", "Currency, VAT, prices, RECOSA's terms and privacy policy, website, sign-up."),
    "support": ("Support", "Languages support is offered in."),
}
STATUS = {"done": "🟢 Done", "partial": "🟡 Partly", "todo": "🔴 To do", "n_a": "– Not applicable"}
COUNTRIES = {"BE": "Belgium", "FR": "France", "NL": "Netherlands", "LU": "Luxembourg"}

st.title("Countries")
st.caption("What is in place for RECOSA to serve each country. A country opens when every "
           "item is done or not applicable.")

user_id = get_user_id()
admin = get_supabase_admin()
try:
    rows = admin.table("country_checklists").select("*").execute().data or []
except Exception as e:
    st.error(f"Could not read the checklists: {e}")
    st.stop()

by_country: dict[str, dict[str, dict]] = {}
for r in rows:
    by_country.setdefault(r["country"], {})[r["item"]] = r

summary = []
for code in sorted(by_country, key=lambda c: list(COUNTRIES).index(c) if c in COUNTRIES else 99):
    items = by_country[code]
    done = sum(1 for r in items.values() if r["status"] in ("done", "n_a"))
    summary.append({"Country": f"{COUNTRIES.get(code, code)} ({code})", "Ready": f"{done} of {len(ITEMS)}",
                    **{ITEMS[k][0]: STATUS[items[k]["status"]].split(" ")[0] if k in items else "?"
                       for k in ITEMS}})
st.dataframe(summary, hide_index=True, use_container_width=True)

code = st.selectbox("Country", [c for c in COUNTRIES if c in by_country] + sorted(set(by_country) - set(COUNTRIES)),
                    format_func=lambda c: f"{COUNTRIES.get(c, c)} ({c})")
items = by_country.get(code, {})
with st.form(f"cc_{code}"):
    changes = {}
    for key, (label, hint) in ITEMS.items():
        cur = items.get(key) or {"status": "todo", "note": ""}
        a, b = st.columns([1, 3])
        status = a.selectbox(label, list(STATUS), index=list(STATUS).index(cur["status"]),
                             format_func=lambda s: STATUS[s], key=f"cc_{code}_{key}_s", help=hint)
        note = b.text_area("Note", value=cur.get("note") or "", height=68, key=f"cc_{code}_{key}_n",
                           label_visibility="hidden")
        if status != cur["status"] or (note or "") != (cur.get("note") or ""):
            changes[key] = {"status": status, "note": note.strip() or None}
    if st.form_submit_button("Save", type="primary"):
        try:
            for key, ch in changes.items():
                admin.table("country_checklists").upsert(
                    {"country": code, "item": key, **ch, "updated_by": user_id,
                     "updated_at": datetime.now(timezone.utc).isoformat()},
                    on_conflict="country,item").execute()
            # Not in audit_log: it is per company, and this is RECOSA's own
            # plan. Who changed an item, and when, is on the row itself.
            st.success(f"Saved {len(changes)} change(s)." if changes else "Nothing changed.")
            if changes:
                st.rerun()
        except Exception as e:
            st.error(f"Could not save: {e}")
