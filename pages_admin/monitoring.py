import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import (
    is_admin, load_regulatory_updates, approve_regulatory_update,
    reject_regulatory_update, create_client_alerts, get_supabase_admin
)

st.set_page_config(
    page_title="COMPLAI Admin — Monitoring",
    page_icon="📡",
    layout="wide"
)

init_auth()

if not is_logged_in():
    login_ui()
    st.stop()

user_id = get_user_id()
if not is_admin(user_id):
    st.error("🚫 Access denied.")
    st.stop()

st.title("📡 Regulatory Monitoring")
st.caption("Review and approve regulatory updates before they reach clients.")

# ── Manual trigger ────────────────────────────────────────────
with st.expander("🔄 Run monitoring manually", expanded=False):
    st.caption(
        "Monitoring runs automatically every day at 8:00 AM Brussels time via GitHub Actions. "
        "Use this to trigger a manual run."
    )
    if st.button("▶️ Run now", type="secondary"):
        with st.spinner("Fetching regulatory sources..."):
            try:
                from monitor import run_monitoring
                result = run_monitoring()
                st.success(
                    f"✅ Done — {result['saved']} new items found, "
                    f"{result['skipped']} duplicates skipped."
                )
                st.rerun()
            except Exception as e:
                st.error(f"Monitor error: {e}")

st.divider()

# ── Tabs: pending / approved / rejected ──────────────────────
tab_pending, tab_approved, tab_rejected = st.tabs([
    "⏳ Pending review",
    "✅ Approved",
    "❌ Rejected",
])

def render_update_card(update: dict, show_actions: bool = True):
    """Render a single regulatory update card."""
    severity_colors = {"urgent": "🔴", "important": "🟡", "info": "🔵"}
    severity_icon = severity_colors.get(update.get("severity", "info"), "🔵")

    col_main, col_meta = st.columns([4, 1])

    with col_main:
        st.markdown(f"**{update['title']}**")
        if update.get("summary"):
            st.caption(update["summary"])
        if update.get("action_description"):
            st.info(f"**Action required:** {update['action_description']}")

    with col_meta:
        st.caption(f"{severity_icon} {update.get('severity','info').capitalize()}")
        st.caption(f"**Source:** {update.get('source','—')}")
        regs = update.get("regulations") or []
        st.caption(f"**Regs:** {', '.join(regs) if regs else '—'}")
        countries = update.get("countries") or []
        st.caption(f"**Countries:** {', '.join(countries) if countries else 'EU'}")
        pub = (update.get("published_at") or update.get("detected_at",""))[:10]
        st.caption(f"**Date:** {pub}")
        if update.get("url"):
            st.link_button("🔗 Source", update["url"], use_container_width=True)

    if show_actions:
        st.markdown("**Review actions:**")
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 2])

        severity = c1.selectbox(
            "Severity",
            options=["info", "important", "urgent"],
            index=["info","important","urgent"].index(update.get("severity","info")),
            key=f"sev_{update['id']}",
            label_visibility="collapsed"
        )

        send_email = c2.checkbox(
            "📧 Email",
            key=f"email_{update['id']}",
            help="Send email to affected clients when approving"
        )

        if c3.button("✅ Approve", key=f"approve_{update['id']}", type="primary"):
            admin_email = st.session_state.user.email
            ok = approve_regulatory_update(
                update["id"], admin_email, severity, send_email
            )
            if ok:
                # Create client alerts
                n = create_client_alerts(update["id"], update)

                # Send emails if requested
                if send_email and n > 0:
                    _send_alert_emails(update, n)

                st.success(f"✅ Approved — {n} client alerts created.")
                st.rerun()

        if c4.button("❌ Reject", key=f"reject_{update['id']}"):
            reject_regulatory_update(update["id"])
            st.info("Rejected.")
            st.rerun()


def _send_alert_emails(update: dict, n_clients: int):
    """Send alert emails to affected clients."""
    try:
        from email_sender import send_regulatory_alert
        send_regulatory_alert(update)
    except Exception as e:
        st.warning(f"Alert emails could not be sent: {e}")


# ── Pending tab ───────────────────────────────────────────────
with tab_pending:
    pending = load_regulatory_updates(status="pending")
    if pending:
        st.caption(f"**{len(pending)} update(s) awaiting review**")
        for update in pending:
            with st.container(border=True):
                render_update_card(update, show_actions=True)
            st.divider()
    else:
        st.success("✅ No updates pending review.")
        st.caption("Run monitoring manually above or wait for the daily cron job.")

# ── Approved tab ──────────────────────────────────────────────
with tab_approved:
    approved = load_regulatory_updates(status="approved")
    if approved:
        st.caption(f"**{len(approved)} approved update(s)**")
        for update in approved:
            with st.container(border=True):
                col1, col2 = st.columns([5, 1])
                col1.markdown(f"**{update['title']}**")
                col1.caption(update.get("summary",""))
                col2.caption(f"By: {update.get('approved_by','—')[:30]}")
                col2.caption((update.get("approved_at") or "")[:10])
                if update.get("url"):
                    col2.link_button("🔗 Source", update["url"], use_container_width=True)
    else:
        st.caption("No approved updates yet.")

# ── Rejected tab ──────────────────────────────────────────────
with tab_rejected:
    rejected = load_regulatory_updates(status="rejected")
    if rejected:
        st.caption(f"**{len(rejected)} rejected update(s)**")
        for update in rejected:
            with st.container(border=True):
                st.markdown(f"~~{update['title']}~~")
                st.caption(f"Source: {update.get('source','—')} · {(update.get('detected_at',''))[:10]}")
    else:
        st.caption("No rejected updates.")
