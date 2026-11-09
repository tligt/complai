import os
import time
import streamlit as st
from supabase import create_client, Client, ClientOptions
import sessions
from database import (
    create_user_profile,
    mark_leads_converted, record_funnel_event,
    SIGNUP_PLANS, SUBSCRIPTION_TIERS, TRIAL_DAYS, start_trial,
)

# D-126: the plans the sign-up form offers, as the website's pricing page
# describes them. Prices excluding VAT; keep in step with recosa.eu/pricing.
# (price, description, short line for the plan card)
PLAN_INFO = {
    "starter": ("€49/month", "For micro and small companies: GDPR, NIS2 and the "
                "EU AI Act, one user, the core documents.",
                "Micro and small companies, 1 user"),
    "professional": ("€149/month", "For growing SMEs: several users, unlimited "
                     "website audits, the full document library.",
                     "Growing SMEs, 3 users, full library"),
}
ENTERPRISE_URL = "https://www.recosa.eu/contact"
TERMS_URL = "https://www.recosa.eu/terms-of-service"
PRIVACY_URL = "https://www.recosa.eu/privacy-policy"


def _new_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in secrets.")
    # S51: no automatic refresh. supabase-py otherwise starts a timer per
    # client that, just before the access token expires, spends the
    # single-use refresh token in the background and keeps the result to
    # itself — so the token the app holds is already used when it refreshes
    # (refresh_token_already_used, D-113), and one timer thread lingered per
    # client created. Refreshing is init_auth's job alone.
    return create_client(url, key, options=ClientOptions(
        auto_refresh_token=False, persist_session=False))


def get_supabase() -> Client:
    """An auth-capable client for this login. One per token pair, reused:
    set_session() checks the token with Supabase (a network call), which was
    made on every call before S51."""
    access_token  = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")
    cached = st.session_state.get("_auth_client")
    if cached and cached[0] == (access_token, refresh_token):
        return cached[1]
    client = _new_client()
    try:
        if access_token and refresh_token:
            client.auth.set_session(access_token, refresh_token)
    except Exception:
        pass
    st.session_state["_auth_client"] = ((access_token, refresh_token), client)
    return client


def _set_login(user, access: str | None, refresh: str | None) -> None:
    st.session_state.user          = user
    st.session_state.access_token  = access
    st.session_state.refresh_token = refresh


def _clear_login() -> None:
    _set_login(None, None, None)
    st.session_state.pop("sid", None)


def _app() -> str:
    return st.session_state.get("_auth_app", "client")


def start_login(res) -> None:
    """A fresh login (password, reset link, confirmation link): this tab's
    state, and from S51 a stored login with its cookie, so a refresh or
    another tab keeps it."""
    old = st.session_state.get("sid")
    if old:
        sessions.delete(old)
    sid = sessions.create(_app(), res.user.id, res.session.access_token,
                          res.session.refresh_token)
    st.session_state.sid = sid
    st.session_state._cookie = sid          # written by init_auth's next run
    st.session_state._resume_tried = sid    # this tab has it already
    st.session_state._last_activity = time.time()
    st.session_state._last_touch = time.time()
    _set_login(res.user, res.session.access_token, res.session.refresh_token)


def init_auth(app: str = "client"):
    """Initialise auth session state, pick up a stored login (S51), and
    refresh the token when it is about to expire.

    app: "client" (app.py) or "admin" (admin_app.py) — each has its own
    cookie and limits (sessions.LIMITS)."""
    st.session_state._auth_app = app
    if "_wanted_path" not in st.session_state:
        st.session_state._wanted_path = _requested_path()
    if "user" not in st.session_state:
        st.session_state.user = None
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "refresh_token" not in st.session_state:
        st.session_state.refresh_token = None

    seen = _bridge(app)
    if st.session_state.user is None:
        before = st.session_state.get("_cookie", False)
        _resume(app, seen)
        if st.session_state.get("_cookie", False) != before:
            # The bridge was mounted before the resume decided: one more
            # run takes the change (clearing a dead cookie) to the browser.
            st.rerun()
        if st.session_state.user is None and _waiting_for_browser(seen):
            st.stop()


def _requested_path() -> str:
    """The page the tab was opened on ("documents", "" for the home page),
    read once per tab from the address. A first run that ends before
    st.navigation (the login page, the wait for the cookie) loses it: the
    next run is on the default page."""
    from urllib.parse import urlparse
    try:
        path = urlparse(st.context.url or "").path
    except Exception:
        return ""
    if path.startswith("/~/+"):          # Streamlit Cloud's inner frame
        path = path[len("/~/+"):]
    return path.strip("/")


def go_to_requested_page(current, sections: dict) -> None:
    """S51: once the login is known, open the page the tab was opened on
    (a link to /documents, a reload of it) if this run is on another one.
    Once per tab. Call after st.navigation, before pg.run()."""
    wanted = st.session_state.pop("_wanted_path", None)
    if not wanted or getattr(current, "url_path", None) == wanted:
        return
    for pages in sections.values():
        for page in pages:
            if page.url_path == wanted:
                st.switch_page(page)


def _waiting_for_browser(seen: str | None) -> bool:
    """On Streamlit Cloud the connection carries no cookies, so a reopened
    page only learns about its login when the bridge answers, a moment
    later. Drawing the login page meanwhile loses the page asked for (a
    link to /documents landed on Home): show a short wait instead. The
    bridge answers on its first render; if it ever does not, a link to the
    login page appears after a few seconds (?nobridge=1)."""
    if seen is not None or not sessions.enabled():
        return False
    if st.query_params.get("nobridge") == "1":
        return False
    try:
        if len(st.context.cookies):
            return False          # cookies arrive with the connection (local)
    except Exception:
        pass
    st.html("""<style>
      .recosa-wait{font:14px 'Public Sans',sans-serif;color:#64748B;padding:3rem 0;text-align:center}
      .recosa-wait a{opacity:0;animation:recosa-show .2s 4s forwards;color:#003366}
      @keyframes recosa-show{to{opacity:1}}
    </style><div class="recosa-wait">Opening RECOSA…<br><br>
      <a href="?nobridge=1" target="_self">Continue to log in</a></div>""")
    return True

    if st.session_state.user is not None and st.session_state.get("sid"):
        if not _still_active(app):
            return

    # Refresh only when the access token is about to expire, not on every
    # rerun. Supabase refresh tokens are single-use: refreshing on every
    # click meant any two overlapping reruns (or one interrupted mid-refresh)
    # presented an already-used token, and the failure logged the user out
    # (refresh_token_already_used, dozens of times on 30 Sept 2026).
    if st.session_state.get("refresh_token"):
        remaining = _seconds_until_expiry(st.session_state.get("access_token"))
        if remaining is None or remaining < _REFRESH_MARGIN_SECONDS:
            if st.session_state.get("sid"):
                _refresh_stored(app, remaining)
            else:
                _refresh_here(remaining)


def _bridge(app: str) -> str | None:
    """The cookie bridge, mounted on every run in a hidden container. A
    pending change (set at login, cleared at logout) is sent on every run
    until the browser reports the new value: a run cut short by st.rerun()
    may never reach the browser, and writing the same cookie twice is
    harmless."""
    if not sessions.enabled():
        return None
    pending = st.session_state.get("_cookie", False)
    op = "none" if pending is False else ("set" if pending else "clear")
    with st.container(key="recosa_cookie"):
        st.html("<style>.st-key-recosa_cookie{display:none}</style>")
        seen = sessions.bridge(app, op, pending or None)
    if pending is not False and seen is not None and seen == (pending or ""):
        st.session_state.pop("_cookie", None)      # the browser has it
    return seen


def _resume(app: str, seen: str | None) -> None:
    """A tab that opens with the login cookie: the stored login, if it is
    still valid. Tried once per tab and cookie. The cookie comes from the
    connection's headers (local) or from the browser bridge (Streamlit
    Cloud, where the proxy does not pass cookies on).

    A run can be cut short at any session-state access (the bridge's answer
    starts a new run), so the slow part comes first and "tried" is written
    last: a cut-short attempt is simply made again on the next run."""
    sid = sessions.read_cookie(app) or seen
    if not sid or st.session_state.get("_resume_tried") == sid:
        return
    got = _resume_login(app, sid)
    if got is None:
        st.session_state._cookie = None     # a dead cookie: clear it
    else:
        access, refresh, user = got
        st.session_state.sid = sid
        st.session_state._last_activity = time.time()
        st.session_state._last_touch = time.time()
        # A reopened page is not a new sign-in: the audit trail (D-128)
        # records sign-ins, not reloads.
        st.session_state.signin_logged = True
        _set_login(user, access, refresh)
    st.session_state._resume_tried = sid


def _resume_login(app: str, sid: str):
    """(access, refresh, user) for a stored login, refreshed if needed, or
    None when it is over. No session-state access in here."""
    row = sessions.load(app, sid)
    if not row:
        return None
    access, refresh, user = row["access"], row["refresh"], None
    remaining = _seconds_until_expiry(access)
    if remaining is None or remaining < _REFRESH_MARGIN_SECONDS:
        got = _rotate(app, sid, row)
        if not got:
            sessions.delete(sid)
            return None
        access, refresh, user = got
    if user is None:
        try:
            user = _new_client().auth.get_user(access).user
        except Exception as e:
            print(f"Stored login rejected: {e}")
            sessions.delete(sid)
            return None
    return access, refresh, user


def _still_active(app: str) -> bool:
    """Idle timeout inside an open tab, and the throttled last-seen write."""
    _, idle = sessions.LIMITS[app]
    now = time.time()
    last = st.session_state.get("_last_activity") or now
    if now - last > idle:
        sessions.delete(st.session_state.get("sid"))
        _clear_login()
        st.session_state._cookie = None
        st.session_state.session_ended = True
        return False
    st.session_state._last_activity = now
    if now - (st.session_state.get("_last_touch") or 0) > sessions.TOUCH_EVERY:
        st.session_state._last_touch = now
        sessions.touch(st.session_state.sid)
    return True


def _rotate(app: str, sid: str, row: dict):
    """Refresh a stored login once for all its tabs. Returns (access,
    refresh, user), or None when the login is over."""
    try:
        res = _new_client().auth.refresh_session(row["refresh"])
    except Exception as e:
        print(f"Refresh of the stored login failed: {e}")
        res = None
    if res and res.session:
        if sessions.swap_tokens(sid, row["sealed"], res.session.access_token,
                                res.session.refresh_token):
            return res.session.access_token, res.session.refresh_token, res.user
    # Another tab refreshed first: its tokens are in the row now.
    again = sessions.load(app, sid)
    if again and again["sealed"] != row["sealed"]:
        if (_seconds_until_expiry(again["access"]) or 0) > 0:
            return again["access"], again["refresh"], None
    return None


def _refresh_stored(app: str, remaining: float | None) -> None:
    sid = st.session_state.sid
    row = sessions.load(app, sid)
    if not row:
        # Logged out in another tab, or past its limits.
        if remaining is None or remaining <= 0:
            _clear_login()
            st.session_state._cookie = None
        return
    if row["access"] != st.session_state.access_token and \
            (_seconds_until_expiry(row["access"]) or 0) > (remaining or 0):
        # Another tab already refreshed: take its tokens.
        st.session_state.access_token  = row["access"]
        st.session_state.refresh_token = row["refresh"]
        return
    got = _rotate(app, sid, row)
    if got:
        access, refresh, user = got
        st.session_state.access_token  = access
        st.session_state.refresh_token = refresh
        if user is not None:
            st.session_state.user = user
    elif remaining is None or remaining <= 0:
        sessions.delete(sid)
        _clear_login()
        st.session_state._cookie = None


def _refresh_here(remaining: float | None) -> None:
    """No stored login (S51 switched off): refresh this tab's tokens."""
    try:
        res = _new_client().auth.refresh_session(st.session_state.refresh_token)
        if res and res.session:
            _set_login(res.user, res.session.access_token, res.session.refresh_token)
    except Exception:
        # Only a session whose access token has actually run out is
        # over. If it is still valid, a failed refresh (e.g. another
        # rerun already rotated the token) must not log the user out.
        if remaining is None or remaining <= 0:
            _clear_login()


# Refresh when less than this is left on the access token (default 1 hour).
_REFRESH_MARGIN_SECONDS = 300


def _seconds_until_expiry(access_token: str | None) -> float | None:
    """Seconds before the JWT's exp claim, or None if it can't be read.
    Reads the payload without verifying the signature: only used to decide
    when to refresh, never to trust the token."""
    import base64, json, time
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
        return exp - time.time()
    except Exception:
        return None


def is_logged_in() -> bool:
    return st.session_state.get("user") is not None


def login_ui(admin: bool = False):
    """The form card of the login page (login_page.py draws the page around
    it, D-127): a Log in / Sign up switch, then the form. Forgot password is
    a third state of the same switch, reached from the log-in form.

    admin=True (the back office, D-140): no sign-up here — the Sign up tab
    sends whoever was looking for RECOSA to the client app."""
    # S49: arriving from a free check or a website sign-up link (app.py
    # parks it in session state), the visitor is new — open on Sign up,
    # unless the link is the free check's "Log in instead".
    funnel = st.session_state.get("funnel") or {}
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = (
            "Sign up" if (funnel.get("pending") or funnel.get("signup"))
            and not funnel.get("login") else "Log in")
    if st.session_state.auth_mode == "Forgot":
        _forgot_form()
        return

    def _keep():
        # A segmented control can be clicked off; keep the last choice.
        if st.session_state.get("auth_switch") is None:
            st.session_state.auth_switch = st.session_state.auth_mode
        st.session_state.auth_mode = st.session_state.auth_switch

    st.session_state.auth_switch = st.session_state.auth_mode
    st.segmented_control(
        "Log in or sign up", ["Log in", "Sign up"], key="auth_switch",
        on_change=_keep, label_visibility="collapsed", width="stretch",
    )

    if st.session_state.auth_mode == "Log in":
        _login_form(funnel, admin)
    elif admin:
        _not_here()
    elif st.session_state.get("signup_sent_to"):
        _check_inbox(st.session_state.signup_sent_to,
                     st.session_state.get("signup_plan"))
    else:
        _signup_form(funnel)


def _not_here() -> None:
    """The back office's Sign up tab: this is not where clients sign up or
    log in."""
    app_url = (os.environ.get("APP_BASE_URL") or "https://recosa.streamlit.app").rstrip("/") + "/"
    st.markdown("This is RECOSA's back office, for the RECOSA team only.")
    st.markdown(f'<div class="auth-fine" style="text-align:left;font-size:14px">If you were trying '
                f'to sign up or log in to RECOSA, <a href="{app_url}" target="_top">click here</a>.</div>',
                unsafe_allow_html=True)
    st.link_button("Go to RECOSA", app_url, type="primary", use_container_width=True)


def _go(mode: str) -> None:
    st.session_state.auth_mode = mode
    st.rerun()


def _login_form(funnel: dict, admin: bool = False) -> None:
    email = st.text_input("Email", key="login_email", placeholder="you@company.com")
    password = st.text_input("Password", type="password", key="login_password",
                             placeholder="Your password")
    if st.button("Forgot your password?", key="auth_to_forgot", type="tertiary"):
        _go("Forgot")
    if st.button("Log in", type="primary", use_container_width=True, key="btn_login"):
        if not (email and password):
            st.warning("Enter your email and password.")
            return
        try:
            res = get_supabase().auth.sign_in_with_password(
                {"email": email.strip(), "password": password})
        except Exception as e:
            st.error(_auth_error(e))
            return
        start_login(res)
        # S49: the free check the link carried is saved by app.py after the
        # rerun (funnel stays in session state until then), and its result
        # page opens.
        st.rerun()
    if not admin:
        st.markdown('<div class="auth-fine">New to RECOSA? Switch to <b>Sign up</b> above '
                    'for a free trial.</div>', unsafe_allow_html=True)


def _auth_error(e: Exception) -> str:
    """Supabase's messages are English and technical; the two that people
    actually hit get a plain sentence."""
    msg = str(e)
    if "Invalid login credentials" in msg:
        return "That email and password don't match. Try again, or reset your password."
    if "Email not confirmed" in msg:
        return ("Your email isn't confirmed yet. Open the link we sent you, "
                "then log in.")
    return f"Login failed: {msg}"


def _plan_cards(default: str) -> str:
    """Two clickable cards instead of a radio (D-127). The chosen one gets a
    navy border — its container key ends in _on, which the page CSS reads."""
    if st.session_state.get("signup_plan_pick") not in SIGNUP_PLANS:
        st.session_state.signup_plan_pick = default
    chosen = st.session_state.signup_plan_pick
    st.markdown('<div class="auth-lbl">Choose your plan</div>', unsafe_allow_html=True)
    cols = st.columns(len(SIGNUP_PLANS))
    for col, p in zip(cols, SIGNUP_PLANS):
        price, line, short = PLAN_INFO[p]
        with col, st.container(key=f"plan_{p}_{'on' if p == chosen else 'off'}"):
            if st.button(f"**{SUBSCRIPTION_TIERS[p]}**\n\n{price}\n\n{short}",
                         key=f"plan_pick_{p}", use_container_width=True):
                st.session_state.signup_plan_pick = p
                st.rerun()
    st.markdown(f'<div class="auth-fine" style="text-align:left">Larger organisation? '
                f'<a href="{ENTERPRISE_URL}" target="_blank">Talk to us about Enterprise</a></div>',
                unsafe_allow_html=True)
    return chosen


def _signup_form(funnel: dict) -> None:
    # A free check result rides along: that account starts free, its result
    # first (S49). Everyone else picks a plan, and its trial starts now
    # (D-126) — the website's buttons say "Free trial".
    plan = None
    if funnel.get("pending"):
        st.info("Create your free account to see your full result.")
    else:
        plan = _plan_cards(funnel.get("plan") or "professional")
    new_email = st.text_input("Work email", key="signup_email", placeholder="you@company.com")
    # One password field (D-127): the eye icon shows what was typed, which
    # does the job a second "confirm" field did, with one field fewer.
    new_password = st.text_input("Password", type="password", key="signup_password",
                                 placeholder="At least 8 characters")
    label = (f"Start my free trial — {SUBSCRIPTION_TIERS[plan]}" if plan
             else "Create my free account")
    clicked = st.button(label, type="primary", use_container_width=True, key="btn_signup")
    st.markdown(
        '<div class="auth-fine">'
        + (f"{TRIAL_DAYS} days free, no card needed. " if plan else "")
        + f'By signing up you agree to the <a href="{TERMS_URL}" target="_blank">Terms</a> '
        f'and <a href="{PRIVACY_URL}" target="_blank">Privacy Policy</a>.</div>',
        unsafe_allow_html=True)
    if not clicked:
        return
    new_email = (new_email or "").strip()
    if not new_email or not new_password:
        st.warning("Enter your email and a password.")
        return
    if len(new_password) < 8:
        st.error("Your password needs at least 8 characters.")
        return
    try:
        res = get_supabase().auth.sign_up({"email": new_email, "password": new_password})
    except Exception as e:
        st.error(f"Sign up failed: {e}")
        return
    if not res.user:
        st.error("Sign up failed. Please try again.")
        return
    # An address that already has an account comes back with no identities
    # (Supabase does not say so, to avoid revealing who has an account).
    # Nothing to write then; the screen is the same either way.
    if getattr(res.user, "identities", None) != []:
        # S37: res.user.id exists immediately, whether or not email
        # confirmation is required. S49: the free check result rides on the
        # profile, so it survives the confirmation email and a different
        # browser.
        source = funnel.get("src") or ("website" if funnel.get("signup") else "direct")
        create_user_profile(
            res.user.id, new_email, plan or "professional",
            signup_source=source,
            pending_result=funnel.get("pending"),
        )
        mark_leads_converted(new_email, res.user.id)
        record_funnel_event("signup", (funnel.get("pending") or {}).get("tool"), source)
        if plan and start_trial(res.user.id, plan):
            record_funnel_event("trial_started", None, source)
    st.session_state.signup_sent_to = new_email
    st.session_state.signup_plan = plan
    st.rerun()


def _check_inbox(email: str, plan: str | None) -> None:
    """After sign-up: the one thing left to do, said plainly, with a way to
    get the email again. Replaces the form, so it cannot be missed."""
    st.markdown('<div class="auth-pill">Almost there</div>', unsafe_allow_html=True)
    st.markdown("### Check your inbox")
    st.markdown(
        f"We sent a confirmation link to **{email}**. Open it, then come back "
        "here and log in."
        + (f"\n\nYour {TRIAL_DAYS}-day free trial of **{SUBSCRIPTION_TIERS[plan]}** "
           "has started — no card needed." if plan else "")
    )
    # 9 Nov: a company mail server can hold a first email from a new sender
    # for half an hour (Hostinger did, for recosa.eu); resending doesn't help.
    st.caption("It usually arrives within a minute. Some company mail servers hold the "
               "first email from a new sender for up to 30 minutes, so if it isn't there "
               "yet, check your spam folder and give it a little time. Sending it again "
               "won't make it arrive sooner.")
    c1, c2 = st.columns(2)
    if c1.button("Send the email again", use_container_width=True, key="signup_resend"):
        try:
            get_supabase().auth.resend({"type": "signup", "email": email})
            st.success("Sent again.")
        except Exception as e:
            st.error(f"Could not send it again: {e}")
    if c2.button("Use another address", use_container_width=True, key="signup_restart"):
        for k in ("signup_sent_to", "signup_plan", "signup_email", "signup_password"):
            st.session_state.pop(k, None)
        st.rerun()


# ── Forgot password (D-127, pulled ahead from S51) ────────────────────────
# The reset email links back to the app with ?token_hash=…&type=recovery
# (Supabase's "Reset password" email template must build its link that way:
# Streamlit cannot read the #access_token fragment of the default link).
# app.py hands those two parameters to start_password_recovery(), which logs
# the person in with that one-time token, and set_new_password_ui() asks for
# the new password before anything else is shown.

def _forgot_form() -> None:
    st.markdown("### Reset your password")
    sent = st.session_state.get("reset_sent_to")
    if sent:
        st.markdown(f"If an account exists for **{sent}**, we've sent it a link to "
                    "choose a new password. It works once, for one hour.")
        st.caption("It usually arrives within a minute, but some company mail servers hold "
                   "it for up to 30 minutes. Check your spam folder too. The link stays "
                   "valid for an hour from when it was sent.")
    else:
        st.caption("Enter the email you signed up with. We'll send you a link to "
                   "choose a new password.")
        email = st.text_input("Email", key="reset_email", placeholder="you@company.com")
        if st.button("Send the reset link", type="primary", use_container_width=True,
                     key="btn_reset"):
            email = (email or "").strip()
            if "@" not in email:
                st.warning("Enter the email you signed up with.")
            else:
                try:
                    get_supabase().auth.reset_password_for_email(email)
                except Exception as e:
                    # Rate limits are the realistic failure; the answer is
                    # the same either way, so nobody learns who has an account.
                    print(f"Password reset request failed: {e}")
                st.session_state.reset_sent_to = email
                st.rerun()
    if st.button("Back to log in", key="auth_back", type="tertiary"):
        st.session_state.pop("reset_sent_to", None)
        _go("Log in")


def start_password_recovery(token_hash: str, otp_type: str = "recovery") -> bool:
    """Logs in with the reset email's one-time token. True when it worked;
    the caller then shows set_new_password_ui().

    D-146: otp_type="invite" is the invite email's "Choose my password" link
    for a colleague whose account RECOSA created; the same screen follows,
    worded as a welcome."""
    try:
        res = get_supabase().auth.verify_otp({"token_hash": token_hash, "type": otp_type})
    except Exception as e:
        print(f"Password recovery link rejected: {e}")
        return False
    if not (res and res.session):
        return False
    start_login(res)
    st.session_state.password_recovery = True
    if otp_type == "invite":
        st.session_state.password_welcome = True
    return True


def start_email_confirmation(token_hash: str) -> bool:
    """D-139. The sign-up confirmation link ("Confirm signup" template, as
    ?token_hash=…&type=email) confirms the address AND logs the person in,
    so they land on their free check result and its emails go out at once —
    not hours later from the scheduled job. True when it worked."""
    try:
        res = get_supabase().auth.verify_otp({"token_hash": token_hash, "type": "email"})
    except Exception as e:
        print(f"Confirmation link rejected: {e}")
        return False
    if not (res and res.session):
        return False
    start_login(res)
    return True


def set_new_password_ui() -> None:
    if st.session_state.get("password_welcome"):
        st.markdown("### Welcome to RECOSA")
        st.caption("You've been given access by a colleague. Choose your password "
                   "to finish setting up your account.")
    else:
        st.markdown("### Choose a new password")
    p1 = st.text_input("New password", type="password", key="recover_pw",
                       placeholder="At least 8 characters")
    if st.button("Save my new password", type="primary", use_container_width=True,
                 key="btn_recover"):
        if len(p1 or "") < 8:
            st.error("Your password needs at least 8 characters.")
            return
        ok, err = change_password(p1)
        if ok:
            st.session_state.pop("password_recovery", None)
            st.session_state.pop("password_welcome", None)
            st.session_state.pop("recover_pw", None)
            st.success("Saved. Taking you to RECOSA…")
            st.rerun()
        else:
            st.error(f"Could not save it: {err}. Ask for a new link and try again.")


def logout():
    """Clear session and log out."""
    try:
        supabase = get_supabase()
        # "local": end this session only. supabase-py defaults to "global",
        # which revokes every session of the account, so logging out in one
        # browser silently logged the user out everywhere else at their
        # next click (init_auth's refresh then fails and clears the session).
        supabase.auth.sign_out({"scope": "local"})
    except Exception:
        pass
    # S51: the stored login goes, so the cookie opens nothing any more, even
    # if the browser keeps it; the next run clears it too.
    sessions.delete(st.session_state.get("sid"))
    for key in ["user", "access_token", "refresh_token", "sid", "_auth_client",
                "selected_client", "messages", "clients", "signin_logged"]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state._cookie = None
    st.rerun()


def get_user_id() -> str:
    """Return the current user's UUID."""
    return st.session_state.user.id


def change_password(new_password: str) -> tuple[bool, str | None]:
    """Change the logged-in user's password.

    Must go through THIS module's get_supabase(), not database.py's. That
    one only sets a PostgREST bearer token (client.postgrest.auth(token)),
    enough for table access under RLS but not a full auth session — and
    supabase_auth's update_user() calls self.get_session() first and raises
    AuthSessionMissingError if there isn't one. This get_supabase() calls
    client.auth.set_session(access_token, refresh_token), which is what
    actually establishes one.
    """
    try:
        supabase = get_supabase()
        supabase.auth.update_user({"password": new_password})
        # S51: a new password ends the logins kept in other browsers.
        sessions.delete_others(get_user_id(), st.session_state.get("sid"))
        return True, None
    except Exception as e:
        return False, str(e)
