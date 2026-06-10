import os
import streamlit as st
from supabase import create_client, Client


def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in secrets.")
    return create_client(url, key)


def init_auth():
    """Initialise auth session state."""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "access_token" not in st.session_state:
        st.session_state.access_token = None


def is_logged_in() -> bool:
    return st.session_state.get("user") is not None


def login_ui():
    """Render the login / signup screen. Returns True if just logged in."""
    st.title("COMPLAI ⚖️")
    st.caption("AI-powered compliance assistant for GDPR, NIS2, and the EU AI Act.")
    st.divider()

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Log in", type="primary", use_container_width=True, key="btn_login"):
            if email and password:
                try:
                    supabase = get_supabase()
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.session_state.access_token = res.session.access_token
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")
            else:
                st.warning("Please enter your email and password.")

    with tab_signup:
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password (min. 8 characters)", type="password", key="signup_password")
        new_password2 = st.text_input("Confirm password", type="password", key="signup_password2")
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
                        st.success("Account created. Please check your email to confirm, then log in.")
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
    for key in ["user", "access_token", "selected_client", "messages", "clients"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def get_user_id() -> str:
    """Return the current user's UUID."""
    return st.session_state.user.id
