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
PLAN_INFO = {
    "starter": ("€49/month", "For micro and small companies: GDPR, NIS2 and the "
                "EU AI Act, one user, the core documents."),
    "professional": ("€149/month", "For growing SMEs: several users, unlimited "
                     "website audits, the full document library."),
}
ENTERPRISE_URL = "https://www.recosa.eu/contact"


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
    """
    Render a clean RECOSA login/signup form.
    Called from app.py after centering CSS is applied.
    No title or branding here — app.py handles that.
    """
    # S49: arriving from a free check (app.py parks it in session state),
    # the visitor is new — open on Sign up and say why.
    funnel = st.session_state.get("funnel") or {}
    tabs = ["Log in", "Sign up"]
    tab_login, tab_signup = st.tabs(
        tabs, default=tabs[1] if (funnel.get("pending") or funnel.get("signup")) else tabs[0],
    )

    with tab_login:
        email    = st.text_input("Email", key="login_email", placeholder="you@company.com")
        password = st.text_input("Password", type="password", key="login_password",
                                  placeholder="Your password")
        if st.button("Log in", type="primary", use_container_width=True, key="btn_login"):
            if email and password:
                try:
                    supabase = get_supabase()
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user          = res.user
                    st.session_state.access_token  = res.session.access_token
                    st.session_state.refresh_token = res.session.refresh_token
                    # S49: an existing account that just took a free check
                    # keeps that result, unless it already has one.
                    if funnel.get("pending") and not get_user_profile(res.user.id).get("pending_result"):
                        save_pending_result(res.user.id, funnel["pending"])
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")
            else:
                st.warning("Please enter your email and password.")

    with tab_signup:
        if st.session_state.get("signup_sent_to"):
            _check_inbox(st.session_state.signup_sent_to,
                         st.session_state.get("signup_plan"))
        else:
            _signup_form(funnel)


def _signup_form(funnel: dict) -> None:
    # A free check result rides along: that account starts free, its result
    # first (S49). Everyone else picks a plan, and its trial starts now
    # (D-126) — the website's buttons say "Free trial".
    plan = None
    if funnel.get("pending"):
        st.info("Create your free account to see your full result.")
    else:
        default = funnel.get("plan") or "professional"
        plan = st.radio(
            "Your plan", SIGNUP_PLANS, index=SIGNUP_PLANS.index(default),
            format_func=lambda p: f"{SUBSCRIPTION_TIERS[p]} — {PLAN_INFO[p][0]}",
            horizontal=True, key="signup_plan_pick",
        )
        st.caption(PLAN_INFO[plan][1] + f" **{TRIAL_DAYS}-day free trial, no card needed.** "
                   f"Larger organisation? [Contact us]({ENTERPRISE_URL}) about Enterprise.")
    new_email     = st.text_input("Email", key="signup_email", placeholder="you@company.com")
    new_password  = st.text_input("Password (min. 8 characters)", type="password",
                                   key="signup_password", placeholder="At least 8 characters")
    new_password2 = st.text_input("Confirm password", type="password",
                                   key="signup_password2", placeholder="Repeat password")
    label = f"Start my {TRIAL_DAYS}-day free trial" if plan else "Create account"
    if not st.button(label, type="primary", use_container_width=True, key="btn_signup"):
        return
    new_email = (new_email or "").strip()
    if not new_email or not new_password:
        st.warning("Please fill in all fields.")
        return
    if new_password != new_password2:
        st.error("Passwords do not match.")
        return
    if len(new_password) < 8:
        st.error("Password must be at least 8 characters.")
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
    with st.container(border=True):
        st.markdown("### 📧 Check your inbox")
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
            for k in ("signup_sent_to", "signup_plan", "signup_email",
                      "signup_password", "signup_password2"):
                st.session_state.pop(k, None)
            st.rerun()


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
