import streamlit as st
from auth import get_user_id
from database import (
    load_regulatory_updates,
    approve_regulatory_update,
    reject_regulatory_update,
    create_client_alerts,
    ingest_alert_to_qdrant,
    mark_alert_ingested,
    get_supabase_admin,
)
from email_sender import send_regulatory_alert

st.title("📡 Regulatory Monitoring")
st.caption("Review incoming regulatory updates from monitored sources.")

REGULATIONS = ["", "GDPR", "NIS2", "EU_AI_ACT", "general"]
COUNTRIES   = ["EU", "be", "fr", "general"]

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
            uid = update["id"]
            with st.expander(
                f"**{update.get('title', 'Untitled')}** — {update.get('source', '')} "
                f"· {update.get('detected_at', '')[:10]}",
                expanded=False,
            ):
                # Summary spans full width
                st.markdown("**Summary:**")
                st.info(update.get("summary", "No summary available."))
                if update.get("url"):
                    st.markdown(f"**Source URL:** [{update['url']}]({update['url']})")

                st.divider()

                # Editable metadata + actions side by side
                col_edit, col_actions = st.columns([2, 1])

                with col_edit:
                    st.markdown("**Edit before approving**")

                    reg_val = update.get("regulation") or ""
                    reg_idx = REGULATIONS.index(reg_val) if reg_val in REGULATIONS else 0
                    regulation = st.selectbox(
                        "Regulation",
                        REGULATIONS,
                        index=reg_idx,
                        key=f"reg_{uid}",
                    )

                    country_val = update.get("country") or "EU"
                    country_idx = COUNTRIES.index(country_val) if country_val in COUNTRIES else 0
                    country = st.selectbox(
                        "Country",
                        COUNTRIES,
                        index=country_idx,
                        key=f"country_{uid}",
                    )

                    severity = st.selectbox(
                        "Severity",
                        ["info", "warning", "critical"],
                        key=f"sev_{uid}",
                    )

                with col_actions:
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    send_email = st.checkbox("Send email to clients", key=f"email_{uid}")

                    if st.button("✅ Approve", key=f"approve_{uid}", type="primary"):
                        with st.spinner("Approving and ingesting into knowledge base…"):

                            # Patch update dict with admin-edited values
                            update["regulation"] = regulation
                            update["country"]    = country

                            # Save edits to Supabase before approving
                            try:
                                get_supabase_admin().table("regulatory_updates") \
                                    .update({"regulation": regulation, "country": country}) \
                                    .eq("id", uid) \
                                    .execute()
                            except Exception as e:
                                st.warning(f"Could not save edits: {e}")

                            # 1. Approve
                            approved = approve_regulatory_update(
                                update_id=uid,
                                approved_by=get_user_id(),
                                severity=severity,
                                send_email=send_email,
                            )

                            if approved:
                                # 2. Client alerts
                                n_alerts = create_client_alerts(uid, update)

                                # 3. Ingest into Qdrant
                                ingest_result = ingest_alert_to_qdrant(update)
                                if ingest_result["success"]:
                                    mark_alert_ingested(uid, ingest_result["chunks_ingested"])

                                # 4. Email
                                if send_email:
                                    try:
                                        send_regulatory_alert(update)
                                    except Exception as e:
                                        st.warning(f"Email send failed: {e}")

                                # 5. Feedback
                                st.success(f"✅ Approved — {n_alerts} client alert(s) created")

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
                                        "Alert approved and notifications sent. "
                                        "Retry from the Approved tab."
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
                f"🧠 {update.get('kb_chunks_count', 0)} chunks · "
                f"{str(update.get('kb_ingested_at', ''))[:10]}"
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
                if update.get("url"):
                    st.markdown(f"**Source URL:** [{update['url']}]({update['url']})")
                st.markdown("**Summary:**")
                st.info(update.get("summary", "No summary available."))

                if not update.get("kb_ingested"):
                    st.warning("This update was not ingested into the knowledge base.")
                    if st.button("🔄 Retry KB ingestion", key=f"retry_{update['id']}"):
                        with st.spinner("Ingesting…"):
                            ingest_result = ingest_alert_to_qdrant(update)
                            if ingest_result["success"]:
                                mark_alert_ingested(update["id"], ingest_result["chunks_ingested"])
                                st.success(f"🧠 {ingest_result['chunks_ingested']} chunk(s) ingested")
                                st.rerun()
                            else:
                                st.error(f"Failed: {ingest_result.get('error', 'unknown')}")

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

                if st.button("↩️ Move to Pending", key=f"unpend_{update['id']}"):
                    get_supabase_admin().table("regulatory_updates") \
                        .update({"status": "pending"}) \
                        .eq("id", update["id"]) \
                        .execute()
                    st.rerun()
