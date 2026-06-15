import os
import re
from datetime import datetime
import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import (
    load_clients, get_signed_url, upload_file,
    get_current_client_documents, register_client_document,
)
from gap_assessment import (
    OBLIGATIONS, PROFILE_QUESTIONS, DOCUMENT_TYPES, DOC_OBLIGATIONS,
    extract_text_from_upload, run_document_review, run_gap_assessment,
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

# ── Two tabs ──────────────────────────────────────────────────
tab1, tab2 = st.tabs([
    "📄 Review a document",
    "🏢 Full compliance check"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1 — Document Review
# ═══════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Review a document")
    st.caption(
        "Upload a specific document and get a score based only on the obligations "
        "that document is supposed to cover. "
        "A good privacy policy should score 75-90/100 on privacy obligations."
    )

    col1, col2 = st.columns(2)
    doc_type_review = col1.selectbox(
        "Document type",
        options=list(DOCUMENT_TYPES.keys()),
        format_func=lambda x: DOCUMENT_TYPES[x],
        key="review_doc_type"
    )

    # Show how many obligations will be checked
    n_obs = len(DOC_OBLIGATIONS.get(doc_type_review, []))
    col2.metric("Obligations checked", n_obs)

    uploaded_review = st.file_uploader(
        f"Upload your {DOCUMENT_TYPES[doc_type_review]}",
        type=["pdf","docx","txt"],
        key="review_upload"
    )

    # Profile questions relevant to this doc type
    ob_ids = DOC_OBLIGATIONS.get(doc_type_review, [])
    relevant_profile_qs = list({
        o["profile_question"]
        for o in OBLIGATIONS
        if o["id"] in ob_ids and o["profile_question"]
    })

    profile_answers_review = {}
    if relevant_profile_qs:
        st.divider()
        st.markdown("**A few quick questions:**")
        for q_key in relevant_profile_qs:
            q_config = PROFILE_QUESTIONS[q_key]
            answer = st.radio(
                q_config["question"],
                options=q_config["options"],
                key=f"rev_q_{q_key}",
                horizontal=True,
            )
            profile_answers_review[q_key] = answer

    run_review = st.button(
        f"🔍 Review {DOCUMENT_TYPES[doc_type_review]}",
        type="primary",
        use_container_width=True,
        key="btn_review",
        disabled=not uploaded_review
    )

    if run_review and uploaded_review:
        doc_text = extract_text_from_upload(uploaded_review)
        if not doc_text.strip():
            st.error("Could not extract text from this file.")
        else:
            with st.spinner(f"Reviewing {DOCUMENT_TYPES[doc_type_review]}..."):
                review = run_document_review(
                    doc_type=doc_type_review,
                    document_text=doc_text,
                    profile_answers=profile_answers_review,
                    client=selected_client or {},
                )

            # Score display
            score = review["score"]
            if score >= 75:
                score_label = "🟢 Good"
                score_msg = "This document covers its key obligations well."
            elif score >= 50:
                score_label = "🟡 Needs improvement"
                score_msg = "This document covers some obligations but has gaps."
            else:
                score_label = "🔴 Significant gaps"
                score_msg = "This document needs substantial improvement."

            st.divider()
            col_score, col_label = st.columns([1, 3])
            col_score.metric(DOCUMENT_TYPES[doc_type_review], f"{score}/100")
            col_label.markdown(f"**{score_label}**")
            col_label.caption(score_msg)

            st.divider()

            # Results
            results_by_id = {r["id"]: r for r in review["results"]}
            obligations = review.get("obligations", [])

            for priority in ["high","medium","low"]:
                p_obs = [o for o in obligations if o["priority"] == priority]
                if not p_obs: continue
                p_labels = {"high":"🔴 High Priority",
                            "medium":"🟡 Medium Priority",
                            "low":"🔵 Low Priority"}
                st.markdown(f"**{p_labels[priority]}**")
                for ob in p_obs:
                    result = results_by_id.get(ob["id"], {})
                    status = result.get("status","missing")
                    icons = {"compliant":"✅","partial":"⚠️","missing":"❌"}
                    icon = icons.get(status,"❌")
                    col_ob, col_st = st.columns([5,1])
                    col_ob.markdown(f"{icon} **{ob['title']}** `{ob['article']}`")
                    col_st.caption(status.capitalize())
                    if status in ("partial","missing"):
                        st.caption(f"↳ {result.get('explanation','')}")
                        if result.get("recommendation"):
                            st.caption(f"→ _{result['recommendation']}_")

            # Download mini-report
            st.divider()
            from io import BytesIO
            import io as _io
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.colors import HexColor
            from reportlab.lib.units import cm

            def make_review_pdf():
                buf = _io.BytesIO()
                doc_r = SimpleDocTemplate(buf, pagesize=A4,
                    leftMargin=2.5*cm, rightMargin=2*cm,
                    topMargin=2.5*cm, bottomMargin=2*cm)
                styles = getSampleStyleSheet()
                NAVY = HexColor("#1B2A4A")
                PURPLE = HexColor("#4A3B8C")
                TEAL = HexColor("#0F6E56")
                MGRAY = HexColor("#888888")
                def S(name, **kw): return ParagraphStyle(name, parent=styles["Normal"], **kw)
                story = []
                story.append(Paragraph(f"Document Review — {review['doc_label']}", S("t", fontSize=18, textColor=NAVY, leading=24, spaceAfter=4)))
                story.append(HRFlowable(width="100%", thickness=2, color=NAVY))
                story.append(Spacer(1, 4))
                company = (selected_client or {}).get("company_name", "")
                story.append(Paragraph(company, S("s", fontSize=12, textColor=PURPLE, leading=16, spaceAfter=4)))
                from datetime import date
                story.append(Paragraph(f"Generated by COMPLAI · {date.today().strftime('%d %B %Y')}", S("d", fontSize=9, textColor=MGRAY, leading=12, spaceAfter=16)))
                story.append(Paragraph(f"Score: {review['score']}/100 — {score_label}", S("sc", fontSize=14, textColor=NAVY, leading=18, spaceAfter=4, fontName="Helvetica-Bold")))
                story.append(Paragraph(score_msg, S("sm", fontSize=9, textColor=MGRAY, leading=12, spaceAfter=12)))
                story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#D3D1C7")))
                for priority in ["high","medium","low"]:
                    p_obs = [o for o in review.get("obligations",[]) if o["priority"] == priority]
                    if not p_obs: continue
                    p_labels = {"high":"High Priority","medium":"Medium Priority","low":"Low Priority"}
                    story.append(Paragraph(p_labels[priority], S("h", fontSize=11, textColor=PURPLE, leading=14, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")))
                    for ob in p_obs:
                        result = results_by_id.get(ob["id"], {})
                        status = result.get("status","missing")
                        icon = "✅" if status=="compliant" else ("⚠️" if status=="partial" else "❌")
                        story.append(Paragraph(f"{icon} {ob['title']} ({ob['article']})", S("ob", fontSize=9, textColor=HexColor("#000000"), leading=13, spaceAfter=2)))
                        if status in ("partial","missing"):
                            story.append(Paragraph(result.get("explanation",""), S("ex", fontSize=8, textColor=MGRAY, leading=11, spaceAfter=2, leftIndent=12)))
                            if result.get("recommendation"):
                                story.append(Paragraph(f"→ {result['recommendation']}", S("r", fontSize=8, textColor=TEAL, leading=11, spaceAfter=4, leftIndent=12)))
                story.append(Spacer(1, 20))
                story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#D3D1C7")))
                story.append(Paragraph("Generated by COMPLAI · complai.be · Review with a qualified legal professional before use.", S("ft", fontSize=7, textColor=MGRAY, leading=10, spaceAfter=0)))
                doc_r.build(story)
                return buf.getvalue()

            review_pdf = make_review_pdf()
            company_name = (selected_client or {}).get("company_name","client")
            st.download_button(
                label=f"📥 Download {review['doc_label']} Review (PDF)",
                data=review_pdf,
                file_name=f"COMPLAI_review_{doc_type_review}_{company_name.replace(' ','_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )

            # Option to save to repository
            st.divider()
            if client_id:
                save_to_repo = st.checkbox(
                    f"Save this document to {chosen}'s repository as current {DOCUMENT_TYPES[doc_type_review]}",
                    key="save_review_doc"
                )
                comment = ""
                if save_to_repo:
                    comment = st.text_input(
                        "Change comment (optional)",
                        placeholder="e.g. Initial upload — external audit pending",
                        key="review_comment"
                    )

                if save_to_repo and st.button("💾 Save to repository", key="btn_save_review"):
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", uploaded_review.name)[:30]
                    path = f"{user_id}/{client_id}/COMPLAI_{doc_type_review}_{ts}_{safe}"
                    stored = upload_file(
                        "compliance-files", path,
                        uploaded_review.getvalue(),
                        "application/octet-stream"
                    )
                    if stored:
                        register_client_document(
                            user_id=user_id,
                            client_id=client_id,
                            document_type=doc_type_review,
                            file_path=path,
                            source="client_upload",
                            change_comment=comment,
                        )
                        st.success("✅ Saved to repository.")

# ═══════════════════════════════════════════════════════════════
# TAB 2 — Full Compliance Check
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Full compliance check")
    st.caption(
        "Assess your overall compliance posture across GDPR, NIS2 and ePrivacy. "
        "Uses documents already in your repository. "
        "Scores reflect the quality of documents provided — "
        "missing documents are shown as gaps separately."
    )

    # Load current documents
    current_docs = get_current_client_documents(client_id, user_id) if client_id else {}

    # Document repository status
    st.markdown("**Your document repository:**")
    doc_types_ordered = [
        "privacy_policy","cookie_policy","dpa",
        "ropa","incident_response","ai_transparency"
    ]

    uploaded_texts = {}
    n_provided = 0

    for doc_type in doc_types_ordered:
        label = DOCUMENT_TYPES[doc_type]
        current = current_docs.get(doc_type)

        col_s, col_i, col_u = st.columns([1,4,2])
        if current:
            n_provided += 1
            col_s.markdown("✅")
            src = "COMPLAI" if current.get("source") == "complai_generated" else "Uploaded"
            ts = current.get("uploaded_at","")[:10]
            col_i.markdown(f"**{label}**")
            col_i.caption(f"v{current.get('version',1)} · {src} · {ts}")
            if current.get("change_comment"):
                col_i.caption(f"_{current['change_comment']}_")
        else:
            col_s.markdown("⬜")
            col_i.markdown(f"**{label}**")
            col_i.caption("Not in repository")

        # Allow uploading new/updated version
        new_file = col_u.file_uploader(
            "Upload" if not current else "Update",
            type=["pdf","docx","txt"],
            key=f"full_upload_{doc_type}",
            label_visibility="collapsed",
        )
        if new_file:
            text = extract_text_from_upload(new_file)
            if text.strip():
                uploaded_texts[doc_type] = text
                if not current:
                    n_provided += 1
                col_i.success(f"✅ {new_file.name} ready")
                # Save to repository
                if client_id:
                    comment = st.text_input(
                        "Change comment",
                        key=f"full_comment_{doc_type}",
                        placeholder="e.g. Updated after audit"
                    )
                    ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe = re.sub(r"[^a-zA-Z0-9_-]","_",new_file.name)[:30]
                    path = f"{user_id}/{client_id}/COMPLAI_{doc_type}_{ts2}_{safe}"
                    stored = upload_file("compliance-files", path,
                                        new_file.getvalue(), "application/octet-stream")
                    if stored:
                        register_client_document(
                            user_id=user_id, client_id=client_id,
                            document_type=doc_type, file_path=path,
                            source="client_upload", change_comment=comment,
                        )
                        current_docs = get_current_client_documents(client_id, user_id)

    st.caption(f"**{n_provided}/6** document types available in repository")
    st.divider()

    # Profile questions
    st.markdown("**Quick profile questions:**")
    st.caption("These cover obligations that can't be assessed from documents alone.")

    profile_answers = {}
    for q_key, q_config in PROFILE_QUESTIONS.items():
        answer = st.radio(
            q_config["question"],
            options=q_config["options"],
            key=f"full_q_{q_key}",
            horizontal=True,
        )
        profile_answers[q_key] = answer

    st.divider()
    st.caption(
        f"Scores reflect quality of the **{n_provided}** document(s) provided. "
        "Missing documents are flagged as gaps but don't lower the quality score. "
        "~30-60 seconds to complete."
    )

    run_full = st.button(
        "🔍 Run Full Compliance Check",
        type="primary",
        use_container_width=True,
        key="btn_run_full"
    )

    if run_full:
        with st.spinner("Running compliance check..."):
            assessment = run_gap_assessment(
                current_docs=current_docs,
                uploaded_docs=uploaded_texts,
                profile_answers=profile_answers,
                client=selected_client or {},
            )

        st.success("✅ Assessment complete!")
        st.divider()

        # Scores
        st.subheader("Compliance scores")
        st.caption("Based on quality of documents provided — not penalised for missing documents.")
        c1,c2,c3,c4 = st.columns(4)

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

        # Missing documents summary
        missing_docs = [DOCUMENT_TYPES[dt] for dt in doc_types_ordered
                        if dt not in current_docs and dt not in uploaded_texts]
        if missing_docs:
            st.warning(
                f"**{len(missing_docs)} document(s) not in repository** — "
                f"these are flagged as gaps below: "
                + ", ".join(missing_docs)
            )

        st.divider()

        # Results by regulation
        results_by_id = {r["id"]: r for r in assessment["results"]}
        for regulation in ["GDPR","NIS2","EPRIVACY"]:
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
                        result = results_by_id.get(ob["id"],{})
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
                            if ob.get("doc_type") and ob.get("doc_type") not in current_docs:
                                doc_label = DOCUMENT_TYPES.get(ob["doc_type"],ob["doc_type"])
                                st.page_link(
                                    "pages/documents.py",
                                    label=f"📄 Generate compliant {doc_label}",
                                )

        st.divider()

        # PDF Report
        st.subheader("Download report")
        with st.spinner("Generating PDF..."):
            doc_versions = {**current_docs,
                            **{k:{"source":"client_upload","version":1}
                               for k in uploaded_texts}}
            pdf_bytes = generate_gap_report_pdf(
                assessment=assessment,
                client=selected_client or {},
                profile_answers=profile_answers,
                doc_versions=doc_versions,
            )

        with st.spinner("Saving..."):
            save_gap_assessment(
                user_id=user_id, client_id=client_id,
                assessment=assessment, profile_answers=profile_answers,
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

    h0,h1,h2,h3,h4,h5 = st.columns([2,1,1,1,1,1])
    h0.caption("**Date**"); h1.caption("**Overall**")
    h2.caption("**GDPR**"); h3.caption("**NIS2**")
    h4.caption("**ePrivacy**"); h5.caption("**Report**")

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
