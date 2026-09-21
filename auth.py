import os
import streamlit as st
from supabase import create_client, Client
from database import SUBSCRIPTION_TIERS, create_user_profile


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

    # Refresh session on every load to keep user logged in across refreshes
    # Supabase refresh tokens are long-lived (weeks) so this survives page refreshes
    if st.session_state.get("refresh_token"):
        try:
            supabase = get_supabase()
            res = supabase.auth.refresh_session(st.session_state.refresh_token)
            if res and res.session:
                st.session_state.access_token  = res.session.access_token
                st.session_state.refresh_token = res.session.refresh_token
                st.session_state.user          = res.user
        except Exception:
            # Token expired or invalid — clear session
            st.session_state.user          = None
            st.session_state.access_token  = None
            st.session_state.refresh_token = None


def is_logged_in() -> bool:
    return st.session_state.get("user") is not None


def login_ui():
    """
    Render a clean RECOSA login/signup form.
    Called from app.py after centering CSS is applied.
    No title or branding here — app.py handles that.
    """
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

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
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")
            else:
                st.warning("Please enter your email and password.")

    with tab_signup:
        new_email     = st.text_input("Email", key="signup_email", placeholder="you@company.com")
        new_password  = st.text_input("Password (min. 8 characters)", type="password",
                                       key="signup_password", placeholder="At least 8 characters")
        new_password2 = st.text_input("Confirm password", type="password",
                                       key="signup_password2", placeholder="Repeat password")
        # S37. Professional / Advisory only — the two tiers with real
        # behavioural difference today (D-90). Starter/Enterprise from the
        # commercial model stay out until S45/S46 give them one.
        new_tier = st.radio(
            "Plan", options=["professional", "advisory"],
            format_func=lambda t: SUBSCRIPTION_TIERS[t],
            captions=["Manage one client.",
                      "Manage more than one client — for consultants and advisors."],
            key="signup_tier", label_visibility="collapsed",
        )
        if st.button("Create account", type="primary", use_container_width=True, key="btn_signup"):
            if not new_email or not new_password:
                st.warning("Please fill in all fields.")
            elif new_password != new_password2:
                st.error("Passwords do not match.")
            elif len(new_password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                try:
                    supabase = get_supabase()
                    res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                    if res.user:
                        # S37: the only place a profiles row is ever created.
                        # res.user.id exists immediately, whether or not
                        # email confirmation is required.
                        create_user_profile(res.user.id, new_email, new_tier)
                        st.success("Account created — check your email to confirm, then log in.")
                    else:
                        st.error("Sign up failed. Please try again.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")


def logout():
    """Clear session and log out."""
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()
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
