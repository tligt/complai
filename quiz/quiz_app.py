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

THE FUNNEL (S49 D-115, part 2 D-119). Free to check; one form for the full
result: it creates the free account, and the result is emailed once the
address is confirmed (and shown in the app at first login). Everything else
in the app sits behind the trial.
  - Score and band, or the website's score and counts per regulation: free.
  - The breakdown / findings: locked here until the account is confirmed.
  - The website report only for the visitor's own site (S43): an address at
    its domain, or the site proven theirs after signup (funnel_delivery).

WHAT THIS APP CAN WRITE. With the anon key only: Supabase sign-up (the new
account, its free check in user metadata) and two SECURITY DEFINER functions
(migration_s49_funnel.sql): start_website_check, record_funnel_event. No
service-role key here, no table access, no reads. It sends no email itself:
the result goes out once the address is confirmed (funnel_delivery.py).

Secrets (Streamlit Cloud, top level): APP_BASE_URL, SUPABASE_URL,
SUPABASE_KEY (the anon key), optionally PRIVACY_POLICY_URL. The BREVO_*
secrets are no longer used here since D-119 and can be removed.

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


def _signup(email: str, password: str, pending: dict, marketing: bool) -> tuple[bool, str]:
    """S49 part 2 (D-119). Create the free account with the anon key, carrying
    the free check on the account itself (user metadata) — the client app
    and monitor_funnel.py pick it up from there. (ok, message)."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return False, "Sign-up is not available just now. Please try again later."
    try:
        r = requests.post(
            f"{url.rstrip('/')}/auth/v1/signup",
            params={"redirect_to": APP_BASE_URL + "/"},
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"email": email, "password": password, "data": {
                "recosa_pending": pending,
                "recosa_source": pending["tool"],
                "recosa_marketing": bool(marketing),
                "recosa_consent_version": funnel.CONSENT_VERSION if marketing else None,
            }},
            timeout=15,
        )
    except Exception as e:
        print(f"signup failed: {e}")
        return False, "We couldn't create your account just now. Please try again later."
    if r.status_code == 429:
        return False, "Too many sign-ups just now. Please try again in a few minutes."
    if r.status_code >= 300:
        print(f"signup refused: {r.status_code} {r.text[:200]}")
        msg = (r.json().get("msg") or r.json().get("error_description") or "") if r.text else ""
        return False, f"We couldn't create your account: {msg or 'please check your details'}."
    # An address that already has an account gets the same answer as a new
    # one (Supabase does not say which, so the form cannot be used to find
    # out who has an account).
    return True, ""


def _account_form(key: str, pending: dict, note: str = "") -> None:
    """The one step: complete the form, get the full report in the app and as
    a PDF by email once the address is confirmed."""
    if st.session_state.get(f"{key}_done"):
        st.success(st.session_state[f"{key}_done"])
        return
    with st.form(key, border=True):
        st.markdown("**Complete the form below and you'll get access to the full report, "
                    "including a PDF version sent to you.**" if pending["tool"] == funnel.TOOL_WEBSITE
                    else "**Complete the form below and you'll get access to your full result, "
                         "also sent to you by email.**")
        if note:
            st.caption(note)
        email = st.text_input("Work email", placeholder="you@company.com", key=f"{key}_email")
        c1, c2 = st.columns(2)
        pw = c1.text_input("Choose a password (min. 8 characters)", type="password", key=f"{key}_pw")
        pw2 = c2.text_input("Repeat the password", type="password", key=f"{key}_pw2")
        marketing = st.checkbox(funnel.CONSENT_TEXT, value=False, key=f"{key}_mkt")
        st.caption(f"This creates your free RECOSA account — no card. We use your email to send "
                   f"the result and to log you in; updates only if you tick the box. "
                   f"[Privacy policy]({PRIVACY_POLICY_URL})")
        go = st.form_submit_button("Get my full report" if pending["tool"] == funnel.TOOL_WEBSITE
                                   else "Get my full result", type="primary")
    # The login link carries the check, so an existing account keeps it.
    login_url = funnel.signup_url(APP_BASE_URL, pending["tool"],
                                  answers=funnel.decode_answers(pending.get("answers")),
                                  site=pending.get("site"))
    if not go:
        st.caption(f"Already have an account? [Log in to RECOSA]({login_url})")
        return
    email = email.strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        st.error("Please enter a valid email address.")
    elif len(pw) < 8:
        st.error("The password needs at least 8 characters.")
    elif pw != pw2:
        st.error("The passwords don't match.")
    else:
        ok, msg = _signup(email, pw, pending, marketing)
        if not ok:
            st.error(msg)
            return
        _rpc("record_funnel_event", {"p_event": "signup", "p_tool": pending["tool"],
                                     "p_source": "public_form"})
        own = (pending["tool"] == funnel.TOOL_QUIZ
               or funnel.domains_match(email, pending.get("site") or ""))
        done = (f"Almost there — we've sent a confirmation link to **{email}**. "
                + ("Confirm your address and the full report comes to you by email, as a PDF; "
                   "log in to RECOSA to see it straight away."
                   if own and pending["tool"] == funnel.TOOL_WEBSITE else
                   "Confirm your address and your full result comes to you by email; "
                   "log in to RECOSA to see it straight away."
                   if own else
                   f"Your email is not at **{pending['site']}**, so after confirming, log in to "
                   f"RECOSA and prove the site is yours — one line on its homepage or in its DNS. "
                   f"The report is sent as soon as it's verified.")
                # Supabase answers an existing address exactly like a new
                # one and sends nothing (so the form can't reveal who has an
                # account) — say so, and give the way in.
                + f"\n\nAlready have a RECOSA account with this address? No new email is "
                  f"sent: [log in instead]({login_url}) to see your report.")
        st.session_state[f"{key}_done"] = done
        st.rerun()


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
        st.session_state.pop("quiz_account_done", None)
        _rpc("record_funnel_event", {"p_event": "quiz_completed",
                                     "p_tool": funnel.TOOL_QUIZ, "p_source": None})

    answers = st.session_state.get("quiz_answers")
    if answers:
        st.divider()
        render_quiz_score(answers)
        render_quiz_breakdown(answers, locked=True)
        st.write("")
        _account_form("quiz_account", {"tool": funnel.TOOL_QUIZ,
                                       "answers": funnel.encode_answers(answers)})

# ── GDPR website check ────────────────────────────────────────────────────
with tab_site:
    st.caption(
        "We read your homepage and its privacy, cookie, terms and contact pages, "
        "and check them against GDPR, ePrivacy, accessibility and consumer rules. "
        "About 30 seconds."
    )
    st.info(
        "**For your own website.** The full report goes to an email address at the "
        "site's domain — you@yourcompany.com for yourcompany.com. Is your email on another "
        "domain, for a brand or product site? You can prove the site is yours after signing "
        "up, with one line on its homepage or in its DNS. Paid plans check any number of "
        "sites: your other brands, or the companies you work for.",
        icon="🔒",
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
                       "this connection. Try again tomorrow, or start a free trial in "
                       f"[RECOSA]({APP_BASE_URL}/) to check your sites without limit.")
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
                st.session_state.pop("site_account_done", None)

    check = st.session_state.get("site_result")
    if check:
        from audit_view import render_results
        st.divider()
        st.subheader(f"Your result for {check['domain']}")
        render_results(check["audit"], locked=True)
        st.write("")
        _account_form("site_account", {"tool": funnel.TOOL_WEBSITE, "site": check["domain"]},
                      note=f"Use your email at {check['domain']} to receive the report directly.")
