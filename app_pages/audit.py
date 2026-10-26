import os
import streamlit as st
from auth import is_logged_in, get_user_id
from cached_reads import load_accessible_clients
from crawler import crawl, extract_domain
from checklist import run_checklist
from report import generate_pdf
from audit_view import render_results
from email_sender import extract_email_domain
from database import (
    upload_file, update_audit_path,
    save_audit,
    create_audit_subscription, list_audit_subscriptions, deactivate_audit_subscription,
)

RISK_COLORS = {"Green": "#0F6E56", "Amber": "#BA7517", "Red": "#993C1D"}

FREQUENCY_OPTIONS = {"Weekly": 7, "Monthly": 30, "Quarterly": 90}


# ── Page header ───────────────────────────────────────────────────────────────

st.title("Web Audit")
st.markdown(
    "Check a website against **GDPR, ePrivacy, Accessibility, Consumer Rights, NIS2, and the EU AI Act** "
    "in minutes."
)
st.divider()

logged_in = is_logged_in()

# ── Authenticated flow ────────────────────────────────────────────────────────
if logged_in:
    user_id = get_user_id()
    st.info("Your plan includes unlimited website audits. Each result is saved to your account.")

    # S44. Not cached (cached_reads.py), so this is always fresh — no
    # cache-clear needed after Subscribe/Unsubscribe below, just a rerun.
    subscriptions = list_audit_subscriptions(user_id)
    if subscriptions:
        with st.expander(f"🔁 Your recurring audits ({len(subscriptions)})"):
            _freq_label_by_days = {v: k for k, v in FREQUENCY_OPTIONS.items()}
            for sub in subscriptions:
                sc1, sc2, sc3 = st.columns([3, 2, 1])
                sc1.write(sub["site_domain"])
                sc2.caption(
                    f"{_freq_label_by_days.get(sub['frequency_days'], sub['frequency_days'])} · "
                    f"last run: {sub.get('last_run_at') or 'never'}"
                )
                if sc3.button("Unsubscribe", key=f"unsub_{sub['id']}"):
                    if deactivate_audit_subscription(sub["id"], user_id):
                        st.rerun()

    # Accessible, not just owned (S38) — a workspace member should be able
    # to link an audit to a client they've been given access to.
    clients = load_accessible_clients(user_id)
    client_options = {c["company_name"]: c for c in clients}

    # Picking a client fills the URL field with that client's website.
    # Runs as on_change, before the text_input below is drawn — setting a
    # widget's key after it has rendered raises in Streamlit. "No client",
    # or a client without a website, leaves whatever was typed.
    def _prefill_url_from_client():
        chosen = client_options.get(st.session_state.auth_client_select)
        if chosen and chosen.get("website_url"):
            st.session_state.auth_url = chosen["website_url"]

    selected_client_name = st.selectbox(
        "Link this audit to a client (optional)",
        options=["— No client —"] + list(client_options.keys()),
        key="auth_client_select",
        on_change=_prefill_url_from_client,
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
                    st.session_state.pop("auth_audit_result", None)
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
                        # S42: link the stored report to its audits row, so it
                        # can be found again (and deleted, S40) from the row.
                        if stored_path and audit_id:
                            update_audit_path(audit_id, stored_path)
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

                    # S44. Stored rather than rendered inline: a Subscribe
                    # click below is itself a widget interaction, which
                    # reruns this whole script from the top. On that rerun
                    # "Run audit" reads False again (it wasn't what was
                    # clicked), so this whole `else:` branch — including an
                    # inline Subscribe button — would never even execute,
                    # and the button it needs to see clicked would never be
                    # on the page to click. Session state survives that
                    # rerun; a local variable here would not.
                    st.session_state.auth_audit_result = {
                        "audit_result": audit_result,
                        "pdf_bytes": pdf_bytes,
                        "site_domain": site_domain,
                        "website_url": website_url.strip(),
                        "client_id": client_id,
                    }

    # ── Results + subscribe (S44), outside the button's own if-block so a
    # Subscribe click's rerun still finds them ──
    _result = st.session_state.get("auth_audit_result")
    if _result:
        st.success(
            f"Audit complete — {_result['audit_result'].risk_level} risk, "
            f"score {_result['audit_result'].score}/100"
        )
        render_results(_result["audit_result"], _result["pdf_bytes"], is_authenticated=True)

        with st.expander("🔁 Get this checked automatically"):
            st.caption(
                "Re-run this audit on a schedule and email the results to "
                f"{st.session_state.user.email}."
            )
            freq_label = st.selectbox(
                "How often", list(FREQUENCY_OPTIONS.keys()), index=1, key="sub_freq",
            )
            if st.button("Subscribe", key="btn_subscribe"):
                ok = create_audit_subscription(
                    user_id=user_id,
                    client_id=_result["client_id"],
                    website_url=_result["website_url"],
                    site_domain=_result["site_domain"],
                    email=st.session_state.user.email,
                    frequency_days=FREQUENCY_OPTIONS[freq_label],
                )
                if ok:
                    st.success(
                        f"Subscribed — {_result['site_domain']} will be "
                        f"checked {freq_label.lower()} and results emailed "
                        f"to you."
                    )
                    st.session_state.pop("auth_audit_result", None)
                    st.rerun()
                else:
                    st.error("Could not create the subscription.")

# ── Public flow ───────────────────────────────────────────────────────────────
# S49 (D-115): the free, no-login website check lives in the public app
# (quiz/quiz_app.py), beside the NIS2 quiz. The anonymous branch that was here
# could never run — app.py gates every page behind is_logged_in() (D-104) — and
# was removed rather than kept as a second copy to drift.
else:
    st.info("Log in to run website audits.")
