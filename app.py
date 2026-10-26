from dotenv import load_dotenv

# No-op when running on Streamlit Cloud (no .env file there, and secrets
# are already exposed as env vars) — only fills in values for local runs.
load_dotenv()

import streamlit as st
from auth import init_auth, is_logged_in, get_user_id
from database import (
    count_unread_replies, claim_pending_invites, get_user_profile,
    expire_trial_if_due, save_pending_result, record_funnel_event,
)
from cached_reads import load_clients, load_accessible_clients
from support_widget import render_help_widget

st.set_page_config(
    page_title="RECOSA",
    page_icon="🛡️",
    layout="wide",
    # "auto": open on desktop, closed on a phone. "expanded" opened the menu
    # over the page on every load on a phone (usability audit C4, 26 Oct).
    initial_sidebar_state="auto",
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
/* Nav section labels. stNavSectionHeader is the element Streamlit 1.61
   renders; the old stSidebarNavSeparator rule matched nothing, so the
   group titles came out dark grey on dark blue (usability audit C3). */
[data-testid="stNavSectionHeader"],
[data-testid="stNavSectionHeader"] * {
    color: #94A3B8 !important;
    visibility: visible !important;
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}
/* "View N more" — was dark grey on dark blue (audit C2). */
[data-testid="stSidebarNavViewButton"],
[data-testid="stSidebarNavViewButton"] * {
    color: #E2E8F0 !important;
    font-weight: 600 !important;
}
/* Sidebar buttons (Log out, New chat…): the text rule above made their
   label pale grey on Streamlit's near-white button, 1.4:1 (audit C1). */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.45) !important;
}
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton > button * {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.10) !important;
}
/* Sidebar inputs */
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    border-color: rgba(255,255,255,0.15) !important;
    color: white !important;
}
/* Streamlit 1.61's select box is a text input inside; the company switcher's
   value was dark grey on dark blue. */
[data-testid="stSidebar"] [data-testid="stSelectbox"] input {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stSelectbox svg {
    fill: #94A3B8 !important;
}

/* ── Buttons ── */
/* Brand teal with dark blue text: white on #14C7D5 was 2.1:1, dark blue is
   6.1:1 (audit M12). Form submit and link buttons get the same look — they
   were Streamlit's default red. */
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"],
[data-testid="stBaseLinkButton-primary"] {
    background: #14C7D5 !important;
    border: none !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    transition: background 0.2s;
}
.stButton > button[kind="primary"],
.stButton > button[kind="primary"] *,
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"],
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] *,
[data-testid="stBaseLinkButton-primary"],
[data-testid="stBaseLinkButton-primary"] * {
    color: #003366 !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"]:hover,
[data-testid="stBaseLinkButton-primary"]:hover {
    background: #0E7C86 !important;
}
.stButton > button[kind="primary"]:hover *,
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"]:hover *,
[data-testid="stBaseLinkButton-primary"]:hover * {
    color: #FFFFFF !important;
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

# ── Deep link capture ─────────────────────────────────────────
# Must happen before init_auth(), because an unauthenticated arrival from a
# notification email hits st.stop() on the login screen and the rerun after
# login carries neither the /support path nor the query string. Session
# state does survive it, so the id is parked there and consumed once
# navigation exists.
#
# The param is deleted immediately: leaving it in the URL means the next
# rerun re-captures it, which fights the switch_page below and loops.
if "ticket" in st.query_params:
    st.session_state.pending_ticket = st.query_params["ticket"]
    del st.query_params["ticket"]

# ── Free check carry-over (S49, D-115) ───────────────────────
# The public app's CTA links here with ?src= and ?quiz= (ten digits) or
# ?site= (a domain) — never the email. Parked in session state for the
# signup form (auth.login_ui), which stores it on the new profile, and
# removed from the URL at once, as the ticket link is above.
if any(k in st.query_params for k in ("src", "quiz", "site")):
    import funnel as _funnel
    _src = (st.query_params.get("src") or "")[:40] or None
    _pending = _funnel.pending_from_params(
        st.query_params.get("quiz"), st.query_params.get("site"))
    st.session_state.funnel = {"src": _src, "pending": _pending}
    record_funnel_event("app_landing", (_pending or {}).get("tool"), _src)
    for _k in ("src", "quiz", "site"):
        if _k in st.query_params:
            del st.query_params[_k]

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
/* Room for the logo. The menu is drawn by this script (st.page_link), so
   it is user content, not stSidebarNav (usability audit batch 2). */
[data-testid="stSidebarUserContent"] {
    padding-top: 1.25rem !important;
}
/* Menu group titles */
.nav-group {
    color: #94A3B8 !important;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 0.9rem 0 0.15rem 0.75rem;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] {
    margin: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] span {
    color: #E2E8F0 !important;
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

# ── Claim any pending workspace invites ───────────────────────────
# S38. Runs on every authenticated load, before the zero-client gate below
# — an invited member with zero clients of their OWN must not be shown
# "create your first client" once their invite has claimed. Cheap when
# there is nothing to claim: one UPDATE that matches zero rows.
if claim_pending_invites(user_id, st.session_state.user.email):
    load_clients.clear()
    load_accessible_clients.clear()

# ── Access: free account or subscribed (S49, D-115) ─────────────────────
# 'registered' (a free account) and 'expired' see their free check result
# and the subscribe page — every other menu item opens the subscribe page.
# Admins, and members of someone else's workspace (S38: the owner's plan
# covers them), always get the full app. A profile that can't be read
# fails open, as before S49.
_profile = expire_trial_if_due(get_user_profile(user_id))
_funnel_state = st.session_state.pop("funnel", None)
if _funnel_state and _funnel_state.get("pending") and not _profile.get("pending_result"):
    # Already logged in when the free check's link was opened.
    save_pending_result(user_id, _funnel_state["pending"])
    _profile["pending_result"] = _funnel_state["pending"]
if not _profile.get("pending_result"):
    # S49 part 2 (D-119): an account made by the public app's one form
    # carries its free check in user metadata. First login copies it to the
    # profile, where the free check page reads it.
    from funnel_delivery import pending_of
    _meta = getattr(st.session_state.user, "user_metadata", None) or {}
    _meta_pending = pending_of(_meta)
    if _meta_pending and save_pending_result(user_id, _meta_pending):
        _profile["pending_result"] = _meta_pending
        # getattr, not a from-import: Streamlit Cloud can serve a new app.py
        # against an older database module still in memory (D-116, and again
        # on 26 Oct), and the source is not worth failing a login over.
        import database as _db
        _save_source = getattr(_db, "save_signup_source", None)
        if _save_source:
            _save_source(user_id, _meta.get("recosa_source"))
limited_access = (
    _profile.get("role") != "admin"
    and (_profile.get("subscription_status") or "active") in ("registered", "expired")
    and not any(c.get("role") == "member" for c in load_accessible_clients(user_id))
)

with st.sidebar:
    if _profile.get("subscription_status") == "trial" and _profile.get("trial_ends_at"):
        from datetime import datetime, timezone
        _left = (datetime.fromisoformat(_profile["trial_ends_at"].replace("Z", "+00:00"))
                 - datetime.now(timezone.utc)).days + 1
        st.caption(f"Free trial — {_left} day{'s' if _left != 1 else ''} left")

# ── First-run: no client yet ─────────────────────────────────────
# S37, widened in S38 to accessible clients (owned or member-of) — not
# load_clients, which is owned-only and would wrongly show this to a
# member who just claimed access to someone else's client. Every page
# reachable below this point (Chat included — chat.py has its own near-
# identical dead end at chat.py:516-542) stops cold with no client to
# work against. Intercepted here, once, before st.navigation even builds,
# rather than patching each page's own empty state — Log out above still
# works since the sidebar block already rendered.
# S49 part 2: a free account that arrived with a free check sees its result
# first — that is what the form promised. Setting up the company comes after
# (the free check page and the trial work without one).
_came_with_check = limited_access and bool(_profile.get("pending_result"))
if (not load_accessible_clients(user_id) and not st.session_state.get("skip_onboarding")
        and not _came_with_check):
    with st.sidebar:
        from auth import logout
        if st.button("Log out", use_container_width=True, key="btn_logout"):
            logout()
    st.title("Welcome to RECOSA")
    st.caption("Set up your first client to get started.")
    # S48: the shared form (client_setup.py) — company-number lookup and
    # website scan included. It clears the client caches itself, so the
    # rerun lands straight in the app.
    from client_setup import render_new_client_form
    if render_new_client_form(user_id, key="ob"):
        st.rerun()
    if st.button("Skip for now", key="ob_skip"):
        st.session_state.skip_onboarding = True
        st.rerun()
    st.stop()

# ── Navigation ────────────────────────────────────────────────
# The page files live in app_pages/, NOT pages/ (S49). Streamlit treats a
# folder named pages/ as legacy multipage auto-discovery: any run that hasn't
# yet called st.navigation — a fresh browser load of /dashboard, or a click
# in the sidebar list shown during login and onboarding — executed the page
# file directly, skipping this script and with it the login check and the
# subscribe gate below. Only a crash on the missing session stopped it.
# Usability audit batch 2 (26 Oct): grouped by what the user is trying to do,
# Home first. Pages reached from another page rather than the menu are
# registered with visibility="hidden" (Compliance Record from Documents,
# Incident wording from Incidents) so links and switch_page still work.
home      = st.Page("app_pages/dashboard.py", title="Home",           icon="🏠", default=True)
plan      = st.Page("app_pages/action_plan.py", title="Action plan",  icon="📋")
oblig     = st.Page("app_pages/obligations.py", title="Obligations",  icon="✅")
gap       = st.Page("app_pages/gap.py",       title="Gap Assessment", icon="🔍")
risk      = st.Page("app_pages/risk.py",      title="Risk assessments", icon="⚖️")
inventory = st.Page("app_pages/inventory.py", title="Systems",        icon="🗂️")
documents = st.Page("app_pages/documents.py", title="Documents",      icon="📄")
record    = st.Page("app_pages/compliance_record.py", title="Compliance Record",
                    icon="🗄️", visibility="hidden")
incidents = st.Page("app_pages/incidents.py", title="Incidents",      icon="🚨")
wording   = st.Page("app_pages/wording.py",   title="Incident wording",
                    icon="✍️", visibility="hidden")
audit     = st.Page("app_pages/audit.py",     title="Web Audit",      icon="🌐")
chat      = st.Page("app_pages/chat.py",      title="Assistant",      icon="💬")
company   = st.Page("app_pages/company.py",   title="Company profile", icon="🏢")
profile   = st.Page("app_pages/profile.py",   title="Account",        icon="👤")
team      = st.Page("app_pages/team.py",      title="Team",           icon="👥")
activity  = st.Page("app_pages/activity.py",  title="Activity Log",   icon="🕐")

# NOTE: declaring a Page does nothing on its own — it has to appear in the
# st.navigation dict below AND in PAGE_CONTEXT at the foot of this file. A page
# missing from the dict fails silently: no error, no warning, just an absent
# link. One missing from PAGE_CONTEXT falls through to "other" and mis-routes
# any support ticket raised on it.

# Support and Alerts carry an unread count. st.page_link has no badge slot,
# so the count goes in the title — without it, a support inbox nobody is
# prompted to check is the main way replies go unread.
_unread = count_unread_replies(user_id)
support   = st.Page(
    "app_pages/support.py",
    title=f"Support ({_unread})" if _unread else "Support",
    icon="🛟",
)
from cached_reads import count_unread_alerts as _count_alerts
_alerts_n = _count_alerts(user_id)
alerts    = st.Page("app_pages/alerts.py",
                    title=f"Alerts ({_alerts_n})" if _alerts_n else "Alerts", icon="🔔")


def _logout_page():
    from auth import logout
    logout()


logout_pg = st.Page(_logout_page, title="Log out", icon="🚪", url_path="logout")

_sections = {
    "":         [home, plan],
    "Assess":   [oblig, gap, risk],
    "Records":  [inventory, documents, record],
    "Respond":  [incidents, wording],
    "Tools":    [audit, chat],
    "Account":  [company, profile, team, alerts, activity, support],
}

if limited_access:
    # S49. Same menu, so a free account sees what RECOSA does; every item
    # opens the subscribe page under its own title and URL. The free check
    # result is the one real page, and the default.
    from subscribe_view import render_subscribe

    def _locked(page):
        # Home is the full app's default page, so its url_path is "".
        return st.Page(render_subscribe, title=page.title, icon=page.icon,
                       url_path=page.url_path or "home", visibility=page.visibility)

    free_check = st.Page("app_pages/free_check.py", title="Your free check",
                         icon="🎯", default=True)
    _sections = {name: [_locked(p) for p in pages] for name, pages in _sections.items()}
    _sections[""] = [free_check] + _sections[""]

_sections["Account"] = _sections["Account"] + [logout_pg]

pg = st.navigation(_sections, position="hidden")

# ── Menu ──────────────────────────────────────────────────────
# Drawn here rather than by st.navigation, which always renders above
# anything the app puts in the sidebar: the company switcher belongs at the
# top (audit H1), and a page's own sidebar tools (Assistant's history) below
# the menu.
from active_client import render_company_switcher
with st.sidebar:
    if not limited_access:
        render_company_switcher(user_id)
    for _header, _pages in _sections.items():
        _shown = [p for p in _pages if p.visibility != "hidden"]
        if not _shown:
            continue
        if _header:
            st.markdown(f'<div class="nav-group">{_header}</div>', unsafe_allow_html=True)
        for _p in _shown:
            st.page_link(_p, width="stretch")

# A ticket deep link bypasses everything else and goes straight to the
# thread. Reading a ticket needs no client context — the ticket carries its
# own client_id from creation time — so there is nothing to gate on.
_pending = st.session_state.pop("pending_ticket", None)
if _pending and not limited_access:
    st.session_state.support_open_ticket = _pending
    st.switch_page(support)

pg.run()

# ── Help widget ───────────────────────────────────────────────
# Mounted once here rather than per page. app.py runs on every page load;
# individual page modules only run when active, so a call inside chat.py
# would render the widget on the chat page only.
#
# Called after pg.run() so it lands at the bottom of the sidebar, below
# whatever the active page contributed, and so session state written by
# that page (selected client, chat session) is already populated.
# Keyed on url_path (derived from the module filename), not title. Titles
# are display strings and this one already moves: Support becomes
# "Support (2)" when replies are unread, which silently dropped the context
# to "other" on exactly the page where a ticket is most likely to be raised.
PAGE_CONTEXT = {
    "chat":      "chat",
    "dashboard": "dashboard",
    "gap":       "gap_assessment",
    "inventory": "inventory",
    "documents": "document_generation",
    "audit":     "website_audit",
    "obligations": "obligations",
    "wording":     "document_generation",
    "risk":        "risk_assessment",
    "compliance_record": "compliance_record",
    "alerts":    "compliance_pulse",
    "profile":   "account",
    "activity":  "account",
    "support":   "account",
    "free_check": "account",
    "incidents": "incidents",
    "action_plan": "obligations",
    "company":   "account",
    "team":      "account",
}

# The default page is served at the root, so its url_path is empty.
_ctx = PAGE_CONTEXT.get(pg.url_path or "dashboard", "other")
_client = st.session_state.get("selected_client") or {}

render_help_widget(
    user_id=user_id,
    context=_ctx,
    # Only chat has a meaningful reference to attach; elsewhere the page
    # context alone is enough to route the ticket.
    context_ref=st.session_state.get("session_id") if _ctx == "chat" else None,
    client_id=_client.get("id"),
)
