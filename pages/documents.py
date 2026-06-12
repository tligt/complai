import os
import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import load_clients
from document_generator import (
    DOCUMENT_TYPES, LEGAL_FORMS, DPA_CONTACTS,
    load_intake, save_intake, update_client_profile,
    save_document_with_files, load_document_history,
    suggest_processing_activities,
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
if doc_type in ["privacy_policy", "ropa", "cookie_policy"] and (selected_client or mode == "external_company"):
    st.divider()
    col_ai1, col_ai2 = st.columns([3, 1])
    col_ai1.markdown("**🤖 Let AI suggest processing activities based on your profile**")
    col_ai1.caption(
        "COMPLAI will analyse your company sector, size and country to suggest "
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

if doc_type == "privacy_policy":
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

elif doc_type == "dpa":
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
if doc_type in ["privacy_policy", "ropa"]:
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

# ── Generate ──────────────────────────────────────────────────
st.divider()
generate = st.button(
    f"⚡ Generate {DOCUMENT_TYPES[doc_type]}",
    type="primary",
    use_container_width=True,
    key=f"btn_gen_{context_key}"
)

if generate:
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
    fname = f"COMPLAI_{doc_type}_{company_display.replace(' ','_')}"
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
                "sender": {"name": _os.environ.get("BREVO_FROM_NAME","COMPLAI"), "email": _os.environ.get("BREVO_FROM_EMAIL","audit@complai.be")},
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": f"<p>{body}</p><p>Generated by <strong>COMPLAI</strong> · complai.be</p>",
                "attachment": [{"name": filename, "content": _b64.b64encode(file_bytes).decode()}]
            },
            timeout=15,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False

st.divider()
st.subheader("📚 Document history")
history = load_document_files(user_id, client_id if mode == "existing_client" else None)

if history:
    # Column headers
    h0, h1, h2, h3, h4, h5 = st.columns([3, 2, 1, 1, 1, 1])
    h0.caption("**Document**")
    h1.caption("**Generated**")
    h2.caption("**DOCX**")
    h3.caption("**PDF**")
    h4.caption("**ODT**")
    h5.caption("**Send**")

    for idx, doc in enumerate(history):
        dt  = _fmt_ts(doc.get("generated_at",""))
        lbl = DOCUMENT_TYPES.get(doc.get("document_type",""), doc.get("document_type",""))
        company = doc.get("company_name","")
        lang    = doc.get("language","").upper()

        c0, c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 1, 1])
        c0.markdown(f"**{lbl}**")
        c0.caption(f"{company} · {lang}")
        c1.caption(dt)

        for col, path_key, label in [
            (c2, "file_path_docx", "DOCX"),
            (c3, "file_path_pdf",  "PDF"),
            (c4, "file_path_odt",  "ODT"),
        ]:
            fpath = doc.get(path_key)
            if fpath:
                url = get_signed_url("compliance-files", fpath, expires_in=300)
                if url:
                    col.link_button(label, url, use_container_width=True)
                else:
                    col.caption("—")
            else:
                col.caption("—")

        # Send button
        send_open_key = f"send_open_{idx}"
        if c5.button("✉", key=f"btn_send_{idx}", use_container_width=True, help="Send by email"):
            st.session_state[send_open_key] = not st.session_state.get(send_open_key, False)
            st.rerun()

        # Inline send form
        if st.session_state.get(send_open_key, False):
            with st.form(key=f"form_send_{idx}"):
                send_to = st.text_input("Recipient email ✱", placeholder="colleague@company.com", key=f"to_{idx}")
                available = []
                if doc.get("file_path_docx"): available.append("DOCX")
                if doc.get("file_path_pdf"):  available.append("PDF")
                if doc.get("file_path_odt"):  available.append("ODT")
                send_fmt = st.selectbox("Format", options=available, key=f"fmt_{idx}")
                submitted = st.form_submit_button("📤 Send", type="primary")

            if submitted:
                if not send_to.strip():
                    st.error("Please enter a recipient email.")
                else:
                    fmt_map = {
                        "DOCX": ("file_path_docx", ".docx"),
                        "PDF":  ("file_path_pdf",  ".pdf"),
                        "ODT":  ("file_path_odt",  ".odt"),
                    }
                    path_key, ext = fmt_map[send_fmt]
                    fpath = doc.get(path_key)
                    if fpath:
                        try:
                            admin = get_supabase_admin()
                            file_bytes = admin.storage.from_("compliance-files").download(fpath)
                            fname = f"COMPLAI_{doc.get('document_type','')}_{company}{ext}".replace(" ","_")
                            ok = _send_email(
                                to=send_to.strip(),
                                subject=f"{lbl} — {company}",
                                body=f"Please find attached the {lbl} generated by COMPLAI for {company}.",
                                file_bytes=file_bytes,
                                filename=fname,
                            )
                            if ok:
                                st.success(f"✅ Sent to {send_to.strip()}")
                                st.session_state[send_open_key] = False
                                st.rerun()
                            else:
                                st.error("Send failed — check Brevo API key.")
                        except Exception as e:
                            st.error(f"Error: {e}")
                    else:
                        st.error("File not in storage.")

        st.divider()
else:
    st.caption("No documents generated yet.")