import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import is_admin

st.set_page_config(
    page_title="COMPLAI Admin",
    page_icon="⚙️",
    layout="wide"
)

init_auth()

# ── Auth gate ─────────────────────────────────────────────────
if not is_logged_in():
    st.title("⚙️ COMPLAI Admin")
    login_ui()
    st.stop()

user_id = get_user_id()

if not is_admin(user_id):
    st.error("🚫 Access denied — admin privileges required.")
    st.caption("If you believe this is an error, contact your system administrator.")
    st.stop()

# ── Admin home ────────────────────────────────────────────────
st.title("⚙️ COMPLAI Admin")
st.caption(f"Logged in as admin · {st.session_state.user.email}")
st.divider()

# Quick stats
from database import (
    get_supabase_admin, load_regulatory_updates, count_unread_alerts
)

try:
    admin = get_supabase_admin()

    col1, col2, col3, col4 = st.columns(4)

    # Total clients
    clients_res = admin.table("clients").select("id", count="exact").execute()
    col1.metric("Total clients", clients_res.count or 0)

    # Total users
    profiles_res = admin.table("profiles").select("id", count="exact").execute()
    col2.metric("Registered users", profiles_res.count or 0)

    # Pending regulatory updates
    pending = load_regulatory_updates(status="pending")
    col3.metric("Pending updates", len(pending),
                delta="needs review" if pending else None,
                delta_color="inverse" if pending else "off")

    # Documents generated
    docs_res = admin.table("documents").select("id", count="exact").execute()
    col4.metric("Documents generated", docs_res.count or 0)

except Exception as e:
    st.warning(f"Could not load stats: {e}")

st.divider()

# Navigation
st.subheader("Admin sections")
col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("**📡 Regulatory Monitoring**")
    st.caption("Review and approve regulatory updates")
    st.page_link("pages/admin_monitoring.py", label="Open →")

with col_b:
    st.markdown("**📚 Knowledge Base**")
    st.caption("Manage the regulatory knowledge base")
    st.page_link("pages/audit.py", label="Open →")

with col_c:
    st.markdown("**👥 Client Management**")
    st.caption("View all clients and usage")
    st.page_link("pages/admin_clients.py", label="Open →")
