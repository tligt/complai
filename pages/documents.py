import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import load_clients
from document_generator import (
    DOCUMENT_TYPES, LEGAL_FORMS, DPA_CONTACTS,
    load_intake, save_intake, update_client_profile,
    save_document_record, load_document_history,
    get_regulatory_context, generate_document_text,
    build_docx, convert_docx_to_pdf, convert_docx_to_odt,
)

st.set_page_config(
    page_title="COMPLAI — Document Generation",
    page_icon="📄",
    layout="centered"
)

init_auth()

if not is_logged_in():
    login_ui()
    st.stop()

user_id = get_user_id()

# ── Page header ───────────────────────────────────────────────
st.title("📄 Document Generation")
st.caption("Generate compliance documents tailored to your client's profile.")
st.divider()

# ── Session state init ────────────────────────────────────────
if "doc_activities" not in st.session_state:
    st.session_state.doc_activities = []
if "doc_processors" not in st.session_state:
    st.session_state.doc_processors = []
if "doc_retention" not in st.session_state:
    st.session_state.doc_retention = []
if "last_mode" not in st.session_state:
    st.session_state.last_mode = None
if "last_client_id" not in st.session_state:
    st.session_state.last_client_id = None

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
else:
    st.info("Advisory mode — fill in the external company details in the form below.")

# Detect mode/client switch — clear structured fields if changed
current_key = f"{mode}_{client_id}"
if current_key != st.session_state.last_mode:
    st.session_state.doc_activities = []
    st.session_state.doc_processors = []
    st.session_state.doc_retention = []
    st.session_state.last_mode = current_key

st.divider()

# ── Document type + language ──────────────────────────────────
doc_type = st.selectbox(
    "Document type",
    options=list(DOCUMENT_TYPES.keys()),
    format_func=lambda x: DOCUMENT_TYPES[x],
    key="doc_type_select"
)

language = st.selectbox(
    "Document language",
    options=["en", "fr", "nl"],
    format_func=lambda x: {"en": "EN — English", "fr": "FR — Français", "nl": "NL — Nederlands"}[x],
    key="doc_lang_select"
)

st.divider()

# ── Load existing intake ──────────────────────────────────────
existing_intake = {}
if client_id:
    existing_intake = load_intake(client_id, user_id, doc_type)

# Pre-fill helper — returns value only for existing clients, empty for external
def pf(field, default=""):
    """Pre-fill from intake or client profile only when in existing client mode."""
    if mode == "external_company":
        return default
    val = existing_intake.get(field)
    if val:
        return val
    if selected_client:
        return selected_client.get(field, default)
    return default

# ── Universal fields ──────────────────────────────────────────
st.subheader("Company information")
st.caption("Fields marked ✱ are required.")

col1, col2 = st.columns(2)
legal_name = col1.text_input("Legal company name ✱", value=pf("legal_name"), key="f_legal_name")

country_options = {
    "BE": "🇧🇪 Belgium", "FR": "🇫🇷 France", "NL": "🇳🇱 Netherlands",
    "DE": "🇩🇪 Germany", "LU": "🇱🇺 Luxembourg", "EU": "🇪🇺 Other EU"
}
default_country = pf("country", "BE")
country = col2.selectbox(
    "Country ✱",
    options=list(country_options.keys()),
    format_func=lambda x: country_options[x],
    index=list(country_options.keys()).index(default_country) if default_country in country_options else 0,
    key="f_country"
)

form_options = LEGAL_FORMS.get(country, LEGAL_FORMS["EU"])
default_form = pf("legal_form", "")
default_form_idx = form_options.index(default_form) if default_form in form_options else 0
legal_form = st.selectbox("Legal form ✱", options=form_options, index=default_form_idx, key="f_legal_form")

website_url = st.text_input("Website URL", value=pf("website_url"), placeholder="https://yourcompany.com", key="f_url")

col3, col4 = st.columns(2)
dpo_name = col3.text_input("DPO name (if appointed)", value=pf("dpo_name"), key="f_dpo_name")
dpo_email = col4.text_input("DPO email", value=pf("dpo_email"), key="f_dpo_email")
contact_email = st.text_input("Contact email for data requests ✱", value=pf("contact_email"), key="f_contact")

# ── Document-specific structured fields ───────────────────────
st.divider()
st.markdown(f"**{DOCUMENT_TYPES[doc_type]} — specific information**")

processor_name = None; processor_country = None; processing_purpose = None
incident_response_contact = None; escalation_procedure = None
processing_activities_text = ""
third_party_processors_text = ""
retention_periods_text = ""
international_transfers = False

# ── Helpers for structured tables ────────────────────────────

def activity_editor():
    """Structured processing activities editor."""
    st.markdown("**Processing activities ✱**")
    st.caption("Add one row per processing activity. The more detail you provide, the better the document.")

    # Load from existing intake if not yet in session
    if not st.session_state.doc_activities and existing_intake.get("processing_activities"):
        # Parse back from saved text into rows if possible
        pass

    for i, act in enumerate(st.session_state.doc_activities):
        with st.expander(f"Activity {i+1}: {act.get('name', 'Untitled')}", expanded=False):
            c1, c2 = st.columns(2)
            st.session_state.doc_activities[i]["name"] = c1.text_input(
                "Activity name", value=act.get("name", ""), key=f"act_name_{i}"
            )
            st.session_state.doc_activities[i]["subjects"] = c2.text_input(
                "Data subjects", value=act.get("subjects", ""), key=f"act_subj_{i}",
                placeholder="e.g. Customers, employees"
            )
            st.session_state.doc_activities[i]["data"] = st.text_input(
                "Personal data collected", value=act.get("data", ""), key=f"act_data_{i}",
                placeholder="e.g. Name, email, phone number"
            )
            c3, c4 = st.columns(2)
            st.session_state.doc_activities[i]["purpose"] = c3.text_input(
                "Purpose", value=act.get("purpose", ""), key=f"act_purp_{i}",
                placeholder="e.g. Delivering the contracted service"
            )
            legal_bases = [
                "Contract performance (Art. 6(1)(b))",
                "Consent (Art. 6(1)(a))",
                "Legal obligation (Art. 6(1)(c))",
                "Legitimate interests (Art. 6(1)(f))",
                "Vital interests (Art. 6(1)(d))",
                "Public task (Art. 6(1)(e))",
            ]
            current_basis = act.get("legal_basis", legal_bases[0])
            basis_idx = legal_bases.index(current_basis) if current_basis in legal_bases else 0
            st.session_state.doc_activities[i]["legal_basis"] = c4.selectbox(
                "Legal basis", options=legal_bases, index=basis_idx, key=f"act_basis_{i}"
            )
            if st.button(f"Remove activity {i+1}", key=f"rm_act_{i}"):
                st.session_state.doc_activities.pop(i)
                st.rerun()

    if st.button("➕ Add processing activity", key="add_activity"):
        st.session_state.doc_activities.append({
            "name": "", "subjects": "", "data": "", "purpose": "", "legal_basis": "Contract performance (Art. 6(1)(b))"
        })
        st.rerun()

    # Convert to text for generation
    lines = []
    for i, act in enumerate(st.session_state.doc_activities):
        if act.get("name"):
            lines.append(
                f"{i+1}. {act['name']}: collects {act.get('data','—')} from {act.get('subjects','—')} "
                f"for the purpose of {act.get('purpose','—')} — legal basis: {act.get('legal_basis','—')}"
            )
    return "\n".join(lines)


def processor_editor():
    """Structured third-party processor editor."""
    st.markdown("**Third-party processors**")
    st.caption("Add one row per tool or service that processes personal data on your behalf.")

    for i, proc in enumerate(st.session_state.doc_processors):
        with st.expander(f"Processor {i+1}: {proc.get('name', 'Untitled')}", expanded=False):
            c1, c2 = st.columns(2)
            st.session_state.doc_processors[i]["name"] = c1.text_input(
                "Service name", value=proc.get("name", ""), key=f"proc_name_{i}",
                placeholder="e.g. Google Analytics"
            )
            st.session_state.doc_processors[i]["country"] = c2.text_input(
                "Country", value=proc.get("country", ""), key=f"proc_country_{i}",
                placeholder="e.g. US, EU"
            )
            c3, c4 = st.columns(2)
            st.session_state.doc_processors[i]["purpose"] = c3.text_input(
                "Purpose", value=proc.get("purpose", ""), key=f"proc_purp_{i}",
                placeholder="e.g. Website analytics"
            )
            st.session_state.doc_processors[i]["data"] = c4.text_input(
                "Data shared", value=proc.get("data", ""), key=f"proc_data_{i}",
                placeholder="e.g. IP address, page views"
            )
            if st.button(f"Remove processor {i+1}", key=f"rm_proc_{i}"):
                st.session_state.doc_processors.pop(i)
                st.rerun()

    if st.button("➕ Add processor", key="add_processor"):
        st.session_state.doc_processors.append({"name": "", "country": "", "purpose": "", "data": ""})
        st.rerun()

    lines = []
    for proc in st.session_state.doc_processors:
        if proc.get("name"):
            lines.append(
                f"{proc['name']} ({proc.get('country','—')}): {proc.get('purpose','—')} — data shared: {proc.get('data','—')}"
            )
    return "\n".join(lines)


def retention_editor():
    """Structured retention periods editor."""
    st.markdown("**Retention periods**")
    st.caption("Specify how long each type of data is kept.")

    for i, ret in enumerate(st.session_state.doc_retention):
        c1, c2, c3 = st.columns([3, 2, 1])
        st.session_state.doc_retention[i]["data_type"] = c1.text_input(
            "Data type", value=ret.get("data_type", ""), key=f"ret_type_{i}",
            placeholder="e.g. Customer contact data", label_visibility="collapsed"
        )
        st.session_state.doc_retention[i]["duration"] = c2.text_input(
            "Duration", value=ret.get("duration", ""), key=f"ret_dur_{i}",
            placeholder="e.g. 3 years after contract end", label_visibility="collapsed"
        )
        if c3.button("✕", key=f"rm_ret_{i}"):
            st.session_state.doc_retention.pop(i)
            st.rerun()

    if not st.session_state.doc_retention:
        st.caption("Data type → Duration")

    if st.button("➕ Add retention rule", key="add_retention"):
        st.session_state.doc_retention.append({"data_type": "", "duration": ""})
        st.rerun()

    lines = []
    for ret in st.session_state.doc_retention:
        if ret.get("data_type"):
            lines.append(f"{ret['data_type']}: {ret.get('duration', '—')}")
    return "\n".join(lines)


# ── Document-specific form sections ───────────────────────────

if doc_type == "privacy_policy":
    processing_activities_text = activity_editor()
    st.divider()
    third_party_processors_text = processor_editor()
    st.divider()
    retention_periods_text = retention_editor()
    st.divider()
    international_transfers = st.checkbox(
        "Do you transfer personal data outside the EU/EEA?",
        value=pf("international_transfers", False),
        key="f_transfers"
    )

elif doc_type == "cookie_policy":
    third_party_processors_text = processor_editor()

elif doc_type == "dpa":
    processor_name = st.text_input(
        "Processor name ✱", value=pf("processor_name"), key="f_proc_name",
        placeholder="Company that processes data on your behalf"
    )
    col_a, col_b = st.columns(2)
    processor_country = col_a.text_input("Processor country", value=pf("processor_country"), key="f_proc_country")
    processing_purpose = col_b.text_input("Purpose of processing ✱", value=pf("processing_purpose"), key="f_proc_purpose")
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
        value=pf("international_transfers", False),
        key="f_transfers"
    )

elif doc_type == "incident_response":
    incident_response_contact = st.text_input(
        "Primary incident response contact ✱",
        value=pf("incident_response_contact"),
        placeholder="Name, role, email, phone",
        key="f_ir_contact"
    )
    escalation_procedure = st.text_area(
        "Escalation chain",
        value=pf("escalation_procedure"),
        height=100,
        placeholder="1. IT Manager → 2. CEO → 3. Legal counsel → 4. CCB/ANSSI (within 24h) → 5. Affected individuals",
        key="f_escalation"
    )
    processing_activities_text = st.text_area(
        "Critical systems and assets to protect",
        value=pf("processing_activities"),
        height=80,
        key="f_systems"
    )

elif doc_type == "ai_transparency":
    processing_activities_text = st.text_area(
        "AI system description ✱",
        value=pf("processing_activities"),
        height=120,
        placeholder="Describe your AI system and how users interact with it...",
        key="f_ai_desc"
    )
    third_party_processors_text = st.text_input(
        "AI provider / model used",
        value=pf("third_party_processors"),
        placeholder="e.g. Mistral AI, OpenAI GPT-4",
        key="f_ai_provider"
    )

# ── Generate button ───────────────────────────────────────────
st.divider()
generate = st.button(
    f"⚡ Generate {DOCUMENT_TYPES[doc_type]}",
    type="primary",
    use_container_width=True,
    key="btn_generate"
)

if generate:
    if not legal_name.strip():
        st.error("Legal company name is required.")
        st.stop()
    if not contact_email.strip() and doc_type in ["privacy_policy", "ropa"]:
        st.error("Contact email for data requests is required.")
        st.stop()
    if doc_type == "privacy_policy" and not st.session_state.doc_activities:
        st.error("Please add at least one processing activity.")
        st.stop()

    intake_data = {
        "legal_name": legal_name.strip(),
        "legal_form": legal_form,
        "country": country,
        "website_url": website_url.strip(),
        "dpo_name": dpo_name.strip(),
        "dpo_email": dpo_email.strip(),
        "contact_email": contact_email.strip(),
        "processing_activities": processing_activities_text,
        "third_party_processors": third_party_processors_text,
        "international_transfers": international_transfers,
        "retention_periods": retention_periods_text,
        "processor_name": processor_name or "",
        "processor_country": processor_country or "",
        "processing_purpose": processing_purpose or "",
        "incident_response_contact": incident_response_contact or "",
        "escalation_procedure": escalation_procedure or "",
    }

    if client_id:
        save_intake(client_id, user_id, doc_type, intake_data)
        update_client_profile(client_id, user_id, {
            "website_url": website_url.strip() or None,
            "dpo_name": dpo_name.strip() or None,
            "dpo_email": dpo_email.strip() or None,
            "contact_email": contact_email.strip() or None,
            "legal_name": legal_name.strip() or None,
            "legal_form": legal_form or None,
        })

    company_display = f"{legal_name.strip()} {legal_form}".strip()

    with st.spinner(f"Retrieving regulatory context and generating {DOCUMENT_TYPES[doc_type]}..."):
        reg_context = get_regulatory_context(doc_type, language, country)
        client_data = selected_client or {}
        doc_text = generate_document_text(
            document_type=doc_type,
            intake=intake_data,
            client=client_data,
            language=language,
            regulatory_context=reg_context,
        )
        docx_bytes = build_docx(doc_text, doc_type, company_display, language)

    st.success(f"✅ {DOCUMENT_TYPES[doc_type]} generated for {company_display}")

    with st.spinner("Preparing PDF and ODT versions..."):
        try:
            pdf_bytes = convert_docx_to_pdf(docx_bytes)
            pdf_ok = True
        except Exception as e:
            pdf_ok = False; pdf_error = str(e)

        try:
            odt_bytes = convert_docx_to_odt(docx_bytes)
            odt_ok = True
        except Exception as e:
            odt_ok = False; odt_error = str(e)

    save_document_record(user_id, client_id, doc_type, language, company_display)

    st.markdown("**Download your document:**")
    filename_base = f"COMPLAI_{doc_type}_{company_display.replace(' ', '_')}"

    col1, col2, col3 = st.columns(3)
    col1.download_button(
        label="📝 Download DOCX",
        data=docx_bytes,
        file_name=f"{filename_base}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
        type="primary",
    )
    if pdf_ok:
        col2.download_button(
            label="📄 Download PDF",
            data=pdf_bytes,
            file_name=f"{filename_base}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        col2.caption(f"PDF unavailable")

    if odt_ok:
        col3.download_button(
            label="📋 Download ODT",
            data=odt_bytes,
            file_name=f"{filename_base}.odt",
            mime="application/vnd.oasis.opendocument.text",
            use_container_width=True,
        )
    else:
        col3.caption(f"ODT unavailable")

    st.divider()
    with st.expander("📖 Preview generated content", expanded=False):
        st.markdown(doc_text)

    st.caption(
        "⚠️ This document was generated by AI based on the information you provided and official EU regulatory sources. "
        "It is a starting point — review with a qualified legal professional before use."
    )

# ── Document history ──────────────────────────────────────────
st.divider()
st.subheader("📚 Document history")
history = load_document_history(user_id, client_id if mode == "existing_client" else None)
if history:
    for doc in history:
        generated_at = doc.get("generated_at", "")[:10] if doc.get("generated_at") else ""
        doc_label = DOCUMENT_TYPES.get(doc.get("document_type", ""), doc.get("document_type", ""))
        st.caption(f"📄 {doc_label} — {doc.get('company_name','')} — {doc.get('language','').upper()} — {generated_at}")
else:
    st.caption("No documents generated yet.")
