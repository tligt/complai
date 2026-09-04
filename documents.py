import os
import streamlit as st
from auth import get_user_id
from database import load_clients
from document_generator import (
    DOCUMENT_TYPES, LEGAL_FORMS, DPA_CONTACTS,
    load_intake, save_intake, update_client_profile,
    save_document_with_files, load_document_history,
    suggest_processing_activities,
    get_regulatory_context, generate_document_text,
    build_docx, convert_docx_to_pdf, convert_docx_to_odt,
)

# ── S25: templated document types ─────────────────────────────
# Tier 1 documents are rendered from a reviewed template plus merge fields
# instead of being written by the LLM at runtime. The flag keeps the old
# prompt path reachable for one sprint (D-11) so a regression can be compared
# against it rather than reconstructed from memory.
#
#   TEMPLATE_DOC_TYPES="cookie_policy,ropa_controller,ropa_processor"
#                                        default — all Tier 1 templated
#   TEMPLATE_DOC_TYPES=""                everything back on the LLM path
#
# S26 retired the single "ropa" doc_type. Art. 30(1) and Art. 30(2) prescribe
# different content and are differently pivoted, and the CNIL recommends an
# organisation acting as both keep two separate registers. There is no LLM
# fallback for either — they never had one under the new names.
#
# The templated path needs a real client_id: it reads the S24 inventory. So
# Advisory / external-company generation stays on the LLM path regardless.
TEMPLATE_DOC_TYPES = {
    t.strip() for t in os.environ.get(
        "TEMPLATE_DOC_TYPES",
        "cookie_policy,ropa_controller,ropa_processor,dpa",
    ).split(",")
    if t.strip()
}

user_id = get_user_id()

st.title("📄 Document Generation")
st.caption("Generate compliance documents tailored to your client's profile.")
st.divider()

# ── Session state init ────────────────────────────────────────
for key, default in [
    ("doc_activities", []),
    ("doc_processors", []),
    ("doc_retention", []),
    ("doc_confirmed", False),
    ("doc_context_key", None),
    ("doc_prefill", {}),
    ("doc_contact_email", ""),
    ("doc_legal_name", ""),
    ("doc_legal_form", ""),
    ("doc_country", "BE"),
    ("doc_website_url", ""),
    ("doc_dpo_name", ""),
    ("doc_dpo_email", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Client / mode selection ───────────────────────────────────
clients = load_clients(user_id)
if not clients:
    st.info("👈 Create a client profile first before generating documents.")
    st.stop()

mode = st.radio(
    "Generate for:",
    options=["existing_client", "external_company"],
    format_func=lambda x: "Existing client profile" if x == "existing_client" else "External company (Advisory)",
    horizontal=True,
    key="doc_mode"
)

selected_client = None
client_id = None

if mode == "existing_client":
    client_names = [c["company_name"] for c in clients]
    chosen = st.selectbox("Select client", options=client_names, key="doc_client_select")
    selected_client = next((c for c in clients if c["company_name"] == chosen), None)
    client_id = selected_client["id"] if selected_client else None

st.divider()

# S26. Art. 30 registers are built from the inventory rather than a form, so
# the page can tell in advance whether one is worth offering.
REGISTER_DOC_TYPES = {"ropa_controller", "ropa_processor"}

# S26A. The Art. 28 clauses are a contract, not a record, so they get their own
# gate rather than joining REGISTER_DOC_TYPES: an incomplete register is
# truthful and publishable, an incomplete contract is neither.
_register_state = None
_dpa_unmeasured: list[str] = []
if mode == "existing_client" and client_id:
    try:
        import inventory_store as _STORE
        _acts = _STORE.load_activities(user_id, client_id)
        _register_state = _STORE.readiness(
            _acts,
            _STORE.load_systems(user_id, client_id),
            _STORE.load_links(user_id, client_id),
            _STORE.load_counterparty_links(user_id, client_id),
            client_id,
        )
        # Annex III part 1 is unioned across the processor activities, so the
        # question is not "does this activity have measures" but "does the
        # engagement as a whole". Naming the activities anyway: a client told
        # only that Annex III is empty has nowhere to go.
        _dpa_unmeasured = sorted(
            (a.get("name") or "(unnamed activity)")
            for a in _acts
            if a.get("controller_role") == "processor"
            and not (a.get("security_measures") or [])
        )
    except Exception:
        # A failed inventory read must not take the page down. Without it the
        # gate simply does not apply and generation behaves as it did before.
        _register_state = None
        _dpa_unmeasured = []

_offered = list(DOCUMENT_TYPES.keys())
if _register_state is not None and not _register_state["processor_activities"]:
    # No processing carried out for another controller means no Art. 30(2)
    # record to keep. An empty processor register is a document nobody needs,
    # and offering it invites a client to file one that says nothing.
    #
    # The same fact removes the DPA. Clause 1(c) makes these Clauses apply to
    # the processing Annex II specifies; with no processor-role activity there
    # is no processing for them to attach to, and the contract would describe
    # nothing.
    _offered = [d for d in _offered if d not in ("ropa_processor", "dpa")]

doc_type = st.selectbox(
    "Document type",
    options=_offered,
    format_func=lambda x: DOCUMENT_TYPES[x],
    key="doc_type_select"
)

# ── S25: is this generation templated? ────────────────────────
use_template = bool(
    doc_type in TEMPLATE_DOC_TYPES
    and mode == "existing_client"
    and client_id
)

if use_template:
    # A templated document is generated in every language the client issues
    # documents in, as one group — not one language at a time. Asking here
    # would imply the languages are separate documents, which is exactly the
    # confusion document_group_id exists to prevent.
    doc_langs = (selected_client or {}).get("document_languages") or ["en"]
    st.info(
        "This document is generated from a reviewed template using your "
        "systems inventory. It will be produced in: "
        + ", ".join(l.upper() for l in doc_langs)
        + ".  You can change these in the client profile."
    )
    language = doc_langs[0]
else:
    language = st.selectbox(
        "Document language",
        options=["en", "fr", "nl"],
        format_func=lambda x: {"en": "EN — English", "fr": "FR — Français", "nl": "NL — Nederlands"}[x],
        key="doc_lang_select"
    )

st.divider()

# ── Context change detection ──────────────────────────────────
# Build a key representing the current context
context_key = f"{mode}_{client_id}_{doc_type}"

if context_key != st.session_state.doc_context_key:
    # Context changed — reload prefill and clear structured rows
    st.session_state.doc_context_key = context_key
    st.session_state.doc_activities = []
    st.session_state.doc_processors = []
    st.session_state.doc_retention = []
    st.session_state.doc_confirmed = False
    st.session_state.doc_contact_email = ""
    st.session_state.doc_legal_name = ""
    st.session_state.doc_legal_form = ""
    st.session_state.doc_country = "BE"
    st.session_state.doc_website_url = ""
    st.session_state.doc_dpo_name = ""
    st.session_state.doc_dpo_email = ""

    if mode == "existing_client" and client_id:
        # Load intake + client profile into prefill cache
        intake = load_intake(client_id, user_id, doc_type)
        pf = {}
        # Start from client profile
        if selected_client:
            for f in ["company_name", "country", "website_url", "dpo_name",
                      "dpo_email", "contact_email", "legal_name", "legal_form", "sector"]:
                pf[f] = selected_client.get(f, "")
        # Override with saved intake (more specific)
        for f, v in intake.items():
            if v:
                pf[f] = v
        st.session_state.doc_prefill = pf
        # Populate stable session state vars from prefill
        st.session_state.doc_contact_email = pf.get("contact_email", "")
        st.session_state.doc_legal_name = pf.get("legal_name") or pf.get("company_name", "")
        st.session_state.doc_legal_form = pf.get("legal_form", "")
        st.session_state.doc_country = pf.get("country", "BE")
        st.session_state.doc_website_url = pf.get("website_url", "")
        st.session_state.doc_dpo_name = pf.get("dpo_name", "")
        st.session_state.doc_dpo_email = pf.get("dpo_email", "")
    else:
        # External company or no client — blank slate
        st.session_state.doc_prefill = {}

# Shortcut to prefill dict
pf = st.session_state.doc_prefill

# ── Universal fields ──────────────────────────────────────────
# Kept for templated documents too: this form writes back to the clients table
# via update_client_profile, and the template reads its merge fields from
# there. Filling it in is how a blocked required field gets unblocked.
st.subheader("Company information")
st.caption("Fields marked ✱ are required.")

col1, col2 = st.columns(2)
col1.text_input(
    "Legal company name ✱",
    value=st.session_state.doc_legal_name,
    key="f_legal_name_stable"
)
# Read current value from session state — this works reliably
legal_name = st.session_state.get("f_legal_name_stable", st.session_state.doc_legal_name)

country_options = {
    "BE": "🇧🇪 Belgium", "FR": "🇫🇷 France", "NL": "🇳🇱 Netherlands",
    "DE": "🇩🇪 Germany", "LU": "🇱🇺 Luxembourg", "EU": "🇪🇺 Other EU"
}
default_country = pf.get("country", "BE")
if default_country not in country_options:
    default_country = "BE"
country = col2.selectbox(
    "Country ✱",
    options=list(country_options.keys()),
    format_func=lambda x: country_options[x],
    index=list(country_options.keys()).index(default_country),
    key=f"f_country_{mode}_{client_id}"
)

form_options = LEGAL_FORMS.get(country, LEGAL_FORMS["EU"])
default_form = pf.get("legal_form", "")
default_form_idx = form_options.index(default_form) if default_form in form_options else 0
legal_form = st.selectbox(
    "Legal form ✱",
    options=form_options,
    index=default_form_idx,
    key=f"f_legal_form_{mode}_{client_id}"
)

website_url = st.text_input(
    "Website URL",
    value=pf.get("website_url", ""),
    placeholder="https://yourcompany.com",
    key=f"f_url_{mode}_{client_id}"
)

col3, col4 = st.columns(2)
dpo_name = col3.text_input(
    "DPO name (if appointed)",
    value=pf.get("dpo_name", ""),
    key=f"f_dpo_name_{mode}_{client_id}"
)
dpo_email = col4.text_input(
    "DPO email",
    value=pf.get("dpo_email", ""),
    key=f"f_dpo_email_{mode}_{client_id}"
)
st.text_input(
    "Contact email for data requests ✱",
    value=st.session_state.doc_contact_email,
    key="f_contact_stable"
)
# Read current value from session state — this works reliably
contact_email = st.session_state.get("f_contact_stable", st.session_state.doc_contact_email)

# ── S25: registered address and enterprise number ─────────────
# Required merge fields for the Cookie Policy, and absent from the pre-S25
# form. Shown for templated documents only, so the LLM path is untouched.
registered_address = None
enterprise_number = None
if use_template:
    col5, col6 = st.columns(2)
    registered_address = col5.text_area(
        "Registered address ✱",
        value=pf.get("registered_address", "") or (selected_client or {}).get("registered_address", "") or "",
        height=80,
        placeholder="Rue Example 1\n1000 Brussels\nBelgium",
        key=f"f_regaddr_{context_key}",
    )
    enterprise_number = col6.text_input(
        "Company registration number",
        value=pf.get("enterprise_number", "") or (selected_client or {}).get("enterprise_number", "") or "",
        placeholder="0123.456.789",
        help="BCE/KBO in Belgium, SIREN or SIRET in France.",
        key=f"f_entnum_{context_key}",
    )

# ── Structured field helpers ──────────────────────────────────

def activity_editor():
    st.markdown("**Processing activities ✱**")
    st.caption("Add one row per processing activity.")

    for i, act in enumerate(st.session_state.doc_activities):
        with st.expander(f"Activity {i+1}: {act.get('name','Untitled')}", expanded=True):
            c1, c2 = st.columns(2)
            st.session_state.doc_activities[i]["name"] = c1.text_input(
                "Activity name", value=act.get("name",""), key=f"act_name_{i}_{context_key}",
                placeholder="e.g. Customer management"
            )
            st.session_state.doc_activities[i]["subjects"] = c2.text_input(
                "Data subjects", value=act.get("subjects",""), key=f"act_subj_{i}_{context_key}",
                placeholder="e.g. Customers, employees"
            )
            st.session_state.doc_activities[i]["data"] = st.text_input(
                "Personal data collected", value=act.get("data",""), key=f"act_data_{i}_{context_key}",
                placeholder="e.g. Name, email, phone"
            )
            c3, c4 = st.columns(2)
            st.session_state.doc_activities[i]["purpose"] = c3.text_input(
                "Purpose", value=act.get("purpose",""), key=f"act_purp_{i}_{context_key}",
                placeholder="e.g. Service delivery"
            )
            legal_bases = [
                "Contract performance (Art. 6(1)(b))",
                "Consent (Art. 6(1)(a))",
                "Legal obligation (Art. 6(1)(c))",
                "Legitimate interests (Art. 6(1)(f))",
                "Vital interests (Art. 6(1)(d))",
                "Public task (Art. 6(1)(e))",
            ]
            current = act.get("legal_basis", legal_bases[0])
            basis_idx = legal_bases.index(current) if current in legal_bases else 0
            st.session_state.doc_activities[i]["legal_basis"] = c4.selectbox(
                "Legal basis", options=legal_bases, index=basis_idx,
                key=f"act_basis_{i}_{context_key}"
            )
            if st.button(f"Remove", key=f"rm_act_{i}_{context_key}"):
                st.session_state.doc_activities.pop(i)
                st.rerun()

    if st.button("➕ Add processing activity", key=f"add_act_{context_key}"):
        st.session_state.doc_activities.append({
            "name":"","subjects":"","data":"","purpose":"",
            "legal_basis":"Contract performance (Art. 6(1)(b))"
        })
        st.rerun()

    lines = []
    for i, act in enumerate(st.session_state.doc_activities):
        if act.get("name"):
            lines.append(
                f"{i+1}. {act['name']}: collects {act.get('data','—')} from "
                f"{act.get('subjects','—')} for {act.get('purpose','—')} — "
                f"legal basis: {act.get('legal_basis','—')}"
            )
    return "\n".join(lines)


def processor_editor():
    st.markdown("**Third-party processors**")
    st.caption("Add one row per tool or service that processes personal data on your behalf.")

    for i, proc in enumerate(st.session_state.doc_processors):
        with st.expander(f"Processor {i+1}: {proc.get('name','Untitled')}", expanded=True):
            c1, c2 = st.columns(2)
            st.session_state.doc_processors[i]["name"] = c1.text_input(
                "Service name", value=proc.get("name",""), key=f"proc_name_{i}_{context_key}",
                placeholder="e.g. Google Analytics"
            )
            st.session_state.doc_processors[i]["country"] = c2.text_input(
                "Country", value=proc.get("country",""), key=f"proc_ctry_{i}_{context_key}",
                placeholder="e.g. US, EU"
            )
            c3, c4 = st.columns(2)
            st.session_state.doc_processors[i]["purpose"] = c3.text_input(
                "Purpose", value=proc.get("purpose",""), key=f"proc_purp_{i}_{context_key}",
                placeholder="e.g. Analytics"
            )
            st.session_state.doc_processors[i]["data"] = c4.text_input(
                "Data shared", value=proc.get("data",""), key=f"proc_data_{i}_{context_key}",
                placeholder="e.g. IP address"
            )
            if st.button("Remove", key=f"rm_proc_{i}_{context_key}"):
                st.session_state.doc_processors.pop(i)
                st.rerun()

    if st.button("➕ Add processor", key=f"add_proc_{context_key}"):
        st.session_state.doc_processors.append({"name":"","country":"","purpose":"","data":""})
        st.rerun()

    lines = []
    for proc in st.session_state.doc_processors:
        if proc.get("name"):
            lines.append(
                f"{proc['name']} ({proc.get('country','—')}): "
                f"{proc.get('purpose','—')} — data: {proc.get('data','—')}"
            )
    return "\n".join(lines)


def retention_editor():
    st.markdown("**Retention periods**")
    if st.session_state.doc_retention:
        c1, c2, c3 = st.columns([3, 3, 1])
        c1.caption("Data type")
        c2.caption("Retention duration")

    for i, ret in enumerate(st.session_state.doc_retention):
        c1, c2, c3 = st.columns([3, 3, 1])
        st.session_state.doc_retention[i]["data_type"] = c1.text_input(
            "Data type", value=ret.get("data_type",""), key=f"ret_type_{i}_{context_key}",
            placeholder="e.g. Customer data", label_visibility="collapsed"
        )
        st.session_state.doc_retention[i]["duration"] = c2.text_input(
            "Duration", value=ret.get("duration",""), key=f"ret_dur_{i}_{context_key}",
            placeholder="e.g. 3 years after contract end", label_visibility="collapsed"
        )
        if c3.button("✕", key=f"rm_ret_{i}_{context_key}"):
            st.session_state.doc_retention.pop(i)
            st.rerun()

    if st.button("➕ Add retention rule", key=f"add_ret_{context_key}"):
        st.session_state.doc_retention.append({"data_type":"","duration":""})
        st.rerun()

    lines = [
        f"{r['data_type']}: {r.get('duration','—')}"
        for r in st.session_state.doc_retention if r.get("data_type")
    ]
    return "\n".join(lines)


# ── AI suggestion button (for privacy_policy and ropa) ──────────
# Not offered for templated documents: their content comes from the inventory,
# so suggesting activities here would produce data the document never reads.
if (not use_template) and doc_type in ["privacy_policy", "ropa", "cookie_policy"] and (selected_client or mode == "external_company"):
    st.divider()
    col_ai1, col_ai2 = st.columns([3, 1])
    col_ai1.markdown("**🤖 Let AI suggest processing activities based on your profile**")
    col_ai1.caption(
        "RECOSA will analyse your company sector, size and country to suggest "
        "likely processing activities, processors and retention periods. "
        "You can then review, edit and complete the list before generating."
    )
    if col_ai2.button("Suggest activities", type="secondary", use_container_width=True, key=f"btn_suggest_{context_key}"):
        with st.spinner("Analysing your profile and generating suggestions..."):
            try:
                client_for_suggest = selected_client or {
                    "company_name": st.session_state.get(f"f_legal_name_{mode}_{client_id}", ""),
                    "sector": "Unknown",
                    "country": country,
                    "company_size": "Unknown",
                    "regulations": ["GDPR"],
                }
                suggestions = suggest_processing_activities(client_for_suggest)
                st.session_state.doc_activities = suggestions.get("activities", [])
                st.session_state.doc_processors = suggestions.get("processors", [])
                st.session_state.doc_retention = suggestions.get("retention", [])
                st.session_state.doc_confirmed = False
                st.success(
                    f"✅ Suggested {len(st.session_state.doc_activities)} activities, "
                    f"{len(st.session_state.doc_processors)} processors and "
                    f"{len(st.session_state.doc_retention)} retention rules. "
                    "Review and edit below, then confirm before generating."
                )
                st.rerun()
            except Exception as e:
                st.error(f"Could not generate suggestions: {e}")

# ── Document-specific sections ────────────────────────────────
st.divider()
st.markdown(f"**{DOCUMENT_TYPES[doc_type]} — specific information**")

processor_name = processor_country = processing_purpose = None
incident_response_contact = escalation_procedure = None
processing_activities_text = third_party_processors_text = retention_periods_text = ""
international_transfers = False

if use_template:
    # No editors on any templated path. The content comes from the S24
    # inventory, so retyping it here would create a second source that drifts
    # from the first.
    #
    # DISPATCHED ON doc_type. This branch was written in S25, when
    # cookie_policy was the only templated document, and said so in prose: it
    # described the cookie vendor list and called _load_vendor_rows
    # unconditionally. S26 added the two registers and S26A the DPA, and all
    # three inherited a caption about systems "marked as setting cookies"
    # above a list of cookie vendors — on documents that read neither.
    #
    # Each templated document reads a DIFFERENT slice of the inventory, so
    # each needs its own description of what it will pick up.
    if doc_type == "cookie_policy":
        st.caption(
            "The third-party services in this document are taken from your "
            "systems inventory — every system marked as setting cookies. To "
            "change what appears, edit the inventory on the Systems page."
        )
        try:
            from template_store import _load_vendor_rows
            _preview_vendors = _load_vendor_rows(client_id, language)
        except Exception as e:
            _preview_vendors = []
            st.warning(f"Could not read the inventory: {e}")

        if _preview_vendors:
            st.markdown(
                "\n".join(
                    f"- **{v['vendor_name']}** — {v.get('purpose') or 'purpose not recorded'}"
                    for v in _preview_vendors
                )
            )
        else:
            st.warning(
                "No systems in your inventory are marked as setting cookies. "
                "The document will state that no third-party cookies are used "
                "— make sure that is actually true before publishing it."
            )

    elif doc_type == "ropa_controller":
        st.caption(
            "This record is built from the processing activities where you "
            "determine the purposes and means, together with the systems and "
            "recipients attached to them. Edit them under *Systems, "
            "activities and controllers*."
        )

    elif doc_type == "ropa_processor":
        st.caption(
            "This record is built from the processing activities you carry "
            "out on another controller's behalf, grouped by controller. Edit "
            "them under *Systems, activities and controllers*."
        )

    elif doc_type == "dpa":
        # No preview list. The two annexes are scoped differently from each
        # other — Annex II by activity, Schedule 1 by the systems attached to
        # those activities — and a single flat list above the form would
        # misrepresent both. The gate below already names anything blocking.
        st.caption(
            "These clauses are built from the processing you carry out on a "
            "customer's behalf. Annex II describes those activities, Schedule "
            "1 names the sub-processors involved in them, and Annex III lists "
            "the security measures recorded against them. Nothing you do "
            "purely as controller appears. Edit any of it under *Systems, "
            "activities and controllers*."
        )

    else:
        # A doc_type added to TEMPLATE_DOC_TYPES without a caption here. Says
        # so plainly rather than describing the wrong document, which is the
        # failure this dispatch exists to fix.
        st.caption(
            "This document is generated from a reviewed template using your "
            "systems inventory. Edit the underlying data under *Systems, "
            "activities and controllers*."
        )

elif doc_type == "privacy_policy":
    processing_activities_text = activity_editor()
    st.divider()
    third_party_processors_text = processor_editor()
    st.divider()
    retention_periods_text = retention_editor()
    st.divider()
    international_transfers = st.checkbox(
        "Do you transfer personal data outside the EU/EEA?",
        value=bool(pf.get("international_transfers", False)),
        key=f"f_transfers_{context_key}"
    )

elif doc_type == "cookie_policy":
    third_party_processors_text = processor_editor()

elif doc_type == "dpa" and not use_template:
    # PRE-D-40 INTAKE — controller side, Advisory path only.
    #
    # These fields name a company processing data ON BEHALF OF the client,
    # which is the VENDOR side of Art. 28. D-40 made that obligation
    # operational: it is discharged by holding the vendor's own DPA and
    # recording it against the system (systems.dpa_status / dpa_signed_on /
    # dpa_url), not by authoring one.
    #
    # The templated "dpa" is the other side entirely — the clauses the client
    # OFFERS its customers, with Annex II built from activities where
    # controller_role = 'processor'. Showing this form alongside it would ask
    # a client for a vendor's name to produce a contract that never mentions
    # one, and save_intake would store three fields the template never reads.
    #
    # Guarded rather than deleted: it is still the only DPA path for Advisory
    # / external-company generation, which has no client_id and so no
    # inventory to build Annex II from. Retiring it is a decision for S28.
    processor_name = st.text_input(
        "Processor name ✱", value=pf.get("processor_name",""),
        key=f"f_proc_name_{context_key}", placeholder="Company processing data on your behalf"
    )
    ca, cb = st.columns(2)
    processor_country = ca.text_input(
        "Processor country", value=pf.get("processor_country",""),
        key=f"f_proc_ctry_{context_key}"
    )
    processing_purpose = cb.text_input(
        "Purpose of processing ✱", value=pf.get("processing_purpose",""),
        key=f"f_proc_purp_{context_key}"
    )
    processing_activities_text = activity_editor()

elif doc_type == "ropa":
    processing_activities_text = activity_editor()
    st.divider()
    third_party_processors_text = processor_editor()
    st.divider()
    retention_periods_text = retention_editor()
    st.divider()
    international_transfers = st.checkbox(
        "International transfers outside EU/EEA?",
        value=bool(pf.get("international_transfers", False)),
        key=f"f_transfers_{context_key}"
    )

elif doc_type == "incident_response":
    incident_response_contact = st.text_input(
        "Primary incident response contact ✱",
        value=pf.get("incident_response_contact",""),
        placeholder="Name, role, email, phone",
        key=f"f_ir_{context_key}"
    )
    escalation_procedure = st.text_area(
        "Escalation chain",
        value=pf.get("escalation_procedure",""),
        height=100,
        placeholder="1. IT Manager → 2. CEO → 3. Legal → 4. CCB/ANSSI (within 24h)",
        key=f"f_esc_{context_key}"
    )
    processing_activities_text = st.text_area(
        "Critical systems and assets",
        value=pf.get("processing_activities",""),
        height=80,
        key=f"f_sys_{context_key}"
    )

elif doc_type == "ai_transparency":
    processing_activities_text = st.text_area(
        "AI system description ✱",
        value=pf.get("processing_activities",""),
        height=120,
        placeholder="Describe your AI system and how users interact with it...",
        key=f"f_ai_{context_key}"
    )
    third_party_processors_text = st.text_input(
        "AI provider / model used",
        value=pf.get("third_party_processors",""),
        placeholder="e.g. Mistral AI",
        key=f"f_aiprov_{context_key}"
    )

# ── Confirmation checkbox ────────────────────────────────────────
if (not use_template) and doc_type in ["privacy_policy", "ropa"]:
    st.divider()
    st.session_state.doc_confirmed = st.checkbox(
        "✅ I have reviewed all processing activities and, to the best of my knowledge, "
        "have not missed any significant data processing my organisation carries out. "
        "I understand this document is a starting point and should be reviewed by a legal professional.",
        value=st.session_state.doc_confirmed,
        key=f"f_confirmed_{context_key}"
    )
else:
    st.session_state.doc_confirmed = True

# ── S26: the register gate ────────────────────────────────────
# render_template blocks only on missing FieldSpec scalars. Per-activity gaps
# live inside a block renderer, which is called after the decision to generate
# has already been made and cannot stop it. So anything that would make the
# record INACCURATE has to be caught here (D-30).
#
# Gaps are not blocked: a register missing a security-measures description is
# incomplete but truthful, and Art. 30(1)(g) asks for one "where possible".
_register_blocked = False
if doc_type in REGISTER_DOC_TYPES and _register_state is not None:
    if _register_state["blocking"]:
        _register_blocked = True
        st.error(
            "**This record cannot be generated yet — these would make it "
            "inaccurate:**\n\n- " + "\n- ".join(_register_state["blocking"])
        )
        st.caption(
            "Resolve them under *Systems, activities and controllers*. A record "
            "that states a purpose with no legal basis, or names special "
            "category data with no Art. 9(2) condition, documents a problem "
            "rather than demonstrating compliance."
        )
    elif _register_state["activity_gaps"]:
        st.warning(
            "This record can be generated, but these fields are not yet "
            "recorded and will show as missing:\n\n- "
            + "\n- ".join(_register_state["activity_gaps"])
        )

# S26A — the DPA's own gate.
#
# annex_iii_security is required=True because Clause 7.4(a) obliges the
# processor to implement AT LEAST the measures Annex III specifies. An empty
# Annex III leaves that obligation with nothing to bite on: the contract is
# wrong, not merely incomplete.
#
# render_template would block this anyway, on the missing required field. It is
# caught here instead so the message can name the activities and say where to
# fix them — a first-time client meeting a bare "cannot generate" on a contract
# has no way to work out what is being asked of them.
_dpa_blocked = False
if doc_type == "dpa" and use_template and _dpa_unmeasured:
    _dpa_blocked = True
    st.error(
        "**These clauses cannot be generated yet.** Annex III has to set out "
        "the security measures the processor implements, and these activities "
        "carried out on a customer's behalf have none recorded:\n\n- "
        + "\n- ".join(_dpa_unmeasured)
    )
    st.caption(
        "Record them under *Systems, activities and controllers*. Clause "
        "7.4(a) commits you to implementing at least what Annex III lists, so "
        "an empty annex is a promise with nothing behind it rather than a "
        "detail left for later."
    )

# ── Generate ──────────────────────────────────────────────────
st.divider()
generate = st.button(
    f"⚡ Generate {DOCUMENT_TYPES[doc_type]}",
    type="primary",
    use_container_width=True,
    key=f"btn_gen_{context_key}",
    disabled=_register_blocked or _dpa_blocked,
)

# ── Adoption (S27) — lives in the history section, not here ──────────────
#
# The adoption control was first placed directly under each generated
# document, which is where a client would look for it. It could not work
# there.
#
# Streamlit reruns the whole script on every interaction. The generation
# blocks below are gated on `generate`, which is a button and is therefore
# True for exactly one run. Clicking "Put in force" starts a NEW run in which
# `generate` is False, so the branch never executes, the button is never
# evaluated, and nothing happens — the panel simply disappears.
#
# A button nested inside a button-gated block cannot fire. Same family as the
# note in pages/inventory.py about widgets inside st.form.
#
# So adoption belongs in the document history, which renders on every run. It
# is also the better home: the history already lists every version with its
# status, so putting the control there means the client adopts a version from
# a list of versions rather than from whichever one they happened to generate
# last.


# ══════════════════════════════════════════════════════════════
# S25 — TEMPLATED PATH
# ══════════════════════════════════════════════════════════════
if generate and use_template:
    from docgen_templates import generate_templated_document

    def _s(v): return (v or "").strip()

    # Write the form back to the client profile FIRST. The template reads its
    # merge fields from the clients table, not from this form, so a blocked
    # required field is unblocked by saving — not by typing and generating.
    profile_update = {
        "website_url": _s(website_url) or None,
        "dpo_name": _s(dpo_name) or None,
        "dpo_email": _s(dpo_email) or None,
        "contact_email": _s(contact_email) or None,
        "legal_name": _s(legal_name) or None,
        "legal_form": legal_form or None,
        "registered_address": _s(registered_address) or None,
        "enterprise_number": _s(enterprise_number) or None,
    }
    update_client_profile(client_id, user_id, profile_update)

    company_display = f"{_s(legal_name)} {legal_form or ''}".strip()

    with st.spinner("Generating from template..."):
        outcome = generate_templated_document(
            user_id=user_id,
            client_id=client_id,
            doc_type=doc_type,
            company_name=company_display,
        )

    if not outcome.ok:
        st.error(outcome.message)
        if outcome.missing_required:
            st.caption(
                "Fill these in above and generate again. The document is not "
                "produced with them missing, because a compliance document that "
                "cannot identify the company is wrong rather than incomplete."
            )
    else:
        st.success(outcome.message)

        for item in outcome.saved:
            st.divider()
            st.markdown(f"### {item['language'].upper()}")
            if item["outstanding"]:
                st.warning(
                    f"{item['outstanding']} field(s) are marked "
                    "`[[ TO COMPLETE: … ]]` in this version."
                )
            if item.get("has_xlsx"):
                st.caption(
                    "Saved as both a spreadsheet and a Word document. The "
                    "spreadsheet is the working copy — it filters and sorts, "
                    "which is what a register is for."
                )
            with st.expander("Preview", expanded=False):
                st.markdown(item["body"])

        st.caption(
            "Generated from a reviewed template. Files are saved to your "
            "document history below. Review with a qualified legal "
            "professional before publishing."
        )

# ══════════════════════════════════════════════════════════════
# LLM PATH (unchanged)
# ══════════════════════════════════════════════════════════════
elif generate:
    legal_name = st.session_state.get("f_legal_name_stable", "") or legal_name or ""
    contact_email = st.session_state.get("f_contact_stable", "") or contact_email or ""

    if not legal_name.strip():
        st.error("Legal company name is required.")
        st.stop()
    if doc_type in ["privacy_policy", "ropa"] and not contact_email.strip():
        st.error("Contact email is required.")
        st.stop()
    if doc_type in ["privacy_policy", "ropa"] and not st.session_state.doc_confirmed:
        st.error("Please confirm you have reviewed all processing activities before generating.")
        st.stop()
    if doc_type == "privacy_policy" and not st.session_state.doc_activities:
        st.error("Please add at least one processing activity.")
        st.stop()

    # Helper to safely strip potentially None values
    def s(v): return (v or "").strip()

    intake_data = {
        "legal_name": s(legal_name),
        "legal_form": legal_form or "",
        "country": country or "BE",
        "website_url": s(website_url),
        "dpo_name": s(dpo_name),
        "dpo_email": s(dpo_email),
        "contact_email": s(contact_email),
        "processing_activities": processing_activities_text or "",
        "third_party_processors": third_party_processors_text or "",
        "international_transfers": international_transfers or False,
        "retention_periods": retention_periods_text or "",
        "processor_name": s(processor_name),
        "processor_country": s(processor_country),
        "processing_purpose": s(processing_purpose),
        "incident_response_contact": s(incident_response_contact),
        "escalation_procedure": s(escalation_procedure),
    }

    if client_id:
        save_intake(client_id, user_id, doc_type, intake_data)
        update_client_profile(client_id, user_id, {
            "website_url": s(website_url) or None,
            "dpo_name": s(dpo_name) or None,
            "dpo_email": s(dpo_email) or None,
            "contact_email": s(contact_email) or None,
            "legal_name": s(legal_name) or None,
            "legal_form": legal_form or None,
        })
        # Update prefill cache
        st.session_state.doc_prefill.update(intake_data)

    company_display = f"{s(legal_name)} {legal_form or ''}".strip()

    with st.spinner(f"Generating {DOCUMENT_TYPES[doc_type]}..."):
        reg_context = get_regulatory_context(doc_type, language, country)
        doc_text = generate_document_text(
            document_type=doc_type,
            intake=intake_data,
            client=selected_client or {},
            language=language,
            regulatory_context=reg_context,
        )
        docx_bytes = build_docx(doc_text, doc_type, company_display, language)

    st.success(f"✅ {DOCUMENT_TYPES[doc_type]} generated for {company_display}")

    with st.spinner("Preparing PDF and ODT..."):
        try:
            pdf_bytes = convert_docx_to_pdf(docx_bytes); pdf_ok = True
        except Exception:
            pdf_ok = False
        try:
            odt_bytes = convert_docx_to_odt(docx_bytes); odt_ok = True
        except Exception:
            odt_ok = False

    # Save record + upload files to Supabase Storage
    save_document_with_files(
        user_id=user_id,
        client_id=client_id,
        document_type=doc_type,
        language=language,
        company_name=company_display,
        docx_bytes=docx_bytes,
        pdf_bytes=pdf_bytes if pdf_ok else None,
        odt_bytes=odt_bytes if odt_ok else None,
    )

    st.markdown("**Download your document:**")
    fname = f"RECOSA_{doc_type}_{company_display.replace(' ','_')}"
    c1, c2, c3 = st.columns(3)
    c1.download_button("📝 DOCX", docx_bytes, f"{fname}.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True, type="primary")
    if pdf_ok:
        c2.download_button("📄 PDF", pdf_bytes, f"{fname}.pdf",
            "application/pdf", use_container_width=True)
    if odt_ok:
        c3.download_button("📋 ODT", odt_bytes, f"{fname}.odt",
            "application/vnd.oasis.opendocument.text", use_container_width=True)

    st.divider()
    with st.expander("📖 Preview", expanded=False):
        st.markdown(doc_text)
    st.caption(
        "⚠️ Generated by AI from official EU regulatory sources. "
        "Review with a qualified legal professional before use."
    )


# ── History ───────────────────────────────────────────────────
#
# Grouped by document_group_id (S25). The language siblings of one generation
# are the SAME document in several languages, not several documents, so they
# collapse into one row. Older generations of the same doc type fold behind an
# expander, leaving one visible row per document type.
#
# Missing languages are DERIVED — languages in the group compared against
# clients.document_languages — never stored. A stored "NL still to do" flag
# would be a second source of truth that can disagree with the rows themselves.
#
# Rows generated before S25 carry no document_group_id. Each becomes its own
# single-language group, which is what they actually were.

import os as _os
import base64 as _b64
import requests as _req
from zoneinfo import ZoneInfo as _ZI
from datetime import datetime as _dt
from database import load_document_files, get_signed_url, get_supabase_admin

def _fmt_ts(raw):
    try:
        return _dt.fromisoformat(raw.replace("Z","+00:00")).astimezone(_ZI("Europe/Brussels")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw[:16].replace("T"," ")

def _send_email(to: str, subject: str, body: str, file_bytes: bytes, filename: str) -> bool:
    api_key = _os.environ.get("BREVO_API_KEY","")
    if not api_key:
        return False
    try:
        r = _req.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender": {"name": _os.environ.get("BREVO_FROM_NAME","RECOSA"), "email": _os.environ.get("BREVO_FROM_EMAIL","hello@recosa.eu")},
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": f"<p>{body}</p><p>Generated by <strong>RECOSA</strong> · recosa.eu</p>",
                "attachment": [{"name": filename, "content": _b64.b64encode(file_bytes).decode()}]
            },
            timeout=15,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


def _render_send_form(doc, slot_key, label, company):
    """Inline 'send by email' form for one document row."""
    with st.form(key=f"form_send_{slot_key}"):
        send_to = st.text_input("Recipient email ✱", placeholder="colleague@company.com",
                                key=f"to_{slot_key}")
        available = []
        # XLSX first for registers: it is the working copy, and the format a
        # supervisory authority is used to receiving a record in.
        if doc.get("file_path_xlsx"): available.append("XLSX")
        if doc.get("file_path_docx"): available.append("DOCX")
        if doc.get("file_path_pdf"):  available.append("PDF")
        if doc.get("file_path_odt"):  available.append("ODT")
        if not available:
            st.caption("No files stored for this document.")
            st.form_submit_button("Send", disabled=True)
            return
        send_fmt = st.selectbox("Format", options=available, key=f"fmt_{slot_key}")
        submitted = st.form_submit_button("📤 Send", type="primary")

    if not submitted:
        return
    if not send_to.strip():
        st.error("Please enter a recipient email.")
        return

    fmt_map = {"DOCX": ("file_path_docx", ".docx"),
               "PDF":  ("file_path_pdf",  ".pdf"),
               "ODT":  ("file_path_odt",  ".odt"),
               "XLSX": ("file_path_xlsx", ".xlsx")}
    path_key, ext = fmt_map[send_fmt]
    fpath = doc.get(path_key)
    if not fpath:
        st.error("File not in storage.")
        return
    try:
        admin = get_supabase_admin()
        file_bytes = admin.storage.from_("compliance-files").download(fpath)
        fname = f"RECOSA_{doc.get('document_type','')}_{company}{ext}".replace(" ","_")
        ok = _send_email(
            to=send_to.strip(),
            subject=f"{label} — {company}",
            body=f"Please find attached the {label} generated by RECOSA for {company}.",
            file_bytes=file_bytes,
            filename=fname,
        )
        if ok:
            st.success(f"✅ Sent to {send_to.strip()}")
            st.session_state[f"send_open_{slot_key}"] = False
            st.rerun()
        else:
            st.error("Send failed — check Brevo API key.")
    except Exception as e:
        st.error(f"Error: {e}")


def _render_language_row(doc, slot_key, label, company, reg=None,
                         successor=None):
    """One language of a generation: status, links, outstanding badge, send.

    S27: the history is built from the `documents` generation log, which has no
    versions or statuses — those live in client_documents. Without the register
    row this listed a date and a language and left the reader to work out which
    of five files their organisation actually operates under, which is the
    question the whole sprint exists to answer.

    `reg` is the matching register row, or None where there is none: documents
    generated before S27, or generated outside a client context. `successor`
    is the register row that superseded it, where one exists.
    """
    lang = (doc.get("language") or "").upper() or "—"
    outstanding = doc.get("outstanding_fields") or []
    n_out = len(outstanding) if isinstance(outstanding, list) else 0

    c0, c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1, 1])
    # Version FIRST, then what happened to it.
    #
    # "Superseded v1" read as "superseded BY v1", which is the opposite of what
    # it meant. The version a row IS and the version that replaced it are
    # different facts and both matter to a reader working out what applied
    # when, so both are stated.
    badge = f"**{lang}**"
    if reg:
        _status = reg.get("status")
        _v = reg.get("version")
        _vlabel = f"v{_v}" if _v else ""
        if _status == "in_force":
            badge += f" · **{_vlabel}** · :green[In force]"
            if reg.get("effective_from"):
                badge += f" from {reg['effective_from']}"
        elif _status == "draft":
            # The distinction the adoption step exists to make: produced, and
            # not the thing the organisation operates under. No version — one
            # is assigned at adoption, so that a discarded draft leaves no gap
            # in the published sequence.
            badge += " · :orange[Draft — not adopted]"
        elif _status == "superseded":
            badge += f" · **{_vlabel}** · :gray[superseded"
            if successor and successor.get("version"):
                badge += f" by v{successor['version']}"
            if reg.get("superseded_on"):
                badge += f" on {reg['superseded_on']}"
            badge += "]"
        elif _status == "archived":
            badge += f" · **{_vlabel}** · :gray[archived"
            if reg.get("superseded_on"):
                badge += f" on {reg['superseded_on']}"
            badge += " — no longer applicable]"
    if n_out:
        badge += f" · :orange[{n_out} to complete]"
    c0.markdown(badge)
    if reg and reg.get("change_comment"):
        c0.caption(reg["change_comment"])

    for col, path_key, flabel in [
        (c1, "file_path_xlsx", "XLSX"),
        (c2, "file_path_docx", "DOCX"),
        (c3, "file_path_pdf",  "PDF"),
        (c4, "file_path_odt",  "ODT"),
    ]:
        fpath = doc.get(path_key)
        url = get_signed_url("compliance-files", fpath, expires_in=300) if fpath else None
        if url:
            col.link_button(flabel, url, use_container_width=True)
        else:
            col.caption("—")

    open_key = f"send_open_{slot_key}"
    if c5.button("✉", key=f"btn_send_{slot_key}", use_container_width=True,
                 help="Send by email"):
        st.session_state[open_key] = not st.session_state.get(open_key, False)
        st.rerun()

    if st.session_state.get(open_key, False):
        _render_send_form(doc, slot_key, label, company)

    # Adoption (S27). Rendered here rather than under the generated document,
    # because this section runs on every rerun and the generation branch does
    # not — see the note above the templated path.
    #
    # Toggled through session_state like the send form: the date and the note
    # need to survive the rerun between opening the control and pressing the
    # button.
    if reg and reg.get("status") == "draft":
        adopt_key = f"adopt_open_{reg['id']}"
        _b1, _b2 = c0.columns(2)
        if _b1.button("Put in force", key=f"btn_adopt_open_{reg['id']}",
                      help="Record this as the version your organisation operates under"):
            st.session_state[adopt_key] = not st.session_state.get(adopt_key, False)
            st.session_state[f"del_open_{reg['id']}"] = False
            st.rerun()

        # Deleting a draft is safe: no version was assigned, so it leaves no
        # gap in the published sequence, and nothing supersedes it. Only
        # drafts — database.delete_draft_document refuses anything else, and
        # the guard lives there rather than here.
        del_key = f"del_open_{reg['id']}"
        if _b2.button("Discard", key=f"btn_del_open_{reg['id']}",
                      help="Delete this draft and its files"):
            st.session_state[del_key] = not st.session_state.get(del_key, False)
            st.session_state[adopt_key] = False
            st.rerun()

        if st.session_state.get(del_key, False):
            with st.container(border=True):
                st.caption(
                    "Deleting this draft removes it and its files for good. "
                    "Nothing else is affected — it was never in force, so no "
                    "version number and no other version depends on it."
                )
                _d1, _d2 = st.columns(2)
                if _d1.button("Delete draft", key=f"btn_del_go_{reg['id']}",
                              type="primary"):
                    from database import delete_draft_document
                    if delete_draft_document(reg["id"], reg["user_id"]):
                        st.session_state[del_key] = False
                        st.rerun()
                    else:
                        st.warning(
                            "Could not delete the draft. Nothing has changed."
                        )
                if _d2.button("Keep it", key=f"btn_del_no_{reg['id']}"):
                    st.session_state[del_key] = False
                    st.rerun()

        if st.session_state.get(adopt_key, False):
            from datetime import date as _date
            from database import adopt_client_document, get_current_client_documents

            _live = (get_current_client_documents(
                reg["client_id"], reg["user_id"], reg["language"]) or {}
            ).get(reg["document_type"])
            _live_here = _live if (_live or {}).get("language") == reg["language"] else None

            with st.container(border=True):
                if _live_here:
                    st.caption(
                        f"This supersedes v{_live_here.get('version')} "
                        f"({reg['language'].upper()}), in force since "
                        f"{_live_here.get('effective_from') or 'an unrecorded date'}. "
                        "That version is kept as the record of what applied "
                        "until now."
                    )
                else:
                    st.caption(
                        f"Nothing is in force for this document in "
                        f"{reg['language'].upper()} yet."
                    )

                a1, a2 = st.columns([1, 2])
                with a1:
                    _eff = st.date_input(
                        "In force from", value=_date.today(),
                        key=f"adopt_eff_{reg['id']}",
                        help=(
                            "The date this version begins to apply — not the "
                            "date it was generated. Backdate it if it was "
                            "already signed or published."
                        ),
                    )
                with a2:
                    _note = st.text_input(
                        "What changed (optional)",
                        key=f"adopt_note_{reg['id']}",
                        placeholder="e.g. Reviewed by counsel, sub-processor added",
                    )

                if st.button("Confirm", key=f"btn_adopt_go_{reg['id']}",
                             type="primary"):
                    _res = adopt_client_document(
                        reg["id"], user_id=reg["user_id"],
                        effective_from=_eff, change_comment=_note or None,
                    )
                    if _res:
                        st.session_state[adopt_key] = False
                        st.success(
                            f"In force as v{_res.get('version')} "
                            f"({reg['language'].upper()}) from {_eff.isoformat()}."
                        )
                        st.rerun()
                    else:
                        st.warning(
                            "Could not put the document in force. Nothing has "
                            "changed — the previous version is still the one "
                            "that counts."
                        )


st.divider()
st.subheader("📚 Document history")

history = load_document_files(user_id, client_id if mode == "existing_client" else None)

# S27. Register rows keyed by the generation they came from, so each history
# row can say whether it is in force, a draft, or superseded — and at what
# version.
#
# Keyed on document_id where present, and falling back to the docx path for
# rows written before S27 added that link. The fallback matters: without it
# every document generated before today would show no status at all, which
# reads as "not adopted" rather than "we did not record it".
_reg_by_doc: dict[str, dict] = {}
_reg_by_path: dict[str, dict] = {}
_reg_by_id: dict[str, dict] = {}
if client_id and mode == "existing_client":
    try:
        from database import get_supabase
        for _r in (get_supabase().table("client_documents")
                   .select("*").eq("client_id", client_id)
                   .eq("user_id", user_id).execute().data or []):
            _reg_by_id[_r["id"]] = _r
            if _r.get("document_id"):
                _reg_by_doc[_r["document_id"]] = _r
            if _r.get("file_path"):
                _reg_by_path[_r["file_path"]] = _r
    except Exception:
        # The history is still worth showing without statuses.
        pass


def _reg_for(doc: dict) -> dict | None:
    return (_reg_by_doc.get(doc.get("id"))
            or _reg_by_path.get(doc.get("file_path_docx") or ""))


def _successor_of(reg: dict | None) -> dict | None:
    """The register row that superseded this one, if any."""
    return _reg_by_id.get((reg or {}).get("superseded_by") or "")


if not history:
    st.caption("No documents generated yet.")
else:
    # 1. Collapse rows into generations.
    groups: dict[str, list[dict]] = {}
    for doc in history:
        gid = doc.get("document_group_id") or f"single:{doc.get('id')}"
        groups.setdefault(gid, []).append(doc)

    def _group_ts(rows):
        return max((r.get("generated_at") or "") for r in rows)

    # 2. Order generations newest first, then bucket by document type.
    ordered = sorted(groups.items(), key=lambda kv: _group_ts(kv[1]), reverse=True)

    by_type: dict[str, list[tuple[str, list[dict]]]] = {}
    for gid, rows in ordered:
        by_type.setdefault(rows[0].get("document_type", ""), []).append((gid, rows))

    expected_langs = [
        l.lower() for l in ((selected_client or {}).get("document_languages") or [])
    ]

    for doc_type_key, generations in by_type.items():
        label = DOCUMENT_TYPES.get(doc_type_key, doc_type_key)
        current_gid, current_rows = generations[0]
        company = current_rows[0].get("company_name", "")

        st.markdown(f"### {label}")

        present = sorted({(r.get("language") or "").lower()
                          for r in current_rows if r.get("language")})
        missing = [l for l in expected_langs if l not in present]

        meta = _fmt_ts(_group_ts(current_rows))
        if present:
            meta += "  ·  " + ", ".join(l.upper() for l in present)
        st.caption(meta)

        if missing:
            # Derived, not stored: the client's document_languages minus the
            # languages actually in this generation.
            st.warning(
                "Not available in "
                + ", ".join(l.upper() for l in missing)
                + " — no in-force template in that language yet."
            )

        for row in sorted(current_rows, key=lambda r: (r.get("language") or "")):
            _cur_reg = _reg_for(row)
            _render_language_row(row, f"cur_{row.get('id')}", label, company,
                                 reg=_cur_reg, successor=_successor_of(_cur_reg))

        older = generations[1:]
        if older:
            with st.expander(f"Previous versions ({len(older)})"):
                for gid, rows in older:
                    langs = sorted({(r.get("language") or "").upper()
                                    for r in rows if r.get("language")})
                    st.caption(
                        _fmt_ts(_group_ts(rows))
                        + ("  ·  " + ", ".join(langs) if langs else "")
                    )
                    for row in sorted(rows, key=lambda r: (r.get("language") or "")):
                        _old_reg = _reg_for(row)
                        _render_language_row(
                            row, f"old_{row.get('id')}", label, company,
                            reg=_old_reg, successor=_successor_of(_old_reg))
                    st.divider()

        st.divider()
