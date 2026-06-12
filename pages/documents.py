import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import load_clients, get_supabase
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

# ── Client selection ──────────────────────────────────────────
clients = load_clients(user_id)

if not clients:
    st.info("👈 Create a client profile first before generating documents.")
    st.stop()

# Advisory mode: can also generate for an external company
mode = st.radio(
    "Generate for:",
    options=["existing_client", "external_company"],
    format_func=lambda x: "Existing client profile" if x == "existing_client" else "External company (Advisory)",
    horizontal=True,
    key="doc_mode"
)

selected_client = None
if mode == "existing_client":
    client_names = [c["company_name"] for c in clients]
    chosen = st.selectbox("Select client", options=client_names, key="doc_client_select")
    selected_client = next((c for c in clients if c["company_name"] == chosen), None)
    client_id = selected_client["id"] if selected_client else None
else:
    client_id = None
    st.info("Advisory mode — fill in the external company details in the form below.")

st.divider()

# ── Document type selection ───────────────────────────────────
doc_type = st.selectbox(
    "Document type",
    options=list(DOCUMENT_TYPES.keys()),
    format_func=lambda x: DOCUMENT_TYPES[x],
    key="doc_type_select"
)

language = st.selectbox(
    "Document language",
    options=["en", "fr", "nl"],
    format_func=lambda x: {"en": "🇬🇧 English", "fr": "🇫🇷 French", "nl": "🇳🇱 Dutch"}[x],
    index=0 if not selected_client else ["en","fr","nl"].index(selected_client.get("language","en")) if selected_client.get("language","en") in ["en","fr","nl"] else 0,
    key="doc_lang_select"
)

st.divider()

# ── Load existing intake if available ────────────────────────
existing_intake = {}
if client_id:
    existing_intake = load_intake(client_id, user_id, doc_type)

# ── Intake form ───────────────────────────────────────────────
st.subheader("Company information")
st.caption("Fields marked ✱ are required. Previously entered data is pre-filled.")

with st.form(key="document_intake_form"):

    # ── Universal profile fields ──────────────────────────────
    col1, col2 = st.columns(2)

    # Legal name
    default_legal = (
        existing_intake.get("legal_name") or
        (selected_client.get("legal_name") if selected_client else "") or
        (selected_client.get("company_name") if selected_client else "") or ""
    )
    legal_name = col1.text_input("Legal company name ✱", value=default_legal, key="f_legal_name")

    # Legal form
    country_key = (
        existing_intake.get("country") or
        (selected_client.get("country") if selected_client else "BE") or "BE"
    )
    form_options = LEGAL_FORMS.get(country_key, LEGAL_FORMS["EU"])
    default_form = existing_intake.get("legal_form") or (selected_client.get("legal_form") if selected_client else "")
    default_form_idx = form_options.index(default_form) if default_form in form_options else 0
    legal_form = col2.selectbox("Legal form ✱", options=form_options, index=default_form_idx, key="f_legal_form")

    # Country
    country_options = {"BE": "🇧🇪 Belgium", "FR": "🇫🇷 France", "NL": "🇳🇱 Netherlands",
                       "DE": "🇩🇪 Germany", "LU": "🇱🇺 Luxembourg", "EU": "🇪🇺 Other EU"}
    default_country = existing_intake.get("country") or (selected_client.get("country") if selected_client else "BE")
    country = st.selectbox(
        "Country of establishment ✱",
        options=list(country_options.keys()),
        format_func=lambda x: country_options[x],
        index=list(country_options.keys()).index(default_country) if default_country in country_options else 0,
        key="f_country"
    )

    # Website URL
    default_url = (
        existing_intake.get("website_url") or
        (selected_client.get("website_url") if selected_client else "") or ""
    )
    website_url = st.text_input("Website URL", value=default_url, placeholder="https://yourcompany.com", key="f_url")

    # DPO
    col3, col4 = st.columns(2)
    default_dpo_name = existing_intake.get("dpo_name") or (selected_client.get("dpo_name") if selected_client else "") or ""
    default_dpo_email = existing_intake.get("dpo_email") or (selected_client.get("dpo_email") if selected_client else "") or ""
    dpo_name = col3.text_input("DPO name (if appointed)", value=default_dpo_name, key="f_dpo_name")
    dpo_email = col4.text_input("DPO email", value=default_dpo_email, key="f_dpo_email")

    # Contact email
    default_contact = existing_intake.get("contact_email") or (selected_client.get("contact_email") if selected_client else "") or ""
    contact_email = st.text_input("Contact email for data requests ✱", value=default_contact, key="f_contact")

    # ── Document-specific fields ──────────────────────────────
    st.divider()
    st.markdown(f"**{DOCUMENT_TYPES[doc_type]} specific information**")

    if doc_type == "privacy_policy":
        processing_activities = st.text_area(
            "Processing activities ✱ — describe what personal data you collect and why",
            value=existing_intake.get("processing_activities", ""),
            height=120,
            placeholder="e.g. Contact form data (name, email) for responding to enquiries; account data for service delivery; analytics data to improve the website...",
            key="f_processing"
        )
        third_party_processors = st.text_area(
            "Third-party processors — list tools and services that process personal data",
            value=existing_intake.get("third_party_processors", ""),
            height=100,
            placeholder="e.g. Google Analytics (analytics), Stripe (payments), Mailchimp (email marketing), AWS (hosting)...",
            key="f_processors"
        )
        international_transfers = st.checkbox(
            "Do you transfer personal data outside the EU/EEA?",
            value=existing_intake.get("international_transfers", False),
            key="f_transfers"
        )
        retention_periods = st.text_area(
            "Retention periods — how long do you keep each type of data?",
            value=existing_intake.get("retention_periods", ""),
            height=100,
            placeholder="e.g. Contact form data: 2 years; Account data: duration of contract + 5 years; Analytics: 13 months...",
            key="f_retention"
        )
        processor_name = None; processor_country = None; processing_purpose = None
        incident_response_contact = None; escalation_procedure = None

    elif doc_type == "cookie_policy":
        third_party_processors = st.text_area(
            "Cookies used ✱ — list each cookie, its purpose, and duration",
            value=existing_intake.get("third_party_processors", ""),
            height=120,
            placeholder="e.g. _ga (Google Analytics, analytics, 2 years); _stripe_mid (Stripe, payment security, 1 year); session_id (session management, session)...",
            key="f_cookies"
        )
        processing_activities = None; international_transfers = False; retention_periods = None
        processor_name = None; processor_country = None; processing_purpose = None
        incident_response_contact = None; escalation_procedure = None

    elif doc_type == "dpa":
        processor_name = st.text_input(
            "Processor name ✱ — company that processes data on your behalf",
            value=existing_intake.get("processor_name", ""),
            key="f_proc_name"
        )
        processor_country = st.text_input(
            "Processor country",
            value=existing_intake.get("processor_country", ""),
            key="f_proc_country"
        )
        processing_purpose = st.text_area(
            "Purpose of processing ✱",
            value=existing_intake.get("processing_purpose", ""),
            height=80,
            key="f_proc_purpose"
        )
        processing_activities = st.text_area(
            "Personal data involved ✱",
            value=existing_intake.get("processing_activities", ""),
            height=80,
            key="f_processing"
        )
        third_party_processors = None; international_transfers = False
        retention_periods = None; incident_response_contact = None; escalation_procedure = None

    elif doc_type == "ropa":
        processing_activities = st.text_area(
            "Processing activities ✱ — list each activity with data types, purposes, and legal basis",
            value=existing_intake.get("processing_activities", ""),
            height=150,
            placeholder="e.g.\n1. Customer management — name, email, contract data — contract performance (Art. 6(1)(b))\n2. Marketing — email, preferences — consent (Art. 6(1)(a))\n3. HR — employee data — legal obligation (Art. 6(1)(c))",
            key="f_processing"
        )
        third_party_processors = st.text_area(
            "Third-party recipients",
            value=existing_intake.get("third_party_processors", ""),
            height=80,
            key="f_processors"
        )
        retention_periods = st.text_area(
            "Retention periods",
            value=existing_intake.get("retention_periods", ""),
            height=80,
            key="f_retention"
        )
        international_transfers = st.checkbox(
            "International transfers outside EU/EEA?",
            value=existing_intake.get("international_transfers", False),
            key="f_transfers"
        )
        processor_name = None; processor_country = None; processing_purpose = None
        incident_response_contact = None; escalation_procedure = None

    elif doc_type == "incident_response":
        incident_response_contact = st.text_input(
            "Primary incident response contact ✱ (name, role, email, phone)",
            value=existing_intake.get("incident_response_contact", ""),
            key="f_ir_contact"
        )
        escalation_procedure = st.text_area(
            "Escalation procedure — who gets notified and in what order",
            value=existing_intake.get("escalation_procedure", ""),
            height=100,
            placeholder="e.g. 1. IT Manager → 2. CEO → 3. Legal counsel → 4. CCB (within 24h) → 5. Affected individuals...",
            key="f_escalation"
        )
        processing_activities = st.text_area(
            "Critical systems and assets to protect",
            value=existing_intake.get("processing_activities", ""),
            height=80,
            key="f_systems"
        )
        third_party_processors = None; international_transfers = False
        retention_periods = None; processor_name = None
        processor_country = None; processing_purpose = None

    elif doc_type == "ai_transparency":
        processing_activities = st.text_area(
            "AI system description ✱ — what AI system(s) do you use and how do users interact with them?",
            value=existing_intake.get("processing_activities", ""),
            height=120,
            placeholder="e.g. AI-powered chatbot on our website that answers customer questions about our products. The system uses large language model technology to generate responses...",
            key="f_ai_desc"
        )
        third_party_processors = st.text_input(
            "AI provider / model used",
            value=existing_intake.get("third_party_processors", ""),
            placeholder="e.g. Mistral AI, OpenAI GPT-4, etc.",
            key="f_ai_provider"
        )
        international_transfers = False; retention_periods = None
        processor_name = None; processor_country = None; processing_purpose = None
        incident_response_contact = None; escalation_procedure = None

    st.divider()

    col_gen, col_cancel = st.columns([3, 1])
    submitted = col_gen.form_submit_button(
        f"⚡ Generate {DOCUMENT_TYPES[doc_type]}",
        type="primary",
        use_container_width=True
    )

# ── Form submission ───────────────────────────────────────────
if submitted:
    if not legal_name.strip():
        st.error("Legal company name is required.")
        st.stop()
    if not contact_email.strip() and doc_type in ["privacy_policy", "ropa"]:
        st.error("Contact email for data requests is required.")
        st.stop()

    # Build intake dict
    intake_data = {
        "legal_name": legal_name.strip(),
        "legal_form": legal_form,
        "country": country,
        "website_url": website_url.strip(),
        "dpo_name": dpo_name.strip(),
        "dpo_email": dpo_email.strip(),
        "contact_email": contact_email.strip(),
        "processing_activities": processing_activities.strip() if processing_activities else "",
        "third_party_processors": third_party_processors.strip() if third_party_processors else "",
        "international_transfers": international_transfers if isinstance(international_transfers, bool) else False,
        "retention_periods": retention_periods.strip() if retention_periods else "",
        "processor_name": processor_name.strip() if processor_name else "",
        "processor_country": processor_country.strip() if processor_country else "",
        "processing_purpose": processing_purpose.strip() if processing_purpose else "",
        "incident_response_contact": incident_response_contact.strip() if incident_response_contact else "",
        "escalation_procedure": escalation_procedure.strip() if escalation_procedure else "",
    }

    # Save intake + update client profile
    if client_id:
        save_intake(client_id, user_id, doc_type, intake_data)
        # Update universal fields on client profile
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
        # Get regulatory context
        reg_context = get_regulatory_context(doc_type, language, country)

        # Generate document text
        client_data = selected_client or {}
        doc_text = generate_document_text(
            document_type=doc_type,
            intake=intake_data,
            client=client_data,
            language=language,
            regulatory_context=reg_context,
        )

        # Build DOCX
        docx_bytes = build_docx(doc_text, doc_type, company_display, language)

    st.success(f"✅ {DOCUMENT_TYPES[doc_type]} generated for {company_display}")

    # Convert to PDF and ODT
    with st.spinner("Preparing PDF and ODT versions..."):
        try:
            pdf_bytes = convert_docx_to_pdf(docx_bytes)
            pdf_ok = True
        except Exception as e:
            pdf_ok = False
            pdf_error = str(e)

        try:
            odt_bytes = convert_docx_to_odt(docx_bytes)
            odt_ok = True
        except Exception as e:
            odt_ok = False
            odt_error = str(e)

    # Save record
    save_document_record(user_id, client_id, doc_type, language, company_display)

    # Download buttons
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
        col2.caption(f"PDF unavailable: {pdf_error}")

    if odt_ok:
        col3.download_button(
            label="📋 Download ODT",
            data=odt_bytes,
            file_name=f"{filename_base}.odt",
            mime="application/vnd.oasis.opendocument.text",
            use_container_width=True,
        )
    else:
        col3.caption(f"ODT unavailable: {odt_error}")

    st.divider()

    # Preview
    with st.expander("📖 Preview generated content", expanded=False):
        st.markdown(doc_text)

    st.caption(
        "⚠️ This document was generated by AI based on the information you provided and official EU regulatory sources. "
        "It is intended as a starting point and should be reviewed by a qualified legal professional before use."
    )

# ── Document history ──────────────────────────────────────────
st.divider()
st.subheader("📚 Document history")

history = load_document_history(user_id, client_id if mode == "existing_client" else None)

if history:
    for doc in history:
        generated_at = doc.get("generated_at", "")[:10] if doc.get("generated_at") else ""
        doc_label = DOCUMENT_TYPES.get(doc.get("document_type", ""), doc.get("document_type", ""))
        company = doc.get("company_name", "")
        lang = doc.get("language", "").upper()
        st.caption(f"📄 {doc_label} — {company} — {lang} — {generated_at}")
else:
    st.caption("No documents generated yet.")
