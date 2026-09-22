import os
import streamlit as st
from auth import is_logged_in, get_user_id
from cached_reads import load_accessible_clients
from crawler import crawl, extract_domain
from checklist import run_checklist, OK, WARN, FAIL
from report import generate_pdf
from email_sender import send_audit_report, is_free_email, extract_email_domain
from database import upload_file, update_audit_path

RISK_COLORS = {"Green": "#0F6E56", "Amber": "#BA7517", "Red": "#993C1D"}
STATUS_EMOJI = {OK: "✅", WARN: "⚠️", FAIL: "❌"}

# S41. Before S43's domain-verification gate existed, the reuse block
# below was keyed entirely on attacker-supplied input — rotating the
# email's domain, or supplying someone else's, cost nothing. IP is a
# second, independent signal neither the domain-match nor the reuse
# check has. Env-var configurable rather than hardcoded, same convention
# as SUPERSEDED_RETENTION_YEARS in database.py.
AUDIT_IP_LIMIT = int(os.environ.get("AUDIT_IP_LIMIT", "3"))
AUDIT_IP_WINDOW_HOURS = int(os.environ.get("AUDIT_IP_WINDOW_HOURS", "24"))


def get_supabase_anon():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)


def domains_match(email_domain: str, site_domain: str) -> bool:
    """S43. True if the requester's email domain is the site's own domain,
    or the two are subdomain-related in either direction (bob@acme.com may
    audit acme.com or app.acme.com; bob@mail.acme.com may audit acme.com).

    This is the actual domain-verification control: a free audit is for
    auditing a site you have an email address at, not any site on the
    internet. No DNS/TXT-record challenge — an email domain match is a
    weaker proof of ownership than that, but it is real (you cannot type
    someone else's professional domain into your own inbox), costs nothing
    to check, and matches the bar every other input on this form already
    clears at (is_free_email, not a verified account).
    """
    email_domain = (email_domain or "").lower()
    site_domain = (site_domain or "").lower()
    if not email_domain or not site_domain:
        return False
    return (
        site_domain == email_domain
        or site_domain.endswith("." + email_domain)
        or email_domain.endswith("." + site_domain)
    )


def check_site_domain_used(site_domain: str) -> bool:
    """True if this exact site has already had a free anonymous audit.

    S43: keyed on the SITE's domain, not the requester's email domain.
    Before this, the block was keyed on the email's domain — which meant
    two different people at two different companies could each request a
    free audit of the same THIRD site, repeatedly, since nothing tied the
    "already used" check to what was actually being audited. Once
    domains_match() enforces that the requester's email is at the site's
    own domain, checking by site_domain is both the correct anti-abuse key
    and a real limit on reruns of one's own site (once, ever, same as
    before this fix — the mechanism is unchanged, only what it's keyed on).
    """
    try:
        from database import get_supabase_admin
        supabase = get_supabase_admin()
        res = supabase.table("audits") \
            .select("id") \
            .eq("site_domain", site_domain) \
            .is_("user_id", "null") \
            .execute()
        return len(res.data) > 0
    except Exception:
        return False


def check_ip_rate_limited(ip_address: str | None) -> bool:
    """True if this IP has already used up its anonymous-audit allowance
    for the current window.

    None/unknown IP fails OPEN — this check is additive to
    check_site_domain_used, not a replacement for it, so an IP this app
    could not determine should not block someone the domain check would
    otherwise have let through.
    """
    if not ip_address:
        return False
    try:
        from datetime import datetime, timedelta, timezone
        from database import get_supabase_admin
        since = (
            datetime.now(timezone.utc) - timedelta(hours=AUDIT_IP_WINDOW_HOURS)
        ).isoformat()
        res = (
            get_supabase_admin().table("audits")
            .select("id", count="exact")
            .eq("ip_address", ip_address)
            .is_("user_id", "null")
            .gte("created_at", since)
            .execute()
        )
        return (res.count or 0) >= AUDIT_IP_LIMIT
    except Exception:
        return False


def save_audit(email, email_domain, website_url, audit_result, user_id=None,
                client_id=None, ip_address=None, site_domain=None):
    try:
        from database import get_supabase_admin
        supabase = get_supabase_admin()
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
        if ip_address:
            record["ip_address"] = ip_address
        if site_domain:
            record["site_domain"] = site_domain
        res = supabase.table("audits").insert(record).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        st.warning(f"Could not save audit record: {e}")
        return None
        

def render_results(audit_result, pdf_bytes, is_authenticated=False):
    col1, col2, col3 = st.columns(3)
    col1.metric("Score", f"{audit_result.score}/100")
    col2.metric("Risk level", audit_result.risk_level)
    col3.metric("Checks run", len(audit_result.checks))

    c1, c2, c3 = st.columns(3)
    c1.success(f"✅ {audit_result.ok_count} Compliant")
    c2.warning(f"⚠️ {audit_result.warn_count} Need attention")
    c3.error(f"❌ {audit_result.fail_count} Missing")

    st.divider()

    groups = {}
    for check in audit_result.checks:
        groups.setdefault(check.regulation, []).append(check)

    for regulation, items in groups.items():
        ok = sum(1 for i in items if i.status == OK)
        with st.expander(f"**{regulation}** — {ok}/{len(items)} compliant", expanded=True):
            for item in items:
                emoji = STATUS_EMOJI[item.status]
                st.markdown(f"{emoji} **{item.id} — {item.label}**")
                st.caption(item.detail)

    st.divider()

    if is_authenticated:
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"RECOSA_Audit_{audit_result.url.replace('https://','').replace('http://','')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    else:
        st.markdown(
            """
            <div style="background:#1B2A4A;padding:24px;border-radius:8px;text-align:center;margin-top:8px;">
                <h3 style="color:white;margin:0 0 8px;">Ready to fix these gaps?</h3>
                <p style="color:#ccc;font-size:14px;margin:0 0 16px;">
                    RECOSA shows you exactly how to remediate each issue, generates your privacy policy,
                    cookie policy, and T&Cs, and monitors your compliance continuously.
                </p>
                <a href="/" style="display:inline-block;background:#0F6E56;color:white;
                    padding:12px 32px;border-radius:6px;text-decoration:none;
                    font-weight:bold;font-size:15px;">
                    Fix it now — start free trial →
                </a>
                <p style="color:#aaa;font-size:12px;margin-top:10px;">No credit card required · 15-day free trial</p>
            </div>
            """,
            unsafe_allow_html=True
        )


# ── Page header ───────────────────────────────────────────────────────────────

st.title("RECOSA — Free Website Compliance Audit")
st.markdown(
    "Check your website against **GDPR, ePrivacy, Accessibility, Consumer Rights, NIS2, and the EU AI Act** "
    "in minutes. Free, no registration required."
)
st.divider()

logged_in = is_logged_in()

# ── Authenticated flow ────────────────────────────────────────────────────────
if logged_in:
    user_id = get_user_id()
    st.info("👤 Running as logged-in user — unlimited audits, results saved to your account.")

    # Accessible, not just owned (S38) — a workspace member should be able
    # to link an audit to a client they've been given access to.
    clients = load_accessible_clients(user_id)
    client_options = {c["company_name"]: c for c in clients}

    selected_client_name = st.selectbox(
        "Link this audit to a client (optional)",
        options=["— No client —"] + list(client_options.keys()),
        key="auth_client_select"
    )
    selected_client = client_options.get(selected_client_name)

    website_url = st.text_input(
        "Website URL to audit",
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
                    # S43: this was previously named email_domain despite
                    # holding the SITE's domain (extract_domain(website_url),
                    # not the user's actual email domain) — harmless here
                    # since the authenticated flow isn't domain-gated, but
                    # it stored the wrong value under audits.email_domain.
                    # Named and stored correctly now that the column split
                    # exists to hold each one properly.
                    site_domain = extract_domain(website_url)
                    email_domain = extract_email_domain(st.session_state.user.email)
                    client_id = selected_client["id"] if selected_client else None
                    audit_id = save_audit(
                        email=st.session_state.user.email,
                        email_domain=email_domain,
                        website_url=website_url,
                        audit_result=audit_result,
                        user_id=user_id,
                        client_id=client_id,
                        ip_address=st.context.ip_address,
                        site_domain=site_domain,
                    )
                    # Upload PDF to storage
                    try:
                        from datetime import datetime
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_domain = site_domain.replace(".", "_")
                        pdf_storage_path = f"{user_id}/{safe_domain}/{ts}_audit.pdf"
                        stored_path = upload_file("audit-reports", pdf_storage_path, pdf_bytes, "application/pdf")
                    except Exception:
                        pass

                    # Audit trail (S21) — only logged when linked to a client
                    if client_id and audit_id:
                        from database import log_audit_event
                        log_audit_event(
                            company_id=client_id,
                            user_id=user_id,
                            event_type="audit_run",
                            resource_id=audit_id,
                            summary=f"Audited {website_url.strip()}",
                            metadata={"domain": site_domain,
                                      "score": audit_result.score,
                                      "risk_level": audit_result.risk_level,
                                      "fail_count": audit_result.fail_count},
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
        if not website_url.strip() or not email.strip():
            st.error("Please enter both your website URL and email address.")
        elif "@" not in email or "." not in email.split("@")[-1]:
            st.error("Please enter a valid email address.")
        elif is_free_email(email.strip()):
            st.error("Please use your professional email address (not Gmail, Hotmail, etc.).")
        else:
            email_domain = extract_email_domain(email.strip())
            site_domain = extract_domain(website_url.strip())
            client_ip = st.context.ip_address
            if not domains_match(email_domain, site_domain):
                # S43. The domain-verification gate: a free audit is for
                # auditing a site you have an email address at, not any
                # site on the internet. Checked before any DB query below —
                # cheapest to reject, and the reuse check's meaning depends
                # on this having already passed.
                st.warning(
                    f"Please use an email address at **{site_domain}** to "
                    "audit this site — e.g. you@" + site_domain + ". "
                    "This free tool is for auditing your own website."
                )
            elif check_site_domain_used(site_domain):
                st.warning(
                    f"A free audit has already been requested for **{site_domain}**. "
                    "Subscribe to RECOSA to run fresh audits and access remediation guidance."
                )
                st.markdown(
                    '<a href="/" style="display:inline-block;background:#0F6E56;color:white;'
                    'padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">'
                    'Start free trial →</a>',
                    unsafe_allow_html=True
                )
            elif check_ip_rate_limited(client_ip):
                # S41. Independent of the domain check above — this is what
                # stops rotating the email's domain from being a free pass.
                st.warning(
                    "You've reached the limit of free audits from this "
                    "connection. Subscribe to RECOSA to run unlimited audits."
                )
                st.markdown(
                    '<a href="/" style="display:inline-block;background:#0F6E56;color:white;'
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
                        save_audit(
                            email=email.strip(),
                            email_domain=email_domain,
                            website_url=website_url.strip(),
                            audit_result=audit_result,
                            ip_address=client_ip,
                            site_domain=site_domain,
                        )
                        # Upload PDF to storage
                        try:
                            from datetime import datetime
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            safe_domain = site_domain.replace(".", "_")
                            pdf_storage_path = f"{safe_domain}/{ts}_audit.pdf"
                            upload_file("audit-reports", pdf_storage_path, pdf_bytes, "application/pdf")
                        except Exception:
                            pass
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

                        render_results(audit_result, pdf_bytes, is_authenticated=False)

    st.divider()
    st.caption("Already have an account? [Log in](/chat) to run unlimited audits and access remediation guidance.")
