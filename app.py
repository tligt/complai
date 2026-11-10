from i18n import tr  # S64 interface translation (D-164)
from dotenv import load_dotenv

# No-op when running on Streamlit Cloud (no .env file there, and secrets
# are already exposed as env vars) — only fills in values for local runs.
load_dotenv()

# D-116: after a deploy, reload our modules that changed on disk before
# anything below imports names from them (fresh_modules.py).
import fresh_modules
fresh_modules.refresh()

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
# Shared with the back office (D-140): brand.py, and the theme in
# .streamlit/config.toml.
import brand
brand.apply_shell()

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
# The public app's CTA links here with ?src= and ?quiz= (a digit per NIS2
# question) and/or ?site= (a domain), ?aiact= (a digit per AI Act question,
# S55), and ?scope= (the four scope
# answers, D-129) — never the
# email. Parked in session state for the
# signup form (auth.login_ui), which stores it on the new profile, and
# removed from the URL at once, as the ticket link is above.
#
# D-126: the website's sign-up links add ?signup=<plan> (starter,
# professional) or ?signup=1, which opens the sign-up form with that plan
# chosen. Anything else is ignored: the link is visitor-controlled.
if any(k in st.query_params for k in ("src", "quiz", "site", "scope", "aiact", "gdpr", "signup",
                                      "login")):
    import funnel as _funnel
    from database import SIGNUP_PLANS as _PLANS
    _src = (st.query_params.get("src") or "")[:40] or None
    _pending = _funnel.pending_from_params(
        st.query_params.get("quiz"), st.query_params.get("site"),
        st.query_params.get("scope"), st.query_params.get("aiact"),
        st.query_params.get("gdpr"))
    _signup = (st.query_params.get("signup") or "").strip().lower()
    st.session_state.funnel = {
        "src": _src, "pending": _pending,
        "signup": bool(_signup),
        "plan": _signup if _signup in _PLANS else None,
        # The public app's "Log in instead" link: an existing account.
        "login": st.query_params.get("login") == "1",
    }
    record_funnel_event("app_landing", (_pending or {}).get("tool"), _src)
    for _k in ("src", "quiz", "site", "scope", "aiact", "gdpr", "signup", "login"):
        if _k in st.query_params:
            del st.query_params[_k]

# ── Auth ──────────────────────────────────────────────────────
init_auth("client")

# ── Login screen ──────────────────────────────────────────────
# D-127: a password-reset link (Supabase "Reset password" template) lands
# here with ?token_hash=…&type=recovery. It logs the person in once; they
# then choose a new password before anything else.
# D-146: an invite's "Choose my password" link (?type=invite) takes the
# same path, for a colleague whose account RECOSA created.
if st.query_params.get("type") in ("recovery", "invite") and st.query_params.get("token_hash"):
    from auth import start_password_recovery
    _th = st.query_params["token_hash"]
    _otp = st.query_params["type"]
    del st.query_params["token_hash"]
    del st.query_params["type"]
    if not start_password_recovery(_th, _otp):
        st.session_state.auth_mode = "Forgot"
        st.session_state.recovery_failed = True

# D-139: the sign-up confirmation link ("Confirm signup" template) lands here
# with ?token_hash=…&type=email (or the older type=signup). It confirms the
# address and logs the person in, so the free check result opens and its
# emails go out now. Supabase's default link confirms too, but hands the
# session over in a #fragment the app cannot read: the person then logs in.
if (st.query_params.get("type") in ("email", "signup")
        and st.query_params.get("token_hash")):
    from auth import start_email_confirmation
    _th = st.query_params["token_hash"]
    del st.query_params["token_hash"]
    del st.query_params["type"]
    if not start_email_confirmation(_th):
        st.session_state.auth_mode = "Log in"
        st.session_state.confirm_failed = True

if not is_logged_in():
    import login_page
    if st.session_state.pop("recovery_failed", False):
        st.warning(tr("That reset link has expired or was already used. Ask for a new one below."))
    if st.session_state.pop("session_ended", False):
        st.info(tr("You were logged out after a day without activity. Log in again to continue."))
    if st.session_state.pop("confirm_failed", False):
        st.info(tr("That confirmation link has expired or was already used. If you've "
                "confirmed your address already, just log in."))
    login_page.render()
    st.stop()

if st.session_state.get("password_recovery"):
    import login_page
    login_page.render_password_reset()
    st.stop()

# ── Authenticated ─────────────────────────────────────────────
user_id = get_user_id()

# Sidebar: the logo above the menu (brand.py), then the menu's own styles.
brand.apply_logo("RECOSA", account=getattr(st.session_state.user, "email", None))
st.markdown("""
<style>
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

# ── Sign-in on the audit trail (S54) ─────────────────────────────
# Once per browser session: on every company this account can reach, so each
# company's trail says who came in and when.
if not st.session_state.get("signin_logged"):
    st.session_state.signin_logged = True
    import database as _db_audit
    _db_audit.log_account_event(user_id, "sign_in", f"{st.session_state.user.email} signed in",
                                metadata={"email": st.session_state.user.email})

# ── Access: free account or subscribed (S49, D-115) ─────────────────────
# 'registered' (a free account) and 'expired' see their free check result
# and the subscribe page — every other menu item opens the subscribe page.
# Admins, and members of someone else's workspace (S38: the owner's plan
# covers them), always get the full app. A profile that can't be read
# fails open, as before S49.
_profile = expire_trial_if_due(get_user_profile(user_id))
# S64 interface slice (D-164): the user's interface language, read by i18n._
# on every page. The Account page saves it; read here on every run so a
# change shows at once.
st.session_state["ui_language"] = (_profile or {}).get("ui_language") or "en"
_funnel_state = st.session_state.pop("funnel", None)
if _funnel_state and _funnel_state.get("pending"):
    # Logged in from the free check's link, or already logged in when it
    # was opened: the check just taken replaces an older one (the account
    # may have taken one before), and the result page opens.
    import funnel as _funnel
    _merged = _funnel.merge_pending(_profile.get("pending_result"), _funnel_state["pending"])
    save_pending_result(user_id, _merged)
    _profile["pending_result"] = _merged
    st.session_state.open_free_check = True
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
    and not any(c.get("role") != "owner" for c in load_accessible_clients(user_id))
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
        if st.button(tr("Log out"), use_container_width=True, key="btn_logout"):
            logout()
    st.title(tr("Welcome to RECOSA"))
    # D-126: most sign-ups are the company itself; only Advisory manages
    # clients.
    if _profile.get("subscription_tier") == "advisory":
        st.caption(tr("Set up your first client company to get started."))
    else:
        st.caption(tr("Tell us about your company to get started — a company number "
                   "or website fills most of it in. Everything can be changed later "
                   "on Company profile."))
    # S48: the shared form (client_setup.py) — company-number lookup and
    # website scan included. It clears the client caches itself, so the
    # rerun lands straight in the app.
    from client_setup import render_new_client_form
    if render_new_client_form(user_id, key="ob"):
        st.rerun()
    if st.button(tr("Skip for now"), key="ob_skip"):
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
home      = st.Page("app_pages/dashboard.py", title=tr("Home"),           icon="🏠", default=True)
plan      = st.Page("app_pages/action_plan.py", title=tr("Action plan"),  icon="📋")
oblig     = st.Page("app_pages/obligations.py", title=tr("Obligations"),  icon="✅")
gap       = st.Page("app_pages/gap.py",       title=tr("Gap Assessment"), icon="🔍")
risk      = st.Page("app_pages/risk.py",      title=tr("Risk assessments"), icon="⚖️")
inventory = st.Page("app_pages/inventory.py", title=tr("Systems"),        icon="🗂️")
training  = st.Page("app_pages/training.py",  title=tr("Training"),       icon="🎓")
ai_inv    = st.Page("app_pages/ai_inventory.py", title=tr("AI inventory"), icon="🤖")
documents = st.Page("app_pages/documents.py", title=tr("Documents"),      icon="📄")
record    = st.Page("app_pages/compliance_record.py", title=tr("Compliance Record"),
                    icon="🗄️", visibility="hidden")
incidents = st.Page("app_pages/incidents.py", title=tr("Incidents"),      icon="🚨")
wording   = st.Page("app_pages/wording.py",   title=tr("Incident wording"),
                    icon="✍️", visibility="hidden")
audit     = st.Page("app_pages/audit.py",     title=tr("Web Audit"),      icon="🌐")
chat      = st.Page("app_pages/chat.py",      title=tr("Assistant"),      icon="💬")
company   = st.Page("app_pages/company.py",   title=tr("Company profile"), icon="🏢")
profile   = st.Page("app_pages/profile.py",   title=tr("Account"),        icon="👤")
team      = st.Page("app_pages/team.py",      title=tr("Team"),           icon="👥")
group_pg  = st.Page("app_pages/group.py",     title=tr("Group"),          icon="🏛️")
activity  = st.Page("app_pages/activity.py",  title=tr("Activity Log"),   icon="🕐")
glossary  = st.Page("app_pages/glossary.py",  title=tr("Glossary"),       icon="📖")

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


logout_pg = st.Page(_logout_page, title=tr("Log out"), icon="🚪", url_path="logout")

# S56: the inbox — tasks given to you, comments, mentions. In the menu once
# you work with someone on a company, or have anything in it.
import work_items as _W
_inbox_n = _W.unread_count(user_id)
inbox = st.Page("app_pages/inbox.py",
                title=f"Inbox ({_inbox_n})" if _inbox_n else "Inbox", icon="📥")
_show_inbox = bool(_inbox_n) or any(
    _W.has_team(c["id"]) for c in (load_accessible_clients(user_id) or [])[:10])

_sections = {
    "":         [home, plan] + ([inbox] if _show_inbox else []),
    "Assess":   [oblig, gap, risk],
    "Records":  [inventory, ai_inv, training, documents, record],
    "Respond":  [incidents, wording],
    "Tools":    [audit, chat],
    "Account":  [company, profile, team, alerts, activity, glossary, support],
}

# S54: the Group page, for an Enterprise account or anyone in a group.
from database import load_member_groups
if _profile.get("subscription_tier") == "enterprise" or load_member_groups(user_id):
    _sections["Account"].insert(3, group_pg)

if limited_access:
    # S49. Same menu, so a free account sees what RECOSA does; every item
    # opens the subscribe page under its own title and URL. The free check
    # result is the one real page, and the default.
    from subscribe_view import render_subscribe

    def _locked(page):
        # Home is the full app's default page, so its url_path is "".
        return st.Page(render_subscribe, title=page.title, icon=page.icon,
                       url_path=page.url_path or "home", visibility=page.visibility)

    free_check = st.Page("app_pages/free_check.py", title=tr("Your free check"),
                         icon="🎯", default=True)
    _sections = {name: [_locked(p) for p in pages] for name, pages in _sections.items()}
    _sections[""] = [free_check] + _sections[""]
elif _profile.get("pending_result"):
    # A full account that took a free check (already a client, or logged in
    # from the public app's "Log in instead"): the result is under Account.
    free_check = st.Page("app_pages/free_check.py", title=tr("Your free check"), icon="🎯")
    _sections["Account"].append(free_check)

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
            st.markdown(f'<div class="nav-group">{tr(_header)}</div>', unsafe_allow_html=True)
        for _p in _shown:
            st.page_link(_p, width="stretch")

# A ticket deep link bypasses everything else and goes straight to the
# thread. Reading a ticket needs no client context — the ticket carries its
# own client_id from creation time — so there is nothing to gate on.
_pending = st.session_state.pop("pending_ticket", None)
if _pending and not limited_access:
    st.session_state.support_open_ticket = _pending
    st.switch_page(support)

# Arrived with a free check: straight to its result, whatever the account.
if st.session_state.pop("open_free_check", False) and not limited_access:
    st.switch_page(free_check)

# S51: a link or reload of a page that first went through the login (or the
# wait for the login cookie) opens that page, not Home.
from auth import go_to_requested_page
go_to_requested_page(pg, _sections)

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
    "group":     "account",
    "glossary":  "other",
    "inbox":     "obligations",
    "training":  "obligations",
    "ai_inventory": "obligations",
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
