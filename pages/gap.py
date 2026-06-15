import os
import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import (
    load_clients, get_signed_url, upload_file,
    get_current_client_documents, register_client_document,
)
from gap_assessment import (
    OBLIGATIONS, PROFILE_QUESTIONS, DOCUMENT_TYPES,
    extract_text_from_upload, run_gap_assessment,
    generate_gap_report_pdf, save_gap_assessment,
    load_gap_assessment_history,
)

st.set_page_config(
    page_title="COMPLAI — Gap Assessment",
    page_icon="🔍",
    layout="centered"
)

init_auth()

if not is_logged_in():
    login_ui()
    st.stop()

user_id = get_user_id()

st.title("🔍 Gap Assessment")
st.caption(
    "Upload your current compliance documents and we'll assess each one against "
    "its specific regulatory obligations. Missing documents are automatically flagged as gaps."
)
st.divider()

# ── Client selection ──────────────────────────────────────────
clients = load_clients(user_id)
if not clients:
    st.info("👈 Create a client profile first before running a gap assessment.")
    st.stop()

client_names = [c["company_name"] for c in clients]
chosen = st.selectbox("Select client", options=client_names, key="gap_client")
selected_client = next((c for c in clients if c["company_name"] == chosen), None)
client_id = selected_client["id"] if selected_client else None

st.divider()

# ── Step 1: Document repository ───────────────────────────────
st.subheader("Step 1 — Document repository")
st.caption(
    "These are the current versions of your compliance documents. "
    "Upload a new or updated version to replace the current one. "
    "COMPLAI-generated documents are automatically registered here."
)

# Load current documents from DB
current_docs = get_current_client_documents(client_id, user_id) if client_id else {}

# Show each document type with status and upload option
uploaded_texts = {}  # {doc_type: extracted_text} from new uploads this session

doc_types_ordered = [
    "privacy_policy", "cookie_policy", "dpa",
    "ropa", "incident_response", "ai_transparency"
]

for doc_type in doc_types_ordered:
    label = DOCUMENT_TYPES[doc_type]
    current = current_docs.get(doc_type)

    col_status, col_info, col_upload = st.columns([1, 4, 2])

    if current:
        col_status.markdown("✅")
        src = "COMPLAI" if current.get("source") == "complai_generated" else "Uploaded"
        ts = current.get("uploaded_at", "")[:10]
        col_info.markdown(f"**{label}**")
        col_info.caption(f"v{current.get('version',1)} · {src} · {ts}")
        if current.get("change_comment"):
            col_info.caption(f"_{current['change_comment']}_")
    else:
        col_status.markdown("⬜")
        col_info.markdown(f"**{label}**")
        col_info.caption("Not provided")

    # Upload new version
    new_file = col_upload.file_uploader(
        "Upload" if not current else "Update",
        type=["pdf","docx","txt"],
        key=f"upload_{doc_type}",
        label_visibility="collapsed",
    )

    if new_file:
        text = extract_text_from_upload(new_file)
        if text.strip():
            uploaded_texts[doc_type] = text
            col_info.success(f"✅ {new_file.name} ready")

            # Ask for change comment if updating
            if current:
                comment = st.text_input(
                    f"What changed in this version? (optional)",
                    key=f"comment_{doc_type}",
                    placeholder="e.g. Updated retention periods after external audit"
                )
            else:
                comment = ""

            # Upload to storage and register
            if client_id:
                import re
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe = re.sub(r"[^a-zA-Z0-9_-]", "_", new_file.name)[:30]
                path = f"{user_id}/{client_id}/COMPLAI_{doc_type}_{ts}_{safe}"
                stored = upload_file(
                    "compliance-files", path,
                    new_file.getvalue(),
                    "application/octet-stream"
                )
                if stored:
                    register_client_document(
                        user_id=user_id,
                        client_id=client_id,
                        document_type=doc_type,
                        file_path=path,
                        source="client_upload",
                        change_comment=comment,
                    )
                    # Refresh current docs
                    current_docs = get_current_client_documents(client_id, user_id)
        else:
            col_info.warning("Could not extract text from this file.")

st.divider()

# ── Step 2: Profile questions ─────────────────────────────────
st.subheader("Step 2 — Profile questions")
st.caption("These cover obligations that can't be assessed from documents alone.")

profile_answers = {}
for q_key, q_config in PROFILE_QUESTIONS.items():
    answer = st.radio(
        q_config["question"],
        options=q_config["options"],
        key=f"gap_q_{q_key}",
        horizontal=True,
    )
    profile_answers[q_key] = answer

st.divider()

# ── Step 3: Run assessment ────────────────────────────────────
st.subheader("Step 3 — Run assessment")

n_docs_available = len(current_docs) + len(uploaded_texts)
n_docs_missing = len(doc_types_ordered) - len(set(list(current_docs.keys()) + list(uploaded_texts.keys())))

if n_docs_available == 0:
    st.warning(
        "No documents available. Upload at least one document or generate documents "
        "in the **Documents** page first. Profile questions will still be assessed."
    )

st.caption(
    f"**{n_docs_available}/6** document types available · "
    f"**{n_docs_missing}** will be flagged as missing · "
    f"~30-60 seconds to complete."
)

run_button = st.button(
    "🔍 Run Gap Assessment",
    type="primary",
    use_container_width=True,
    key="btn_run_gap"
)

if run_button:
    with st.spinner("Running gap assessment..."):
        assessment = run_gap_assessment(
            current_docs=current_docs,
            uploaded_docs=uploaded_texts,
            profile_answers=profile_answers,
            client=selected_client or {},
        )

    st.success("✅ Assessment complete!")
    st.divider()

    # Score cards
    st.subheader("Compliance scores")
    c1, c2, c3, c4 = st.columns(4)

    def score_emoji(s):
        if s >= 75: return "🟢"
        if s >= 50: return "🟡"
        return "🔴"

    c1.metric("Overall", f"{assessment['score_overall']}/100")
    c2.metric(f"{score_emoji(assessment['score_gdpr'])} GDPR",
              f"{assessment['score_gdpr']}/100")
    c3.metric(f"{score_emoji(assessment['score_nis2'])} NIS2",
              f"{assessment['score_nis2']}/100")
    c4.metric(f"{score_emoji(assessment['score_eprivacy'])} ePrivacy",
              f"{assessment['score_eprivacy']}/100")

    st.divider()

    # Results by regulation
    results_by_id = {r["id"]: r for r in assessment["results"]}

    for regulation in ["GDPR", "NIS2", "EPRIVACY"]:
        reg_labels = {"GDPR":"GDPR","NIS2":"NIS2 Directive","EPRIVACY":"ePrivacy Directive"}
        reg_obs = [o for o in OBLIGATIONS if o["regulation"] == regulation]
        reg_results = [results_by_id.get(o["id"],{}) for o in reg_obs]

        n_c  = sum(1 for r in reg_results if r.get("status") == "compliant")
        n_p  = sum(1 for r in reg_results if r.get("status") == "partial")
        n_m  = sum(1 for r in reg_results if r.get("status") == "missing")
        n_na = sum(1 for r in reg_results if r.get("status") == "not_applicable")

        with st.expander(
            f"**{reg_labels[regulation]}** — "
            f"✅ {n_c} · ⚠️ {n_p} · ❌ {n_m}"
            + (f" · ➖ {n_na} N/A" if n_na else ""),
            expanded=(n_m + n_p > 0)
        ):
            for priority in ["high","medium","low"]:
                p_obs = [o for o in reg_obs if o["priority"] == priority]
                if not p_obs: continue

                p_labels = {"high":"🔴 High Priority",
                            "medium":"🟡 Medium Priority",
                            "low":"🔵 Low Priority"}
                st.markdown(f"**{p_labels[priority]}**")

                for ob in p_obs:
                    result = results_by_id.get(ob["id"], {})
                    status = result.get("status","missing")
                    if status == "not_applicable": continue

                    icons = {"compliant":"✅","partial":"⚠️","missing":"❌"}
                    icon = icons.get(status,"❌")

                    col_ob, col_st = st.columns([5,1])
                    col_ob.markdown(f"{icon} **{ob['title']}** `{ob['article']}`")
                    col_st.caption(status.capitalize())

                    if status in ("partial","missing"):
                        st.caption(f"↳ {result.get('explanation','')}")
                        if result.get("recommendation"):
                            st.caption(f"→ _{result['recommendation']}_")
                        if ob.get("doc_type"):
                            doc_label = DOCUMENT_TYPES.get(ob["doc_type"],ob["doc_type"])
                            st.page_link(
                                "pages/documents.py",
                                label=f"📄 Generate compliant {doc_label}",
                            )

    st.divider()

    # PDF report
    st.subheader("Download report")
    with st.spinner("Generating PDF report..."):
        doc_versions = {k: v for k, v in current_docs.items()}
        doc_versions.update({k: {"source":"client_upload","version":"new"}
                              for k in uploaded_texts})
        pdf_bytes = generate_gap_report_pdf(
            assessment=assessment,
            client=selected_client or {},
            profile_answers=profile_answers,
            doc_versions=doc_versions,
        )

    with st.spinner("Saving assessment..."):
        save_gap_assessment(
            user_id=user_id,
            client_id=client_id,
            assessment=assessment,
            profile_answers=profile_answers,
            pdf_bytes=pdf_bytes,
        )

    company = (selected_client or {}).get("company_name","client")
    st.download_button(
        label="📥 Download Gap Assessment Report (PDF)",
        data=pdf_bytes,
        file_name=f"COMPLAI_gap_{company.replace(' ','_')}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )

# ── Assessment history ────────────────────────────────────────
st.divider()
st.subheader("📋 Assessment history")

history = load_gap_assessment_history(user_id, client_id)

if history:
    from zoneinfo import ZoneInfo
    from datetime import datetime as _dt

    h0, h1, h2, h3, h4, h5 = st.columns([2,1,1,1,1,1])
    h0.caption("**Date**")
    h1.caption("**Overall**")
    h2.caption("**GDPR**")
    h3.caption("**NIS2**")
    h4.caption("**ePrivacy**")
    h5.caption("**Report**")

    for rec in history:
        try:
            raw = rec.get("created_at","")
            dt = _dt.fromisoformat(raw.replace("Z","+00:00")) \
                    .astimezone(ZoneInfo("Europe/Brussels")) \
                    .strftime("%Y-%m-%d %H:%M")
        except Exception:
            dt = raw[:16]

        c0,c1,c2,c3,c4,c5 = st.columns([2,1,1,1,1,1])
        c0.caption(dt)
        c1.caption(f"{rec.get('score_overall','—')}/100")
        c2.caption(f"{rec.get('score_gdpr','—')}/100")
        c3.caption(f"{rec.get('score_nis2','—')}/100")
        c4.caption(f"{rec.get('score_eprivacy','—')}/100")

        if rec.get("file_path_pdf"):
            url = get_signed_url("compliance-files", rec["file_path_pdf"], expires_in=300)
            if url:
                c5.link_button("PDF", url, use_container_width=True)
            else:
                c5.caption("—")
        else:
            c5.caption("—")
        st.divider()
else:
    st.caption("No assessments run yet.")
