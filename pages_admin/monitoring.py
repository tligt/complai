import streamlit as st
from database import (
    load_regulatory_updates,
    approve_regulatory_update,
    reject_regulatory_update,
    create_client_alerts,
    ingest_alert_to_qdrant,
    mark_alert_ingested,
)
from email_sender import send_regulatory_alert_emails

st.set_page_config(page_title="Regulatory Monitoring — COMPLAI Admin", layout="wide")

# ── Auth guard ────────────────────────────────────────────────────────────────
if "user" not in st.session_state or not st.session_state.get("is_admin"):
    st.error("Admin access required.")
    st.stop()

st.title("📡 Regulatory Monitoring")
st.caption("Review incoming regulatory updates from monitored sources.")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_pending, tab_approved, tab_rejected = st.tabs([
    "🟡 Pending",
    "✅ Approved",
    "❌ Rejected",
])

# ── PENDING ───────────────────────────────────────────────────────────────────
with tab_pending:
    pending = load_regulatory_updates(status="pending")

    if not pending:
        st.info("No pending updates. Run the monitoring job or wait for the daily cron.")
    else:
        st.markdown(f"**{len(pending)} update(s) awaiting review**")

        for update in pending:
            with st.expander(
                f"**{update.get('title', 'Untitled')}** — {update.get('source', '')} "
                f"· {update.get('detected_at', '')[:10]}",
                expanded=False,
            ):
                col_meta, col_actions = st.columns([3, 1])

                with col_meta:
                    st.markdown(f"**Regulation:** {update.get('regulation', '—')}")
                    st.markdown(f"**Country:** {update.get('country', '—')}")
                    if update.get("url"):
                        st.markdown(f"**Source URL:** [{update['url']}]({update['url']})")
                    st.markdown("**Summary:**")
                    st.info(update.get("summary", "No summary available."))

                with col_actions:
                    uid = update["id"]
                    admin_id = st.session_state["user"]["id"]

                    severity = st.selectbox(
                        "Severity",
                        ["info", "warning", "critical"],
                        key=f"sev_{uid}",
                    )
                    send_email = st.checkbox("Send email to clients", key=f"email_{uid}")

                    if st.button("✅ Approve", key=f"approve_{uid}", type="primary"):
                        with st.spinner("Approving and ingesting into knowledge base…"):

                            # 1. Update status in Supabase
                            approved = approve_regulatory_update(
                                update_id=uid,
                                approved_by=admin_id,
                                severity=severity,
                                send_email=send_email,
                            )

                            if approved:
                                # 2. Create client alerts
                                n_alerts = create_client_alerts(uid, update)

                                # 3. Ingest into Qdrant (Sprint 12 core)
                                ingest_result = ingest_alert_to_qdrant(update)

                                if ingest_result["success"]:
                                    mark_alert_ingested(uid, ingest_result["chunks_ingested"])

                                # 4. Send email if requested
                                if send_email:
                                    try:
                                        send_regulatory_alert_emails(uid, update)
                                    except Exception as e:
                                        st.warning(f"Email send failed: {e}")

                                # 5. Show result summary
                                st.success(
                                    f"✅ Approved — {n_alerts} client alert(s) created"
                                )

                                # KB ingestion feedback
                                if ingest_result["success"]:
                                    full_text_msg = (
                                        "full article + summary"
                                        if ingest_result["full_text_ingested"]
                                        else "summary only (full article unavailable)"
                                    )
                                    st.success(
                                        f"🧠 Ingested into knowledge base — "
                                        f"{ingest_result['chunks_ingested']} chunk(s) "
                                        f"({full_text_msg})"
                                    )
                                else:
                                    st.warning(
                                        f"⚠️ KB ingestion failed: {ingest_result.get('error', 'unknown error')}. "
                                        "The alert was approved and client notifications sent, "
                                        "but the knowledge base was not updated. "
                                        "You can retry by re-approving from the Approved tab."
                                    )

                                st.rerun()
                            else:
                                st.error("Approval failed. Please try again.")

                    if st.button("❌ Reject", key=f"reject_{uid}"):
                        reject_regulatory_update(uid)
                        st.rerun()

# ── APPROVED ──────────────────────────────────────────────────────────────────
with tab_approved:
    approved_list = load_regulatory_updates(status="approved")

    if not approved_list:
        st.info("No approved updates yet.")
    else:
        st.markdown(f"**{len(approved_list)} approved update(s)**")

        for update in approved_list:
            kb_status = (
                f"🧠 {update.get('kb_chunks_count', 0)} chunks in KB "
                f"· {str(update.get('kb_ingested_at', ''))[:10]}"
                if update.get("kb_ingested")
                else "⚠️ Not in KB"
            )

            with st.expander(
                f"**{update.get('title', 'Untitled')}** — {update.get('source', '')} "
                f"· {update.get('detected_at', '')[:10]} · {kb_status}",
                expanded=False,
            ):
                st.markdown(f"**Regulation:** {update.get('regulation', '—')}")
                st.markdown(f"**Country:** {update.get('country', '—')}")
                st.markdown(f"**Severity:** {update.get('severity', '—')}")
                st.markdown(f"**Approved by:** {update.get('approved_by', '—')}")
                if update.get("url"):
                    st.markdown(f"**Source URL:** [{update['url']}]({update['url']})")
                st.markdown("**Summary:**")
                st.info(update.get("summary", "No summary available."))

                # Retry ingestion if it failed
                if not update.get("kb_ingested"):
                    st.warning("This update was not ingested into the knowledge base.")
                    if st.button("🔄 Retry KB ingestion", key=f"retry_{update['id']}"):
                        with st.spinner("Ingesting into knowledge base…"):
                            ingest_result = ingest_alert_to_qdrant(update)
                            if ingest_result["success"]:
                                mark_alert_ingested(update["id"], ingest_result["chunks_ingested"])
                                st.success(
                                    f"🧠 Ingested — {ingest_result['chunks_ingested']} chunk(s)"
                                )
                                st.rerun()
                            else:
                                st.error(
                                    f"Ingestion failed: {ingest_result.get('error', 'unknown error')}"
                                )

# ── REJECTED ──────────────────────────────────────────────────────────────────
with tab_rejected:
    rejected_list = load_regulatory_updates(status="rejected")

    if not rejected_list:
        st.info("No rejected updates.")
    else:
        st.markdown(f"**{len(rejected_list)} rejected update(s)**")

        for update in rejected_list:
            with st.expander(
                f"**{update.get('title', 'Untitled')}** — {update.get('source', '')} "
                f"· {update.get('detected_at', '')[:10]}",
                expanded=False,
            ):
                st.markdown(f"**Regulation:** {update.get('regulation', '—')}")
                st.markdown("**Summary:**")
                st.info(update.get("summary", "No summary available."))

                # Allow re-approval from rejected state
                if st.button("↩️ Move to Pending", key=f"unpend_{update['id']}"):
                    from database import get_supabase_admin
                    get_supabase_admin().table("regulatory_updates") \
                        .update({"status": "pending"}) \
                        .eq("id", update["id"]) \
                        .execute()
                    st.rerun()
