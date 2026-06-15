import os
import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import load_clients, get_signed_url
from gap_assessment import (
    OBLIGATIONS, PROFILE_QUESTIONS, DOCUMENT_TYPE_LABELS,
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
st.caption("Upload your existing compliance documents and we'll identify what's missing, partial or compliant across GDPR, NIS2 and ePrivacy.")
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

# ── Check if client has generated documents already ──────────
from database import load_document_files
existing_docs = load_document_files(user_id, client_id)

if not existing_docs:
    st.info(
        "💡 **No compliance documents found for this client.** "
        "If you have existing documents, upload them below. "
        "If you're starting from scratch, we recommend generating your key documents first "
        "using the **Documents** page, then returning here for a gap assessment."
    )
else:
    st.success(f"✅ {len(existing_docs)} COMPLAI document(s) found for this client. "
               f"You can also upload additional existing documents below.")

st.divider()

# ── Step 1: Document upload ───────────────────────────────────
st.subheader("Step 1 — Upload existing compliance documents")
st.caption("Upload any existing policies, procedures or compliance documents (PDF, DOCX or TXT). "
           "These are analysed in-session and not stored.")

uploaded_files = st.file_uploader(
    "Upload documents",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    key="gap_uploads",
    help="Privacy policy, DPA, incident response plan, cookie policy, RoPA — any compliance document you already have."
)

# Extract text from uploads
document_texts = {}
if uploaded_files:
    for f in uploaded_files:
        text = extract_text_from_upload(f)
        if text.strip():
            document_texts[f.name] = text
            st.caption(f"✅ {f.name} — {len(text):,} characters extracted")
        else:
            st.warning(f"⚠️ Could not extract text from {f.name}")

if not uploaded_files:
    st.caption("No documents uploaded — assessment will be based on profile questions only.")

st.divider()

# ── Step 2: Profile questions ─────────────────────────────────
st.subheader("Step 2 — Quick profile questions")
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

n_obligations = len(OBLIGATIONS)
n_doc_based = len([o for o in OBLIGATIONS if not o["profile_question"]])
n_profile_based = len([o for o in OBLIGATIONS if o["profile_question"]])

st.caption(
    f"Will assess **{n_obligations} obligations** across GDPR, NIS2 and ePrivacy. "
    f"{n_doc_based} will be analysed against your uploaded documents, "
    f"{n_profile_based} are based on your profile answers above. "
    f"Estimated time: 30-60 seconds."
)

run_button = st.button(
    "🔍 Run Gap Assessment",
    type="primary",
    use_container_width=True,
    key="btn_run_gap"
)

if run_button:
    with st.spinner("Running gap assessment — this takes about 30-60 seconds..."):
        assessment = run_gap_assessment(
            document_texts=document_texts,
            profile_answers=profile_answers,
            client=selected_client or {},
        )

    # ── Results display ───────────────────────────────────────
    st.success("✅ Gap assessment complete!")
    st.divider()

    # Score cards
    st.subheader("Compliance scores")
    c1, c2, c3, c4 = st.columns(4)

    def score_emoji(s):
        if s >= 75: return "🟢"
        if s >= 50: return "🟡"
        return "🔴"

    c1.metric("Overall", f"{assessment['score_overall']}/100",
              delta=None, help="Weighted: GDPR 50%, NIS2 35%, ePrivacy 15%")
    c2.metric(f"{score_emoji(assessment['score_gdpr'])} GDPR",
              f"{assessment['score_gdpr']}/100")
    c3.metric(f"{score_emoji(assessment['score_nis2'])} NIS2",
              f"{assessment['score_nis2']}/100")
    c4.metric(f"{score_emoji(assessment['score_eprivacy'])} ePrivacy",
              f"{assessment['score_eprivacy']}/100")

    st.divider()

    # Results by regulation and priority
    results_by_id = {r["id"]: r for r in assessment["results"]}

    for regulation in ["GDPR", "NIS2", "EPRIVACY"]:
        reg_labels = {
            "GDPR": "GDPR",
            "NIS2": "NIS2 Directive",
            "EPRIVACY": "ePrivacy Directive"
        }
        reg_obs = [o for o in OBLIGATIONS if o["regulation"] == regulation]
        reg_results = [results_by_id.get(o["id"], {}) for o in reg_obs]

        n_compliant = sum(1 for r in reg_results if r.get("status") == "compliant")
        n_partial   = sum(1 for r in reg_results if r.get("status") == "partial")
        n_missing   = sum(1 for r in reg_results if r.get("status") == "missing")
        n_na        = sum(1 for r in reg_results if r.get("status") == "not_applicable")

        with st.expander(
            f"**{reg_labels[regulation]}** — "
            f"✅ {n_compliant} compliant · "
            f"⚠️ {n_partial} partial · "
            f"❌ {n_missing} missing"
            + (f" · ➖ {n_na} N/A" if n_na else ""),
            expanded=(n_missing + n_partial > 0)
        ):
            for priority in ["high", "medium", "low"]:
                priority_obs = [o for o in reg_obs if o["priority"] == priority]
                if not priority_obs:
                    continue

                priority_labels = {
                    "high": "🔴 High Priority",
                    "medium": "🟡 Medium Priority",
                    "low": "🔵 Low Priority"
                }
                st.markdown(f"**{priority_labels[priority]}**")

                for ob in priority_obs:
                    result = results_by_id.get(ob["id"], {})
                    status = result.get("status", "missing")

                    if status == "not_applicable":
                        continue

                    icons = {
                        "compliant": "✅",
                        "partial": "⚠️",
                        "missing": "❌",
                    }
                    icon = icons.get(status, "❌")

                    col_ob, col_status = st.columns([5, 1])
                    col_ob.markdown(f"{icon} **{ob['title']}** `{ob['article']}`")
                    col_status.caption(status.capitalize())

                    if status in ("partial", "missing"):
                        st.caption(f"↳ {result.get('explanation', '')}")
                        if result.get("recommendation"):
                            st.caption(f"→ _{result['recommendation']}_")
                        if ob.get("doc_type"):
                            doc_label = DOCUMENT_TYPE_LABELS.get(ob["doc_type"], ob["doc_type"])
                            st.page_link(
                                "pages/documents.py",
                                label=f"📄 Generate compliant {doc_label}",
                                icon="📄"
                            )

                st.divider()

    # ── Generate report ───────────────────────────────────────
    st.subheader("Gap Assessment Report")
    st.caption("Download your full gap assessment report as a PDF.")

    with st.spinner("Generating PDF report..."):
        pdf_bytes = generate_gap_report_pdf(
            assessment=assessment,
            client=selected_client or {},
            profile_answers=profile_answers,
        )

    # Save to Supabase
    with st.spinner("Saving assessment..."):
        save_gap_assessment(
            user_id=user_id,
            client_id=client_id,
            assessment=assessment,
            profile_answers=profile_answers,
            pdf_bytes=pdf_bytes,
        )

    company = selected_client.get("company_name", "client") if selected_client else "client"
    st.download_button(
        label="📥 Download Gap Assessment Report (PDF)",
        data=pdf_bytes,
        file_name=f"COMPLAI_gap_assessment_{company.replace(' ','_')}.pdf",
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

    h0, h1, h2, h3, h4, h5 = st.columns([2, 1, 1, 1, 1, 1])
    h0.caption("**Date**")
    h1.caption("**Overall**")
    h2.caption("**GDPR**")
    h3.caption("**NIS2**")
    h4.caption("**ePrivacy**")
    h5.caption("**Report**")

    for rec in history:
        try:
            raw = rec.get("created_at", "")
            utc_dt = _dt.fromisoformat(raw.replace("Z", "+00:00"))
            dt = utc_dt.astimezone(ZoneInfo("Europe/Brussels")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            dt = raw[:16].replace("T", " ")

        c0, c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1, 1])
        c0.caption(dt)
        c1.caption(f"{rec.get('score_overall', '—')}/100")
        c2.caption(f"{rec.get('score_gdpr', '—')}/100")
        c3.caption(f"{rec.get('score_nis2', '—')}/100")
        c4.caption(f"{rec.get('score_eprivacy', '—')}/100")

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
