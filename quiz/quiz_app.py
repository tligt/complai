"""
quiz/quiz_app.py — the public free checks: the NIS2 Quick Check (S45) and
the GDPR website check (S49). Deployed as its own Streamlit Cloud app with
this file as the entry point, at recosa-checklist.streamlit.app.

Lives in its own directory, not the repo root, and that is load-bearing, not
tidiness. Streamlit's legacy multipage auto-discovery lists any `pages/`
directory sitting next to whichever script it runs as its own navigation —
confirmed live, running this file from the repo root put every gated page
(documents, gap, obligations, ...) in the public quiz's sidebar, each one
directly executable with no is_logged_in() check. Putting this script in a
directory with no `pages/` sibling removes that discovery path entirely.

A SEPARATE entry point, not a page inside app.py: app.py gates every page
behind is_logged_in() before st.navigation even builds (D-104), and a public
lead magnet does not get a hole punched in that boundary (D-107).

THE FUNNEL (S49, D-115). Free to check; the full result is the reward for an
email (sent by email) or an account (shown in the app); everything else in
the app sits behind the trial.
  - Score and band, or the website's score and counts per regulation: free.
  - The breakdown / findings: locked here. Sent in full by email, or shown
    after signup — the CTA carries the answers or the site, never the email.

WHAT THIS APP CAN WRITE. Only through three SECURITY DEFINER functions, with
the anon key (migration_s49_funnel.sql): submit_lead, start_website_check,
record_funnel_event. No service-role key here, no table access, no reads.
The Brevo key sends the result emails.

Secrets (Streamlit Cloud, top level): APP_BASE_URL, SUPABASE_URL,
SUPABASE_KEY (the anon key), BREVO_API_KEY, BREVO_FROM_EMAIL, BREVO_FROM_NAME,
optionally PRIVACY_POLICY_URL.

NOT A COMPLIANCE AUDIT. The quiz questions and weights in funnel.py are draft
marketing copy, not reviewed legal text — reviewed before launch (D-115).
"""

import os
import sys
from pathlib import Path

# The shared modules (funnel, crawler, checklist, report, email_sender) live
# at the repo root, one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    # Local runs only; python-dotenv is not in this app's requirements, and
    # Streamlit Cloud exposes top-level secrets as environment variables.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
import streamlit as st

import funnel
from funnel_ui import render_quiz_form, render_quiz_score, render_quiz_breakdown

st.set_page_config(
    page_title="RECOSA — Free compliance checks",
    page_icon="🛡️",
    layout="centered",
)

APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "http://localhost:8501").rstrip("/")
PRIVACY_POLICY_URL = os.environ.get("PRIVACY_POLICY_URL") or "https://recosa.eu/privacy-policy"


# ── Database: three functions, anon key ───────────────────────────────────

def _rpc(fn: str, params: dict):
    """Call one of the funnel's SECURITY DEFINER functions. Returns its result,
    or None if the database is not configured or the call failed."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        r = requests.post(
            f"{url.rstrip('/')}/rest/v1/rpc/{fn}",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json=params, timeout=10,
        )
        if r.status_code >= 300:
            print(f"rpc {fn} failed: {r.status_code} {r.text[:200]}")
            return None
        return r.json() if r.text else True
    except Exception as e:
        print(f"rpc {fn} failed: {e}")
        return None


def _submit_lead(tool, email, *, answers=None, site=None, score=None, marketing=False):
    return _rpc("submit_lead", {
        "p_tool": tool, "p_email": email.strip(),
        "p_answers": funnel.encode_answers(answers) if answers else None,
        "p_site_domain": site, "p_score": score,
        "p_marketing_consent": bool(marketing),
        "p_consent_version": funnel.CONSENT_VERSION,
        "p_source": st.query_params.get("utm_source") or "direct",
        "p_ip": st.context.ip_address,
    })


_LEAD_REFUSED = {
    "invalid": "Please enter a valid email address.",
    "rate_limited": "A result was already sent to this address recently. "
                    "Check your inbox, or try again tomorrow.",
    "already_sent": "The full report for this site has already been sent. "
                    "Create a free account to see it in RECOSA.",
    None: "We couldn't record your request just now. Please try again later.",
}


def _email_form(key: str, button: str) -> tuple[str, bool] | None:
    """The optional email step. Returns (email, marketing_consent) when
    submitted with an address, else None."""
    with st.form(key, border=True):
        st.markdown("**📧 Email me the full result**")
        email = st.text_input("Your email", placeholder="you@company.com",
                              key=f"{key}_email", label_visibility="collapsed")
        marketing = st.checkbox(funnel.CONSENT_TEXT, value=False, key=f"{key}_mkt")
        st.caption(
            f"We use your email to send this result. Updates only if you tick the box. "
            f"[Privacy policy]({PRIVACY_POLICY_URL})"
        )
        sent = st.form_submit_button(button)
    if not sent:
        return None
    if "@" not in email or "." not in email.split("@")[-1]:
        st.error("Please enter a valid email address.")
        return None
    return email.strip(), marketing


def _signup_cta(url: str) -> None:
    st.link_button("See your full result in RECOSA — create a free account →",
                   url, type="primary", use_container_width=True)
    st.caption("Free account, no card. A 14-day trial unlocks the full assessment.")


# ── Page ──────────────────────────────────────────────────────────────────

st.title("🛡️ RECOSA free compliance checks")
st.caption("Two minutes each. A first read on where you stand — not a compliance audit.")

_tabs = ["🛡️ NIS2 Quick Check", "🌐 GDPR website check"]
tab_quiz, tab_site = st.tabs(
    _tabs, default=_tabs[1] if st.query_params.get("tool") == "website" else _tabs[0],
)

# ── NIS2 Quick Check ──────────────────────────────────────────────────────
with tab_quiz:
    st.caption(
        "10 questions on NIS2's core security measures (Art. 21). "
        "Your score is shown straight away."
    )
    answers = render_quiz_form("nis2_quiz")
    if answers is not None:
        st.session_state.quiz_answers = answers
        _rpc("record_funnel_event", {"p_event": "quiz_completed",
                                     "p_tool": funnel.TOOL_QUIZ, "p_source": None})

    answers = st.session_state.get("quiz_answers")
    if answers:
        st.divider()
        render_quiz_score(answers)
        render_quiz_breakdown(answers, locked=True)
        st.write("")

        submitted = _email_form("quiz_email", "Send my full result")
        if submitted:
            email, marketing = submitted
            status = _submit_lead(funnel.TOOL_QUIZ, email, answers=answers,
                                  score=funnel.score(answers), marketing=marketing)
            if status == "ok":
                try:
                    from email_sender import send_quiz_result
                    ok = send_quiz_result(email, answers, funnel.signup_url(
                        APP_BASE_URL, funnel.TOOL_QUIZ, answers=answers))
                except Exception as e:
                    print(f"quiz email failed: {e}")
                    ok = False
                if ok:
                    st.success(f"Sent to **{email}** — check your inbox.")
                else:
                    st.warning("We couldn't send the email just now. "
                               "You can see your full result by creating a free account below.")
            else:
                st.warning(_LEAD_REFUSED.get(status, _LEAD_REFUSED[None]))

        _signup_cta(funnel.signup_url(APP_BASE_URL, funnel.TOOL_QUIZ, answers=answers))

# ── GDPR website check ────────────────────────────────────────────────────
with tab_site:
    st.caption(
        "We read your homepage and its privacy, cookie, terms and contact pages, "
        "and check them against GDPR, ePrivacy, accessibility and consumer rules. "
        "About 30 seconds."
    )
    with st.form("site_check"):
        url = st.text_input("Website", placeholder="https://yourcompany.com")
        run = st.form_submit_button("Check my website", type="primary")

    if run:
        from crawler import crawl, extract_domain, normalise_url
        if not url.strip():
            st.error("Please enter a website address.")
        elif _rpc("start_website_check", {"p_ip": st.context.ip_address}) is False:
            # Only an explicit refusal blocks; an unconfigured or failed call
            # fails open, as S41's check does.
            st.warning("You've reached today's limit of free website checks from "
                       "this connection. Create a free account to keep checking.")
            _signup_cta(funnel.signup_url(APP_BASE_URL, funnel.TOOL_WEBSITE))
        else:
            with st.spinner("Reading your website and running the checks…"):
                result = crawl(url.strip())
            if result.error:
                st.error(result.error)
            else:
                from checklist import run_checklist
                st.session_state.site_result = {
                    "audit": run_checklist(result),
                    "domain": extract_domain(normalise_url(url.strip())),
                    "url": normalise_url(url.strip()),
                }

    check = st.session_state.get("site_result")
    if check:
        from audit_view import render_results
        st.divider()
        st.subheader(f"Your result for {check['domain']}")
        render_results(check["audit"], locked=True)
        st.write("")

        submitted = _email_form("site_email", "Send my full report")
        if submitted:
            email, marketing = submitted
            from email_sender import is_free_email
            if is_free_email(email):
                st.error("Please use your work email address, at your company's own domain.")
            elif not funnel.domains_match(email, check["domain"]):
                st.warning(
                    f"The full report goes to an address at **{check['domain']}** — "
                    f"e.g. you@{check['domain']}. It is for checking your own website."
                )
            else:
                audit = check["audit"]
                status = _submit_lead(funnel.TOOL_WEBSITE, email, site=check["domain"],
                                      score=audit.score, marketing=marketing)
                if status == "ok":
                    try:
                        from report import generate_pdf
                        from email_sender import send_audit_report
                        ok = send_audit_report(
                            to_email=email, website_url=check["url"],
                            pdf_bytes=generate_pdf(audit), score=audit.score,
                            risk_level=audit.risk_level, ok_count=audit.ok_count,
                            warn_count=audit.warn_count, fail_count=audit.fail_count,
                            cta_url=funnel.signup_url(APP_BASE_URL, funnel.TOOL_WEBSITE,
                                                      site=check["domain"]),
                        )
                    except Exception as e:
                        print(f"website report email failed: {e}")
                        ok = False
                    if ok:
                        st.success(f"Report sent to **{email}** — check your inbox.")
                    else:
                        st.warning("We couldn't send the report just now. "
                                   "You can see it by creating a free account below.")
                elif status == "domain":
                    st.warning(f"The full report goes to an address at **{check['domain']}**.")
                else:
                    st.warning(_LEAD_REFUSED.get(status, _LEAD_REFUSED[None]))

        _signup_cta(funnel.signup_url(APP_BASE_URL, funnel.TOOL_WEBSITE, site=check["domain"]))
