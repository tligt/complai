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

THE FLOW (D-129, 28 Oct 2026). Replaces two tabs that each ended in their
own sign-up form, so the second check was never taken:
  1. Which rules apply — four questions (funnel.applicable_rules).
  2. The checks that matter for those rules, one after the other: the
     website check, then the NIS2 questions. Either can be skipped.
  3. One result page and one form; the account carries every check taken.

DEEP LINKS, for the website and campaigns (all optional, combinable):
  ?check=website      straight to the website check (?tool=website still works)
  ?check=nis2         straight to the NIS2 Quick Check
  ?site=acme.be       the website field filled in
  ?src=homepage       where the visitor came from: on every funnel event, and
                      on the account as recosa_source
With no ?check the visit starts at step 1. After a direct check, the result
page offers the other one before the form.

THE FUNNEL (S49 D-115, part 2 D-119). Free to check; one form for the full
result: it creates the free account, and the result is emailed once the
address is confirmed (and shown in the app at first login). Everything else
in the app sits behind the trial.
  - Score and band, or the website's score and counts per regulation: free.
  - The breakdown / findings: locked here until the account is confirmed.
  - The website report only for the visitor's own site (S43): an address at
    its domain, or the site proven theirs after signup (funnel_delivery).

WHAT THIS APP CAN WRITE. With the anon key only: Supabase sign-up (the new
account, its free checks in user metadata) and two SECURITY DEFINER functions
(migration_s49_funnel.sql): start_website_check, record_funnel_event. No
service-role key here, no table access, no reads. It sends no email itself:
the result goes out once the address is confirmed (funnel_delivery.py).

Secrets (Streamlit Cloud, top level): APP_BASE_URL, SUPABASE_URL,
SUPABASE_KEY (the anon key), optionally PRIVACY_POLICY_URL.

NOT A COMPLIANCE AUDIT. The quiz questions and weights in funnel.py are draft
marketing copy, not reviewed legal text — reviewed before launch (D-115). The
scope answers are a first indication, and the page says so.
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
from funnel_ui import (render_quiz_form, render_quiz_score, render_quiz_breakdown,
                       render_rules)

st.set_page_config(
    page_title="RECOSA — Free compliance check",
    page_icon="🛡️",
    layout="centered",
)

APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "http://localhost:8501").rstrip("/")
PRIVACY_POLICY_URL = os.environ.get("PRIVACY_POLICY_URL") or "https://recosa.eu/privacy-policy"
WEBSITE_URL = "https://www.recosa.eu"

CHECK_LABELS = {
    funnel.TOOL_WEBSITE: ("🌐", "Website check", "30 seconds",
                          "Your homepage and its privacy, cookie, terms and contact pages, "
                          "against GDPR, ePrivacy, accessibility and consumer rules."),
    funnel.TOOL_QUIZ:    ("🛡️", "NIS2 Quick Check", "2 minutes",
                          "Ten questions on the security measures NIS2 expects (Art. 21)."),
}
# The check's name inside a sentence: "the website check", "the NIS2 Quick Check".
IN_TEXT = {funnel.TOOL_WEBSITE: "website check", funnel.TOOL_QUIZ: "NIS2 Quick Check"}
LINK_CHECKS = {"website": funnel.TOOL_WEBSITE, "nis2": funnel.TOOL_QUIZ,
               "quiz": funnel.TOOL_QUIZ}


# ── Look: recosa.eu, as the login page (D-127) ────────────────────────────
# Public Sans, navy #003366 for headings and the main button, slate #31506D
# for text, turquoise #14C7D5 only for small labels, pale #E8EDF2 panels,
# white cards with soft corners.
_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;700;800&display=swap");
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stHeader"] {
    display: none !important; }
.stApp { background: #FFFFFF; }
.stApp, .stApp p, .stApp label, .stApp input, .stApp button, .stApp a, .stApp li {
    font-family: 'Public Sans', -apple-system, BlinkMacSystemFont, sans-serif; }
.main .block-container, [data-testid="stMainBlockContainer"] {
    max-width: 760px !important; padding: 1.25rem 1rem 3rem !important; }
.stApp p, .stApp li, .stApp label { color: #31506D; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { color: #003366 !important; font-weight: 800 !important; }

.fc-top { display: flex; align-items: center; gap: 10px; padding: 0 0 18px;
          border-bottom: 1px solid #EEF1F4; margin-bottom: 28px; }
.fc-mark { width: 32px; height: 32px; border-radius: 8px; background: #003366; color: #fff;
           display: flex; align-items: center; justify-content: center; font-weight: 800; }
.fc-name { color: #003366; font-weight: 800; font-size: 18px; letter-spacing: .5px; }
.fc-back { margin-left: auto; color: #31506D !important; font-size: 14px; font-weight: 700;
           text-decoration: none; }
.fc-pill { display: inline-block; background: rgba(20,199,213,.14); color: #0B7F89;
           font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 999px; }
.fc-h { color: #003366; font-weight: 800; font-size: 34px; line-height: 1.15; margin: 14px 0 10px; }
.fc-sub { color: #31506D; font-size: 16px; line-height: 1.5; margin: 0 0 22px; }
.fc-steps { display: flex; gap: 8px; margin: 0 0 18px; flex-wrap: wrap; }
.fc-step { font-size: 13px; font-weight: 700; color: #8A9BB0; background: #F3F6F9;
           border-radius: 999px; padding: 6px 12px; }
.fc-step.on { color: #FFFFFF; background: #003366; }
.fc-step.done { color: #003366; background: #E8EDF2; }
.fc-note { background: #E8EDF2; border-radius: 14px; padding: 12px 16px; margin: 6px 0 14px;
           color: #31506D; font-size: 14px; line-height: 1.5; }
.fc-note b { color: #003366; }
.fc-fine { color: #31506D; font-size: 12.5px; line-height: 1.5; }
.fc-fine a { color: #003366 !important; font-weight: 700; }

/* Cards: Streamlit's bordered containers and forms */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]),
[data-testid="stForm"] { border: 1px solid #E3E8EE !important; border-radius: 18px !important;
    background: #FFFFFF; }
[data-testid="stForm"] { padding: 22px 22px 18px !important; }
[data-testid="stTextInputRootElement"] { border-radius: 8px !important;
    border: 1px solid #D6DDE5 !important; background: #FFFFFF !important; }
[data-testid="stTextInputRootElement"] * { background: transparent !important; }
[data-testid="stTextInputRootElement"]:focus-within { border-color: #003366 !important; }
.stApp label p { color: #003366 !important; font-weight: 700 !important; }
[data-testid="stRadio"] [role="radiogroup"] label p, [data-testid="stCheckbox"] label p {
    color: #31506D !important; font-weight: 500 !important; }

/* Main buttons: navy, as on recosa.eu */
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind^="primary"] {
    background: #003366 !important; border: none !important; border-radius: 8px !important;
    min-height: 44px; }
.stButton > button[kind="primary"] p, [data-testid="stFormSubmitButton"] > button[kind^="primary"] p {
    color: #FFFFFF !important; font-weight: 700 !important; font-size: 15px !important; }
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind^="primary"]:hover { background: #00264D !important; }
.stButton > button[kind="secondary"] { border-radius: 8px !important; border: 1px solid #D6DDE5 !important;
    min-height: 44px; }
.stButton > button[kind="secondary"] p { color: #003366 !important; font-weight: 700 !important; }
.stButton > button[kind="tertiary"] p { color: #31506D !important; font-size: 13px !important;
    text-decoration: underline; }
@media (max-width: 640px) { .fc-h { font-size: 27px; } }
</style>
"""


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


def _event(event: str, tool: str | None = None) -> None:
    _rpc("record_funnel_event", {"p_event": event, "p_tool": tool,
                                 "p_source": st.session_state.get("src")})


def _signup(email: str, password: str, pending: dict, marketing: bool) -> tuple[bool, str]:
    """S49 part 2 (D-119). Create the free account with the anon key, carrying
    the free checks on the account itself (user metadata) — the client app
    and monitor_funnel.py pick them up from there. (ok, message)."""
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
                "recosa_source": st.session_state.get("src") or pending["tool"],
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


# ── State ─────────────────────────────────────────────────────────────────
# step: scope → plan → website / nis2 (in plan order) → results.
# plan: the checks to take; done: those taken; skipped: those passed over.

ss = st.session_state


def _start_from_link() -> None:
    """Once per visit: where the link says to start, and what it fills in."""
    qp = st.query_params
    check = LINK_CHECKS.get((qp.get("check") or "").strip().lower())
    if not check and qp.get("tool") == "website":
        check = funnel.TOOL_WEBSITE
    ss.src = (qp.get("src") or "")[:40] or None
    ss.site_prefill = (qp.get("site") or "").strip()[:120]
    ss.plan = [check] if check else []
    ss.done, ss.skipped = [], []
    ss.step = check or "scope"
    ss.direct = bool(check)
    _event("check_landing", check)


if "step" not in ss:
    _start_from_link()


def _go(step: str) -> None:
    ss.step = step
    st.rerun()


def _next_step() -> str:
    for tool in ss.plan:
        if tool not in ss.done and tool not in ss.skipped:
            return tool
    return "results"


def _pending() -> dict | None:
    """Everything taken so far, as the account will carry it."""
    answers = ss.get("quiz_answers")
    site = (ss.get("site_result") or {}).get("domain")
    scope = ss.get("scope")
    return funnel.pending_from_params(
        funnel.encode_answers(answers) if answers else None, site,
        funnel.encode_scope(scope) if scope else None)


# ── Page parts ────────────────────────────────────────────────────────────

def _header() -> None:
    st.html(_CSS)
    st.markdown(
        '<div class="fc-top"><div class="fc-mark">R</div><span class="fc-name">RECOSA</span>'
        f'<a class="fc-back" href="{WEBSITE_URL}" target="_self">Back to recosa.eu</a></div>',
        unsafe_allow_html=True)
    titles = {
        "scope":   ("Which EU rules apply to your company?",
                    "Four quick questions, then the free checks that matter for you."),
        "plan":    ("Here is what applies to you",
                    "A first indication from your answers — not legal advice."),
        funnel.TOOL_WEBSITE: ("Check your website",
                              "A first read on your site's GDPR and ePrivacy basics."),
        funnel.TOOL_QUIZ:    ("NIS2 Quick Check",
                              "Where you stand on the security measures NIS2 expects."),
        "results": ("Your results", "The headline is free. The full report comes with a free account."),
    }
    h, sub = titles[ss.step]
    st.markdown(f'<span class="fc-pill">Free · no card · a few minutes</span>'
                f'<div class="fc-h">{h}</div><div class="fc-sub">{sub}</div>',
                unsafe_allow_html=True)
    # Where the visitor is. A direct link starts at the check: no step 1.
    stage = {"scope": 0, "plan": 0, "results": 2}.get(ss.step, 1)
    names = (["Your checks", "Your results"] if ss.direct
             else ["Which rules apply", "Your checks", "Your results"])
    offset = 1 if ss.direct else 0
    pills = "".join(
        f'<span class="fc-step {"on" if i + offset == stage else "done" if i + offset < stage else ""}">'
        f'{i + 1}. {n}</span>' for i, n in enumerate(names))
    st.markdown(f'<div class="fc-steps">{pills}</div>', unsafe_allow_html=True)


def _scope_step() -> None:
    with st.form("scope_form"):
        size = st.radio("How big is your company?", list(funnel.SIZES),
                        format_func=funnel.SIZES.get, index=None)
        sector = st.selectbox("What does it do?", list(funnel.SECTOR_OPTIONS),
                              format_func=funnel.SECTOR_OPTIONS.get, index=None,
                              placeholder="Choose the closest — or None of these")
        website = st.radio("Do you have a website?", [funnel.YES, funnel.NO],
                           format_func={funnel.YES: "Yes", funnel.NO: "No"}.get,
                           index=None, horizontal=True)
        ai = st.radio("Does anyone at your company use AI tools for work?",
                      [funnel.YES, funnel.NO, funnel.UNSURE],
                      format_func={funnel.YES: "Yes", funnel.NO: "No",
                                   funnel.UNSURE: "Not sure"}.get,
                      index=None, horizontal=True)
        go = st.form_submit_button("Show what applies to me", type="primary",
                                   use_container_width=True)
    if go:
        if None in (size, sector, website, ai):
            st.warning("Answer the four questions to see what applies.")
            return
        ss.scope = {"size": size, "sector": sector, "website": website, "ai": ai}
        ss.plan = funnel.checks_for(funnel.applicable_rules(ss.scope))
        _event("scope_completed", None)
        _go("plan")


def _plan_step() -> None:
    rules = funnel.applicable_rules(ss.scope)
    with st.container(border=True):
        render_rules(rules)
    if ss.plan:
        st.markdown("#### Your free checks")
        for tool in ss.plan:
            icon, name, time, what = CHECK_LABELS[tool]
            st.markdown(f"{icon} **{name}** · {time}  \n:gray[{what}]")
        if st.button(f"Start the {IN_TEXT[ss.plan[0]]}", type="primary", use_container_width=True):
            _go(ss.plan[0])
    else:
        st.markdown(
            '<div class="fc-note"><b>No free check fits your answers.</b> GDPR still applies to '
            'you: RECOSA works out your obligations from your company and writes the policies '
            'and registers with you.</div>', unsafe_allow_html=True)
        st.link_button("Start a 14-day free trial", f"{APP_BASE_URL}/?signup=1&src=free_check",
                       type="primary", use_container_width=True)
        if st.button("Take the NIS2 Quick Check anyway", use_container_width=True):
            ss.plan = [funnel.TOOL_QUIZ]
            _go(funnel.TOOL_QUIZ)
    if st.button("Change my answers", type="tertiary"):
        _go("scope")


def _skip_or_next(tool: str) -> None:
    """Under a check: on to the next one, or to the results."""
    nxt = _next_step()
    if tool in ss.done:
        label = (f"Next: the {IN_TEXT[nxt]}" if nxt != "results"
                 else "See my results and get the full report")
        if st.button(label + " →", type="primary", use_container_width=True, key=f"next_{tool}"):
            _go(nxt)
    elif len(ss.plan) > 1 or ss.done:
        if st.button("Skip this check", type="tertiary", key=f"skip_{tool}"):
            ss.skipped.append(tool)
            _go(_next_step())


def _website_step() -> None:
    st.markdown(
        '<div class="fc-note"><b>For your own website.</b> The full report goes to an email '
        'address at the site\'s domain — you@yourcompany.com for yourcompany.com. Email on another '
        'domain, for a brand or product site? You can prove the site is yours after signing up. '
        'Paid plans check any number of sites.</div>', unsafe_allow_html=True)
    with st.form("site_check"):
        url = st.text_input("Website", value=ss.get("site_prefill") or "",
                            placeholder="https://yourcompany.com")
        run = st.form_submit_button("Check my website", type="primary", use_container_width=True)

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
                ss.site_result = {
                    "audit": run_checklist(result),
                    "domain": extract_domain(normalise_url(url.strip())),
                    "url": normalise_url(url.strip()),
                }
                if funnel.TOOL_WEBSITE not in ss.done:
                    ss.done.append(funnel.TOOL_WEBSITE)
                ss.pop("account_done", None)

    check = ss.get("site_result")
    if check:
        from audit_view import render_results
        st.markdown(f"#### Your result for {check['domain']}")
        render_results(check["audit"], locked=True)
    _skip_or_next(funnel.TOOL_WEBSITE)


def _quiz_step() -> None:
    answers = render_quiz_form("nis2_quiz")
    if answers is not None:
        ss.quiz_answers = answers
        if funnel.TOOL_QUIZ not in ss.done:
            ss.done.append(funnel.TOOL_QUIZ)
        ss.pop("account_done", None)
        _event("quiz_completed", funnel.TOOL_QUIZ)
    if ss.get("quiz_answers"):
        render_quiz_score(ss.quiz_answers)
        render_quiz_breakdown(ss.quiz_answers, locked=True)
    _skip_or_next(funnel.TOOL_QUIZ)


def _results_step() -> None:
    if ss.get("scope"):
        with st.container(border=True):
            st.markdown("**What applies to you**")
            render_rules(funnel.applicable_rules(ss.scope))
    check = ss.get("site_result")
    if check:
        from audit_view import render_results
        with st.container(border=True):
            st.markdown(f"**🌐 Website check — {check['domain']}**")
            render_results(check["audit"], locked=True)
    if ss.get("quiz_answers"):
        with st.container(border=True):
            st.markdown("**🛡️ NIS2 Quick Check**")
            render_quiz_score(ss.quiz_answers)
            render_quiz_breakdown(ss.quiz_answers, locked=True)

    # The checks not taken: offered before the form, so taking one does not
    # lose the other's result (the account carries both).
    missing = [t for t in (funnel.TOOL_WEBSITE, funnel.TOOL_QUIZ) if t not in ss.done]
    for tool in missing:
        icon, name, time, what = CHECK_LABELS[tool]
        if st.button(f"{icon} Also take the {IN_TEXT[tool]} · {time}", use_container_width=True,
                     key=f"also_{tool}"):
            if tool not in ss.plan:
                ss.plan.append(tool)
            if tool in ss.skipped:
                ss.skipped.remove(tool)
            _go(tool)
    if not ss.get("scope") and st.button("Not sure which rules apply to you? Four questions",
                                         type="tertiary"):
        ss.direct = False
        _go("scope")

    pending = _pending()
    if not pending:
        st.markdown(
            '<div class="fc-note">Take a check above to see where you stand.</div>',
            unsafe_allow_html=True)
        return
    st.write("")
    _account_form(pending)


def _account_form(pending: dict) -> None:
    """The one step: complete the form, get the full results in the app and
    by email once the address is confirmed."""
    if ss.get("account_done"):
        st.success(ss.account_done)
        return
    site, quiz = funnel.has_site(pending), funnel.has_quiz(pending)
    with st.form("account", border=True):
        st.markdown(
            "**Get the full report — " + (
                "the website findings and how to fix them, as a PDF, and your NIS2 breakdown."
                if site and quiz else
                "every finding and how to fix it, also sent to you as a PDF."
                if site else
                "every area, what to do first, also sent to you by email.") + "**")
        if site:
            st.caption(f"Use your email at {pending['site']} to receive the website report directly.")
        email = st.text_input("Work email", placeholder="you@company.com", key="acc_email")
        c1, c2 = st.columns(2)
        pw = c1.text_input("Choose a password (min. 8 characters)", type="password", key="acc_pw")
        pw2 = c2.text_input("Repeat the password", type="password", key="acc_pw2")
        marketing = st.checkbox(funnel.CONSENT_TEXT, value=False, key="acc_mkt")
        st.markdown(f'<div class="fc-fine">This creates your free RECOSA account — no card. We use '
                    f'your email to send the results and to log you in; updates only if you tick '
                    f'the box. <a href="{PRIVACY_POLICY_URL}" target="_blank">Privacy policy</a></div>',
                    unsafe_allow_html=True)
        go = st.form_submit_button("Get my full report", type="primary", use_container_width=True)
    # The login link carries the checks, so an existing account keeps them.
    login_url = funnel.signup_url(APP_BASE_URL, ss.get("src") or pending["tool"],
                                  answers=funnel.decode_answers(pending.get("answers")),
                                  site=pending.get("site"), scope=pending.get("scope"))
    if not go:
        st.markdown(f'<div class="fc-fine">Already have an account? '
                    f'<a href="{login_url}" target="_self">Log in to RECOSA</a></div>',
                    unsafe_allow_html=True)
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
        _event("signup", pending["tool"])
        own = not site or funnel.domains_match(email, pending["site"])
        if own:
            what = ("the website report as a PDF and your NIS2 breakdown come to you by email"
                    if site and quiz else
                    "the full report comes to you by email, as a PDF" if site else
                    "your full result comes to you by email")
            body = f"Confirm your address and {what}; log in to RECOSA to see it straight away."
        else:
            body = ((("Confirm your address and your NIS2 result comes to you by email. ")
                     if quiz else "")
                    + f"Your email is not at **{pending['site']}**, so after confirming, log in "
                      f"to RECOSA and prove the site is yours — one line on its homepage or in "
                      f"its DNS. The website report is sent as soon as it's verified.")
        ss.account_done = (
            f"Almost there — we've sent a confirmation link to **{email}**. {body}"
            # Supabase answers an existing address exactly like a new one and
            # sends nothing (so the form can't reveal who has an account) —
            # say so, and give the way in.
            f"\n\nAlready have a RECOSA account with this address? No new email is "
            f"sent: [log in instead]({login_url}) to see your report.")
        st.rerun()


# ── Page ──────────────────────────────────────────────────────────────────

_header()
{
    "scope": _scope_step,
    "plan": _plan_step,
    funnel.TOOL_WEBSITE: _website_step,
    funnel.TOOL_QUIZ: _quiz_step,
    "results": _results_step,
}[ss.step]()
