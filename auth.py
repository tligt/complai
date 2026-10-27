import os
import streamlit as st
from supabase import create_client, Client
from database import (
    create_user_profile, get_user_profile, save_pending_result,
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


def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in secrets.")
    client = create_client(url, key)
    try:
        access_token  = st.session_state.get("access_token")
        refresh_token = st.session_state.get("refresh_token")
        if access_token and refresh_token:
            client.auth.set_session(access_token, refresh_token)
    except Exception:
        pass
    return client


def init_auth():
    """Initialise auth session state and refresh token if needed."""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "refresh_token" not in st.session_state:
        st.session_state.refresh_token = None

    # Refresh only when the access token is about to expire, not on every
    # rerun. Supabase refresh tokens are single-use: refreshing on every
    # click meant any two overlapping reruns (or one interrupted mid-refresh)
    # presented an already-used token, and the failure logged the user out
    # (refresh_token_already_used, dozens of times on 30 Sept 2026).
    if st.session_state.get("refresh_token"):
        remaining = _seconds_until_expiry(st.session_state.get("access_token"))
        if remaining is None or remaining < _REFRESH_MARGIN_SECONDS:
            try:
                supabase = get_supabase()
                res = supabase.auth.refresh_session(st.session_state.refresh_token)
                if res and res.session:
                    st.session_state.access_token  = res.session.access_token
                    st.session_state.refresh_token = res.session.refresh_token
                    st.session_state.user          = res.user
            except Exception:
                # Only a session whose access token has actually run out is
                # over. If it is still valid, a failed refresh (e.g. another
                # rerun already rotated the token) must not log the user out.
                if remaining is None or remaining <= 0:
                    st.session_state.user          = None
                    st.session_state.access_token  = None
                    st.session_state.refresh_token = None


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


def login_ui():
    """The form card of the login page (login_page.py draws the page around
    it, D-127): a Log in / Sign up switch, then the form. Forgot password is
    a third state of the same switch, reached from the log-in form."""
    # S49: arriving from a free check or a website sign-up link (app.py
    # parks it in session state), the visitor is new — open on Sign up.
    funnel = st.session_state.get("funnel") or {}
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = (
            "Sign up" if (funnel.get("pending") or funnel.get("signup")) else "Log in")
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
        _login_form(funnel)
    elif st.session_state.get("signup_sent_to"):
        _check_inbox(st.session_state.signup_sent_to,
                     st.session_state.get("signup_plan"))
    else:
        _signup_form(funnel)


def _go(mode: str) -> None:
    st.session_state.auth_mode = mode
    st.rerun()


def _login_form(funnel: dict) -> None:
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
        st.session_state.user          = res.user
        st.session_state.access_token  = res.session.access_token
        st.session_state.refresh_token = res.session.refresh_token
        # S49: an existing account that just took a free check keeps that
        # result, unless it already has one.
        if funnel.get("pending") and not get_user_profile(res.user.id).get("pending_result"):
            save_pending_result(res.user.id, funnel["pending"])
        st.rerun()
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
    st.caption("Nothing after a few minutes? Look in your spam folder, or send it again.")
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
        st.caption("Nothing after a few minutes? Look in your spam folder.")
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


def start_password_recovery(token_hash: str) -> bool:
    """Logs in with the reset email's one-time token. True when it worked;
    the caller then shows set_new_password_ui()."""
    try:
        res = get_supabase().auth.verify_otp({"token_hash": token_hash, "type": "recovery"})
    except Exception as e:
        print(f"Password recovery link rejected: {e}")
        return False
    if not (res and res.session):
        return False
    st.session_state.user          = res.user
    st.session_state.access_token  = res.session.access_token
    st.session_state.refresh_token = res.session.refresh_token
    st.session_state.password_recovery = True
    return True


def set_new_password_ui() -> None:
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
    for key in ["user", "access_token", "refresh_token",
                "selected_client", "messages", "clients"]:
        if key in st.session_state:
            del st.session_state[key]
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
        return True, None
    except Exception as e:
        return False, str(e)
