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
    --text-primary: #1A202C;
    --text-secondary: #64748B;
    --sidebar-width: 240px;
}

/* Hide Streamlit default chrome */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* Global font */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background: var(--blue) !important;
    min-width: var(--sidebar-width) !important;
    max-width: var(--sidebar-width) !important;
}
[data-testid="stSidebar"] * {
    color: #CBD5E1 !important;
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    color: white !important;
}
/* Active nav item */
[data-testid="stSidebar"] [aria-selected="true"] {
    background: rgba(20, 199, 213, 0.15) !important;
    border-left: 3px solid var(--teal) !important;
    color: white !important;
}
/* Nav items hover */
[data-testid="stSidebar"] a:hover {
    background: rgba(255,255,255,0.08) !important;
    color: white !important;
}

/* Main content area */
.main .block-container {
    padding: 2rem 2.5rem;
    max-width: 1100px;
}

/* Primary buttons → teal */
.stButton > button[kind="primary"] {
    background: var(--teal) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    padding: 0.5rem 1.5rem !important;
    transition: background 0.2s;
}
.stButton > button[kind="primary"]:hover {
    background: var(--teal-dark) !important;
}

/* Secondary buttons */
.stButton > button[kind="secondary"] {
    border: 1.5px solid var(--grey-border) !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}

/* Chat input */
[data-testid="stChatInput"] {
    border-radius: 12px !important;
    border: 1.5px solid var(--grey-border) !important;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: var(--grey-bg);
    border-radius: 8px;
    padding: 1rem;
    border: 1px solid var(--grey-border);
}

/* Expanders */
[data-testid="stExpander"] {
    border: 1px solid var(--grey-border) !important;
    border-radius: 8px !important;
}

/* Login page centering */
.login-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 85vh;
}
.login-card {
    background: white;
    border: 1px solid var(--grey-border);
    border-radius: 16px;
    padding: 3rem 2.5rem;
    max-width: 420px;
    width: 100%;
    box-shadow: 0 4px 24px rgba(0,51,102,0.08);
}
.login-logo {
    font-size: 2rem;
    font-weight: 800;
    color: var(--blue);
    letter-spacing: -0.5px;
    margin-bottom: 0.25rem;
}
.login-tagline {
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin-bottom: 2rem;
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

# Sidebar logo
with st.sidebar:
    st.markdown("""
    <div style="padding: 1.25rem 0 1rem; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 0.5rem;">
        <div style="font-size:1.3rem;font-weight:800;color:white;letter-spacing:-0.3px;">🛡️ RECOSA</div>
        <div style="font-size:0.72rem;color:#94A3B8;margin-top:2px;">EU Compliance Co-pilot</div>
    </div>
    """, unsafe_allow_html=True)

    # User info + logout
    try:
        email = st.session_state.get("user", {}).get("email", "")
        if email:
            st.markdown(f'<div style="font-size:0.75rem;color:#94A3B8;padding:0.5rem 0 0.25rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{email}</div>', unsafe_allow_html=True)
    except Exception:
        pass

    from auth import logout
    if st.button("Log out", use_container_width=True, key="btn_logout"):
        logout()
        st.rerun()

    st.markdown("<div style='margin-top:0.5rem;border-top:1px solid rgba(255,255,255,0.1);'></div>", unsafe_allow_html=True)

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
