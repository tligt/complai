import streamlit as st
from auth import init_auth, is_logged_in, get_user_id

st.set_page_config(
    page_title="RECOSA",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────
st.markdown("""
<style>
/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* Global font */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ── Sidebar ── */
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
    padding: 0.4rem 0.75rem !important;
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
/* Nav section labels */
[data-testid="stSidebarNavSeparator"] p {
    color: #475569 !important;
    font-size: 0.68rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}
/* Sidebar inputs */
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    border-color: rgba(255,255,255,0.15) !important;
    color: white !important;
}
[data-testid="stSidebar"] .stSelectbox svg {
    fill: #94A3B8 !important;
}

/* ── Buttons ── */
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

/* ── Content width ── */
.main .block-container {
    max-width: 1200px !important;
    padding: 2rem 3rem !important;
    margin: 0 auto !important;
}

/* ── Login specific ── */
.login-container .main .block-container {
    max-width: 420px !important;
    padding: 3rem 1.5rem !important;
    margin: 5vh auto 0 !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: #F4F7FA;
    border-radius: 8px;
    padding: 1rem;
    border: 1px solid #E2E8F0;
}
</style>
""", unsafe_allow_html=True)

# ── Auth ──────────────────────────────────────────────────────
init_auth()

# ── Login screen ──────────────────────────────────────────────
if not is_logged_in():
    # Narrow centered layout for login — use width:0 not display:none
    # display:none causes Streamlit to remember sidebar as collapsed in localStorage
    st.markdown("""
    <style>
    [data-testid="stSidebar"] { width: 0 !important; min-width: 0 !important; overflow: hidden !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    .main .block-container {
        max-width: 420px !important;
        padding: 3rem 1.5rem 2rem !important;
        margin: 8vh auto 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-bottom:2rem;">
        <div style="font-size:2rem;font-weight:800;color:#003366;letter-spacing:-1px;">🛡️ RECOSA</div>
        <div style="color:#64748B;font-size:0.9rem;margin-top:6px;">EU Regulatory Compliance for SMEs</div>
    </div>
    """, unsafe_allow_html=True)

    from auth import login_ui
    login_ui()
    st.stop()

# ── Authenticated ─────────────────────────────────────────────
user_id = get_user_id()

# Sidebar: logo above nav (injected via CSS top position)
st.markdown("""
<style>
/* Push nav items down to make room for logo */
[data-testid="stSidebarNav"] {
    margin-top: 70px !important;
}
/* Logo overlay at top of sidebar */
[data-testid="stSidebar"]::before {
    content: "🛡️  RECOSA";
    display: block;
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    padding: 1rem 1rem 0.75rem;
    font-size: 1.1rem;
    font-weight: 800;
    color: white !important;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: #003366;
    z-index: 999;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    from auth import logout
    if st.button("Log out", use_container_width=True, key="btn_logout"):
        logout()

# ── Navigation ────────────────────────────────────────────────
chat      = st.Page("pages/chat.py",      title="Chat",           icon="💬", default=True)
dashboard = st.Page("pages/dashboard.py", title="Dashboard",      icon="📊")
gap       = st.Page("pages/gap.py",       title="Gap Assessment", icon="🔍")
documents = st.Page("pages/documents.py", title="Documents",      icon="📄")
audit     = st.Page("pages/audit.py",     title="Web Audit",      icon="🌐")
alerts    = st.Page("pages/alerts.py",    title="Alerts",         icon="🔔")

pg = st.navigation({
    "":           [chat],
    "Compliance": [dashboard, gap],
    "Tools":      [documents, audit],
    "Updates":    [alerts],
})
pg.run()
