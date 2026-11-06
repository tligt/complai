from dotenv import load_dotenv

# No-op when running on Streamlit Cloud (no .env file there, and secrets
# are already exposed as env vars) — only fills in values for local runs.
load_dotenv()

import streamlit as st
from auth import init_auth, is_logged_in, get_user_id
from database import is_admin, count_open_tickets

st.set_page_config(
    page_title="RECOSA Admin",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── The client app's look (D-140): brand.py and .streamlit/config.toml ────
import brand
brand.apply_shell()

init_auth("admin")

if not is_logged_in():
    import login_page
    login_page.render_admin()
    st.stop()

brand.apply_logo("RECOSA Admin", native_nav=True,
                account=getattr(st.session_state.user, "email", None))

user_id = get_user_id()
if not is_admin(user_id):
    st.error("🚫 Access denied — admin privileges required.")
    st.caption("If you believe this is an error, contact your system administrator.")
    st.stop()

home       = st.Page("pages_admin/home.py",       title="Home",          icon="⚙️",  default=True)
dashboard  = st.Page("pages_admin/dashboard.py",  title="Dashboard",     icon="📊")
users      = st.Page("pages_admin/users.py",      title="Users",         icon="👥")
monitoring = st.Page("pages_admin/monitoring.py", title="Monitoring",    icon="📡")
kb         = st.Page("pages_admin/kb.py",         title="Knowledge Base",icon="📚")
audit_log  = st.Page("pages_admin/audit_log.py",  title="Audit Trail",   icon="🕐")
feedback   = st.Page("pages_admin/feedback.py",   title="Feedback",      icon="👍")
versions   = st.Page("pages_admin/versions.py", title="Versions", icon="🔧")

# Open + in-progress count in the title: st.navigation has no badge slot,
# and an unattended ticket queue is the failure mode worth designing against.
_open_tickets = count_open_tickets()
tickets = st.Page(
    "pages_admin/tickets.py",
    title=f"Tickets ({_open_tickets})" if _open_tickets else "Tickets",
    icon="🎫",
)

_admin_sections = {
    "Admin":   [home, dashboard, users, audit_log, versions],
    "Support": [tickets, feedback],
    "Content": [monitoring, kb],
}
pg = st.navigation(_admin_sections)
# S51: a link or reload of a page that first went through the login opens it.
from auth import go_to_requested_page
go_to_requested_page(pg, _admin_sections)
pg.run()
