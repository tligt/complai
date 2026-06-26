import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import is_admin

st.set_page_config(
    page_title="RECOSA Admin",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── RECOSA Brand CSS (same as client app) ─────────────────────
st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #003366 !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] small {
    color: #CBD5E1 !important;
}
[data-testid="stSidebar"] a {
    color: #CBD5E1 !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] a:hover {
    background: rgba(255,255,255,0.08) !important;
    color: white !important;
}
[data-testid="stSidebar"] [aria-current="page"],
[data-testid="stSidebar"] [aria-selected="true"] {
    background: rgba(20,199,213,0.18) !important;
    border-left: 3px solid #14C7D5 !important;
    color: white !important;
}
[data-testid="stSidebarNavSeparator"] p {
    color: #475569 !important;
    font-size: 0.68rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

/* Sidebar logo via pseudo-element */
[data-testid="stSidebarNav"] { margin-top: 70px !important; }
[data-testid="stSidebar"]::before {
    content: "⚙️  RECOSA Admin";
    display: block;
    position: absolute;
    top: 0; left: 0; right: 0;
    padding: 1rem 1rem 0.75rem;
    font-size: 1.1rem;
    font-weight: 800;
    color: white !important;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: #003366;
    z-index: 999;
}

/* Primary buttons */
.stButton > button[kind="primary"] {
    background: #14C7D5 !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    transition: background 0.2s;
}
.stButton > button[kind="primary"]:hover {
    background: #0F9FB5 !important;
}

/* Content width */
.main .block-container {
    max-width: 1200px !important;
    padding: 2rem 3rem !important;
    margin: 0 auto !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background: #F4F7FA;
    border-radius: 8px;
    padding: 1rem;
    border: 1px solid #E2E8F0;
}
</style>
""", unsafe_allow_html=True)

init_auth()

if not is_logged_in():
    st.title("⚙️ RECOSA Admin")
    login_ui()
    st.stop()

user_id = get_user_id()
if not is_admin(user_id):
    st.error("🚫 Access denied — admin privileges required.")
    st.caption("If you believe this is an error, contact your system administrator.")
    st.stop()

home       = st.Page("pages_admin/home.py",       title="Admin Home",    icon="⚙️",  default=True)
dashboard  = st.Page("pages_admin/dashboard.py",  title="Dashboard",     icon="📊")
monitoring = st.Page("pages_admin/monitoring.py", title="Monitoring",    icon="📡")
kb         = st.Page("pages_admin/kb.py",         title="Knowledge Base",icon="📚")

pg = st.navigation({
    "Admin": [home, dashboard],
    "Content": [monitoring, kb],
})
pg.run()
