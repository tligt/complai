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

# ── Navigation — explicitly control sidebar pages ─────────────
home = st.Page("pages_admin/home.py", title="Admin Home", icon="⚙️", default=True)
monitoring = st.Page("pages_admin/monitoring.py", title="Regulatory Monitoring", icon="📡")

pg = st.navigation({"Admin": [home, monitoring]})
pg.run()
