import os
import streamlit as st

# Must be first Streamlit call
st.set_page_config(page_title="COMPLAI — Free Website Audit", page_icon="⚖️", layout="centered")

st.title("COMPLAI ⚖️ — Free Website Compliance Audit")
st.write("Page is loading correctly.")

# Test imports one by one with error catching
try:
    from crawler import crawl, extract_domain
    st.success("✅ crawler imported")
except Exception as e:
    st.error(f"❌ crawler: {e}")

try:
    from checklist import run_checklist, OK, WARN, FAIL
    st.success("✅ checklist imported")
except Exception as e:
    st.error(f"❌ checklist: {e}")

try:
    from report import generate_pdf
    st.success("✅ report imported")
except Exception as e:
    st.error(f"❌ report: {e}")

try:
    from email_sender import send_audit_report, is_free_email, extract_email_domain
    st.success("✅ email_sender imported")
except Exception as e:
    st.error(f"❌ email_sender: {e}")

try:
    from auth import init_auth, is_logged_in, get_user_id
    init_auth()
    st.success("✅ auth imported")
except Exception as e:
    st.error(f"❌ auth: {e}")

try:
    from database import load_clients
    st.success("✅ database imported")
except Exception as e:
    st.error(f"❌ database: {e}")

st.info("If you see this, all imports are working.")
