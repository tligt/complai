import streamlit as st
from auth import init_auth, is_logged_in, get_user_id

st.set_page_config(
    page_title="RECOSA",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="auto",
)

# ── RECOSA Brand CSS ──────────────────────────────────────────
st.markdown("""
<style>
/* Brand tokens */
:root {
    --blue:      #003366;
    --teal:      #14C7D5;
    --teal-dark: #0F9FB5;
    --white:     #FFFFFF;
    --grey-bg:   #F4F7FA;
    --grey-border: #E2E8F0;
}

/* Hide Streamlit default chrome */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* Global font */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Sidebar background */
[data-testid="stSidebar"] {
    background: var(--blue) !important;
}

/* All sidebar text */
[data-testid="stSidebar"],
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div {
    color: #CBD5E1 !important;
}

/* Nav item backgrounds — override white */
[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] {
    background: var(--blue) !important;
}
[data-testid="stSidebar"] a {
    background: transparent !important;
    color: #CBD5E1 !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] a:hover {
    background: rgba(255,255,255,0.08) !important;
    color: white !important;
}
[data-testid="stSidebar"] [aria-selected="true"],
[data-testid="stSidebar"] [aria-current="page"] {
    background: rgba(20,199,213,0.15) !important;
    border-left: 3px solid var(--teal) !important;
    color: white !important;
}

/* Section headers in nav */
[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] {
    color: #475569 !important;
    font-size: 0.7rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

/* Sidebar selectbox and inputs */
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    border-color: rgba(255,255,255,0.15) !important;
    color: white !important;
}

/* Primary buttons → teal */
.stButton > button[kind="primary"] {
    background: var(--teal) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    transition: background 0.2s;
}
.stButton > button[kind="primary"]:hover {
    background: var(--teal-dark) !important;
}

/* Content width */
.main .block-container {
    max-width: 1200px !important;
    padding: 2rem 2.5rem !important;
    margin: 0 auto !important;
}

/* Chat input */
[data-testid="stChatInput"] {
    border-radius: 12px !important;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: var(--grey-bg);
    border-radius: 8px;
    padding: 1rem;
    border: 1px solid var(--grey-border);
}
</style>
""", unsafe_allow_html=True)

# ── Auth init ─────────────────────────────────────────────────
init_auth()

# ── Login screen (no sidebar, no nav) ────────────────────────
if not is_logged_in():
    st.markdown("""
    <style>
    .main .block-container {
        max-width: 440px !important;
        padding: 4rem 1.5rem 2rem !important;
        margin: 0 auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Logo + tagline
    st.markdown("""
    <div style="text-align:center;margin-bottom:2rem;">
        <div style="font-size:2.2rem;font-weight:800;color:#003366;letter-spacing:-1px;">🛡️ RECOSA</div>
        <div style="color:#64748B;font-size:0.95rem;margin-top:4px;">EU Regulatory Compliance for SMEs</div>
    </div>
    """, unsafe_allow_html=True)

    from auth import login_ui
    login_ui()
    st.stop()

# ── Authenticated — define navigation ────────────────────────
user_id = get_user_id()

# Constrain content width for authenticated pages
st.markdown("""
<style>
.main .block-container {
    max-width: 1200px !important;
    padding: 2rem 2.5rem !important;
    margin: 0 auto !important;
}
</style>
""", unsafe_allow_html=True)

# Sidebar logo at top
with st.sidebar:
    st.markdown("""
    <div style="padding:1rem 0 1.25rem;border-bottom:1px solid rgba(255,255,255,0.1);margin-bottom:0.75rem;">
        <div style="font-size:1.25rem;font-weight:800;color:white;letter-spacing:-0.3px;">🛡️ RECOSA</div>
        <div style="font-size:0.7rem;color:#64748B;margin-top:2px;text-transform:uppercase;letter-spacing:0.05em;">EU Compliance Co-pilot</div>
    </div>
    """, unsafe_allow_html=True)

# ── Page routing ──────────────────────────────────────────────
chat       = st.Page("pages/chat.py",      title="Chat",           icon="💬", default=True)
dashboard  = st.Page("pages/dashboard.py", title="Dashboard",      icon="📊")
documents  = st.Page("pages/documents.py", title="Documents",      icon="📄")
gap        = st.Page("pages/gap.py",       title="Gap Assessment", icon="🔍")
audit      = st.Page("pages/audit.py",     title="Web Audit",      icon="🌐")
alerts     = st.Page("pages/alerts.py",    title="Alerts",         icon="🔔")

pg = st.navigation({
    "": [chat],
    "Compliance": [dashboard, gap],
    "Tools": [documents, audit],
    "Updates": [alerts],
})

pg.run()
