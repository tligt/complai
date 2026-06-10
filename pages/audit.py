import os
import streamlit as st
from auth import init_auth, is_logged_in, get_user_id
from database import load_clients
from crawler import crawl, extract_domain
from checklist import run_checklist, OK, WARN, FAIL, STATUS_LABELS
from report import generate_pdf
from email_sender import send_audit_report, is_free_email, extract_email_domain

st.set_page_config(page_title="COMPLAI — Free Website Audit", page_icon="⚖️", layout="centered")

# ── Init auth (needed to detect if user is logged in) ────────────────────────
init_auth()

RISK_COLORS = {"Green": "#0F6E56", "Amber": "#BA7517", "Red": "#993C1D"}
STATUS_EMOJI = {OK: "✅", WARN: "⚠️", FAIL: "❌"}


def get_supabase_anon():
    """Get Supabase client without auth token — for public audit table."""
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)


def check_email_domain_used(email_domain: str) -> bool:
    """Check if this email domain has already had a free audit."""
    try:
        supabase = get_supabase_anon()
        res = supabase.table("audits") \
            .select("id") \
            .eq("email_domain", email_domain) \
            .is_("user_id", "null") \
            .execute()
        return len(res.data) > 0
    except Exception:
        return False


def save_audit(email: str, email_domain: str, website_url: str, audit_result, user_id=None, client_id=None):
    """Save audit record to Supabase."""
    try:
        supabase = get_supabase_anon()
        record = {
            "email": email,
            "email_domain": email_domain,
            "website_url": website_url,
            "risk_level": audit_result.risk_level,
            "report_data": {
                "score": audit_result.score,
                "ok_count": audit_result.ok_count,
                "warn_count": audit_result.warn_count,
                "fail_count": audit_result.fail_count,
            }
        }
        if user_id:
            record["user_id"] = user_id
        if client_id:
            record["client_id"] = client_id
        supabase.table("audits").insert(record).execute()
    except Exception as e:
        st.warning(f"Could not save audit record: {e}")


def render_results(audit_result, pdf_bytes, is_authenticated=False):
    """Render the audit results on screen."""
    risk_color = RISK_COLORS.get(audit_result.risk_level, "#333")

    # Score header
    col1, col2, col3 = st.columns(3)
    col1.metric("Score", f"{audit_result.score}/100")
    col2.metric("Risk level", audit_result.risk_level)
    col3.metric("Checks run", len(audit_result.checks))

    # Summary stats
    c1, c2, c3 = st.columns(3)
    c1.success(f"✅ {audit_result.ok_count} Compliant")
    c2.warning(f"⚠️ {audit_result.warn_count} Need attention")
    c3.error(f"❌ {audit_result.fail_count} Missing")

    st.divider()

    # Checklist by regulation
    groups = {}
    for check in audit_result.checks:
        groups.setdefault(check.regulation, []).append(check)

    for regulation, items in groups.items():
        with st.expander(f"**{regulation}** — {sum(1 for i in items if i.status==OK)}/{len(items)} compliant", expanded=True):
            for item in items:
                emoji = STATUS_EMOJI[item.status]
                st.markdown(f"{emoji} **{item.id} — {item.label}**")
                st.caption(f"{item.detail}")

    st.divider()

    # CTA — different for authenticated vs public users
    if is_authenticated:
        # Download PDF directly
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"COMPLAI_Audit_{audit_result.url.replace('https://','').replace('http://','')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    else:
        # Fix it now CTA
        st.markdown(
            f"""
            <div style="background:#1B2A4A;padding:24px;border-radius:8px;text-align:center;margin-top:8px;">
                <h3 style="color:white;margin:0 0 8px;">Ready to fix these gaps?</h3>
                <p style="color:#ccc;font-size:14px;margin:0 0 16px;">
                    COMPLAI shows you exactly how to remediate each issue, generates your privacy policy,
                    cookie policy, and T&Cs, and monitors your compliance continuously.
                </p>
                <a href="/app" style="display:inline-block;background:#0F6E56;color:white;
                    padding:12px 32px;border-radius:6px;text-decoration:none;
                    font-weight:bold;font-size:15px;">
                    Fix it now — start free trial →
                </a>
                <p style="color:#aaa;font-size:12px;margin-top:10px;">No credit card required · 15-day free trial</p>
            </div>
            """,
            unsafe_allow_html=True
        )


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("COMPLAI ⚖️ — Free Website Compliance Audit")
st.markdown(
    "Check your website against **GDPR, ePrivacy, Accessibility, Consumer Rights, NIS2, and the EU AI Act** "
    "in minutes. Free, no registration required."
)
st.divider()

logged_in = is_logged_in()

# ── Authenticated flow ────────────────────────────────────────────────────────
if logged_in:
    user_id = get_user_id()
    st.info(f"👤 Running as logged-in user — unlimited audits, results saved to your client profiles.")

    clients = load_clients(user_id)
    client_options = {c["company_name"]: c for c in clients}

    selected_client_name = st.selectbox(
        "Link this audit to a client (optional)",
        options=["— No client —"] + list(client_options.keys()),
        key="auth_client_select"
    )
    selected_client = client_options.get(selected_client_name)

    # Pre-fill URL from client if available
    default_url = ""
    if selected_client:
        default_url = selected_client.get("website_url", "")

    website_url = st.text_input(
        "Website URL to audit",
        value=default_url,
        placeholder="https://yourcompany.com",
        key="auth_url"
    )

    if st.button("🔍 Run audit", type="primary", use_container_width=True, key="btn_auth_audit"):
        if not website_url.strip():
            st.error("Please enter a website URL.")
        else:
            with st.spinner("Crawling website and running compliance checks..."):
                crawl_result = crawl(website_url.strip())
                if crawl_result.error:
                    st.error(crawl_result.error)
                else:
                    audit_result = run_checklist(crawl_result)
                    pdf_bytes = generate_pdf(audit_result)

                    # Save to Supabase
                    email_domain = extract_domain(website_url)
                    client_id = selected_client["id"] if selected_client else None
                    save_audit(
                        email=st.session_state.user.email,
                        email_domain=email_domain,
                        website_url=website_url,
                        audit_result=audit_result,
                        user_id=user_id,
                        client_id=client_id,
                    )

                    st.success(f"Audit complete — {audit_result.risk_level} risk, score {audit_result.score}/100")
                    render_results(audit_result, pdf_bytes, is_authenticated=True)

# ── Public flow ───────────────────────────────────────────────────────────────
else:
    st.markdown("**Enter your website URL and professional email to receive your free report.**")

    col1, col2 = st.columns(2)
    website_url = col1.text_input(
        "Your website URL",
        placeholder="https://yourcompany.com",
        key="pub_url"
    )
    email = col2.text_input(
        "Your professional email",
        placeholder="you@yourcompany.com",
        key="pub_email"
    )

    if st.button("🔍 Get my free audit", type="primary", use_container_width=True, key="btn_pub_audit"):
        # Validation
        if not website_url.strip() or not email.strip():
            st.error("Please enter both your website URL and email address.")
        elif "@" not in email or "." not in email.split("@")[-1]:
            st.error("Please enter a valid email address.")
        elif is_free_email(email.strip()):
            st.error("Please use your professional email address (not Gmail, Hotmail, etc.).")
        else:
            email_domain = extract_email_domain(email.strip())

            # Check if already audited
            if check_email_domain_used(email_domain):
                st.warning(
                    f"A free audit has already been requested for **{email_domain}**. "
                    "Subscribe to COMPLAI to run fresh audits and access remediation guidance."
                )
                st.markdown(
                    '<a href="/app" style="display:inline-block;background:#0F6E56;color:white;'
                    'padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">'
                    'Start free trial →</a>',
                    unsafe_allow_html=True
                )
            else:
                with st.spinner("Crawling your website and running compliance checks — this takes about 30 seconds..."):
                    crawl_result = crawl(website_url.strip())

                    if crawl_result.error:
                        st.error(crawl_result.error)
                    else:
                        audit_result = run_checklist(crawl_result)
                        pdf_bytes = generate_pdf(audit_result)

                        # Save audit record
                        save_audit(
                            email=email.strip(),
                            email_domain=email_domain,
                            website_url=website_url.strip(),
                            audit_result=audit_result,
                        )

                        # Send email
                        try:
                            sent = send_audit_report(
                                to_email=email.strip(),
                                website_url=website_url.strip(),
                                pdf_bytes=pdf_bytes,
                                score=audit_result.score,
                                risk_level=audit_result.risk_level,
                                ok_count=audit_result.ok_count,
                                warn_count=audit_result.warn_count,
                                fail_count=audit_result.fail_count,
                            )
                            if sent:
                                st.success(f"✅ Report sent to **{email.strip()}** — check your inbox!")
                            else:
                                st.warning("Audit complete but email delivery failed. Your results are below.")
                        except Exception as e:
                            st.warning(f"Audit complete but email could not be sent: {e}")

                        # Show results on screen
                        render_results(audit_result, pdf_bytes, is_authenticated=False)

    st.divider()
    st.caption(
        "Already have an account? [Log in](/app) to run unlimited audits and access remediation guidance."
    )
