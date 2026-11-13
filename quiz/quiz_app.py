"""
quiz/quiz_app.py — the public free checks: the NIS2 Quick Check (S45), the
GDPR website check (S49), the AI Act Quick Check (S55) and the GDPR Quick
Check (D-137). Deployed as its own Streamlit Cloud app with
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
     website check, the GDPR, NIS2 and AI Act questions. Any can be
     skipped.
  3. One result page and one form; the account carries every check taken.

DEEP LINKS, for the website and campaigns (all optional, combinable):
  ?check=website      straight to the website check (?tool=website still works)
  ?check=nis2         straight to the NIS2 Quick Check
  ?check=ai           straight to the AI Act Quick Check (S55)
  ?check=gdpr         straight to the GDPR Quick Check (D-137)
  ?site=acme.be       the website field filled in
  ?src=homepage       where the visitor came from: on every funnel event, and
                      on the account as recosa_source
With no ?check the visit starts at step 1.

THE PAGES (D-133, 3 Nov 2026). A check shows its questions, then its result
alone (the questions go; "Change my answers" brings them back). The results
page puts the full report first — the one main action — and offers the
checks not taken in one quiet line under it. The whole visit is kept in the
address (step, answers, the site's summary — never anything personal), so a
refresh or a bookmark keeps every result: a Streamlit session alone does not
survive a reload.

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


def _fresh_shared_modules() -> None:
    """D-136. On a push, Streamlit Cloud reruns this script with the new code
    but keeps the modules from the folder above as first imported — only
    this script's own folder is watched. New questions in funnel.py stayed
    invisible until a reboot, and a call into something new would fail.
    funnel and funnel_ui record their file's timestamp when loaded; reload
    either one whose file is newer (or that predates the record), before the
    from-imports below bind their names."""
    import importlib
    for name in ("funnel", "funnel_ui"):  # funnel first: funnel_ui uses it
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "_LOADED_MTIME", None) != os.path.getmtime(mod.__file__):
            importlib.reload(mod)


_fresh_shared_modules()

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
    funnel.TOOL_GDPR:    ("🔐", "GDPR Quick Check", "2 minutes",
                          "Ten questions on what GDPR asks behind the website — your data, "
                          "suppliers, rights requests, breaches, retention."),
    funnel.TOOL_QUIZ:    ("🛡️", "NIS2 Quick Check", "3 minutes",
                          "Thirteen questions on the security measures NIS2 expects, and "
                          "management's own duties."),
    funnel.TOOL_AI:      ("🤖", "AI Act Quick Check", "2 minutes",
                          "Nine questions on what the AI Act asks of companies that use "
                          "AI tools — training, transparency, banned and high-risk uses."),
}
# The check's name inside a sentence: "the website check", "the NIS2 Quick Check".
IN_TEXT = {funnel.TOOL_WEBSITE: "website check", funnel.TOOL_QUIZ: "NIS2 Quick Check",
           funnel.TOOL_AI: "AI Act Quick Check", funnel.TOOL_GDPR: "GDPR Quick Check"}
LINK_CHECKS = {"website": funnel.TOOL_WEBSITE, "nis2": funnel.TOOL_QUIZ,
               "quiz": funnel.TOOL_QUIZ, "ai": funnel.TOOL_AI, "aiact": funnel.TOOL_AI,
               "ai-act": funnel.TOOL_AI, "gdpr": funnel.TOOL_GDPR}
ALL_CHECKS = funnel.ALL_CHECKS


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
# step: scope → plan → website / nis2 / ai (in plan order) → results.
# plan: the checks to take; done: those taken; skipped: those passed over.
# editing: the checks whose questions are open again ("Change my answers").
#
# D-133: mirrored into the address after every run (_save_to_url) and read
# back when a new session starts with it (_restore_from_url): a reload starts
# a new Streamlit session, which used to lose every result. Only what is
# already non-personal: answer digits, the scope code, the checked domain and
# its score summary. The site's findings are not in the address — the summary
# is shown instead, and the full report comes by email as before.

ss = st.session_state
CODE_TOOL = {"website": funnel.TOOL_WEBSITE, "nis2": funnel.TOOL_QUIZ, "ai": funnel.TOOL_AI,
             "gdpr": funnel.TOOL_GDPR}
TOOL_CODE = {t: c for c, t in CODE_TOOL.items()}
STEPS = {"scope", "plan", "results"}
RISKS = {"Green", "Amber", "Red", "Low", "Medium", "High"}


def _tools(code: str | None) -> list[str]:
    return [CODE_TOOL[c] for c in (code or "").split(",") if c in CODE_TOOL]


def _site_summary(audit) -> dict:
    return {"score": audit.score, "risk": audit.risk_level, "ok": audit.ok_count,
            "warn": audit.warn_count, "fail": audit.fail_count}


def _restore_from_url() -> bool:
    """A reload or a bookmark: the visit as the address holds it. Validated —
    the address is visitor-controlled. False if there is nothing to restore."""
    qp = st.query_params
    step = qp.get("step") or ""
    step = CODE_TOOL.get(step) or (step if step in STEPS else None)
    if not step:
        return False
    ss.src = (qp.get("src") or "")[:40] or None
    ss.site_prefill = ""
    ss.plan, ss.done, ss.skipped = _tools(qp.get("plan")), _tools(qp.get("done")), _tools(qp.get("skip"))
    ss.direct = qp.get("direct") == "1"
    ss.editing = []
    scope = funnel.decode_scope(qp.get("scope"))
    if scope:
        ss.scope = scope
    answers = funnel.decode_answers(qp.get("q"))
    if answers:
        ss.quiz_answers = answers
    ai = funnel.decode_answers(qp.get("ai"), funnel.AI_ACT)
    if ai:
        ss.ai_answers = ai
    gdpr = funnel.decode_answers(qp.get("g"), funnel.GDPR)
    if gdpr:
        ss.gdpr_answers = gdpr
    site = funnel.pending_from_params(None, qp.get("site"))
    parts = (qp.get("ws") or "").split(".")
    if site and len(parts) == 5 and parts[1] in RISKS and all(p.isdigit() for p in parts[:1] + parts[2:]):
        ss.site_result = {"audit": None, "domain": site["site"], "url": f"https://{site['site']}",
                          "summary": {"score": int(parts[0]), "risk": parts[1], "ok": int(parts[2]),
                                      "warn": int(parts[3]), "fail": int(parts[4])}}
    elif site:
        ss.site_prefill = site["site"]
    # Only what the address actually restored counts as taken.
    have = {funnel.TOOL_WEBSITE: bool(ss.get("site_result")),
            funnel.TOOL_QUIZ: bool(ss.get("quiz_answers")), funnel.TOOL_AI: bool(ss.get("ai_answers")),
            funnel.TOOL_GDPR: bool(ss.get("gdpr_answers"))}
    ss.done = [t for t in ss.done if have[t]]
    if step == "plan" and not ss.get("scope"):
        step = "scope"
    ss.step = step
    return True


def _save_to_url() -> None:
    """The visit, written to the address (no rerun)."""
    d = {"step": TOOL_CODE.get(ss.step, ss.step)}
    if ss.get("src"):
        d["src"] = ss.src
    for key, tools in (("plan", ss.plan), ("done", ss.done), ("skip", ss.skipped)):
        if tools:
            d[key] = ",".join(TOOL_CODE[t] for t in tools)
    if ss.direct:
        d["direct"] = "1"
    if ss.get("scope"):
        d["scope"] = funnel.encode_scope(ss.scope)
    if ss.get("quiz_answers"):
        d["q"] = funnel.encode_answers(ss.quiz_answers)
    if ss.get("ai_answers"):
        d["ai"] = funnel.encode_answers(ss.ai_answers)
    if ss.get("gdpr_answers"):
        d["g"] = funnel.encode_answers(ss.gdpr_answers)
    site = ss.get("site_result")
    if site:
        sm = site.get("summary") or _site_summary(site["audit"])
        d["site"] = site["domain"]
        d["ws"] = f"{sm['score']}.{sm['risk']}.{sm['ok']}.{sm['warn']}.{sm['fail']}"
    elif ss.get("site_prefill"):
        d["site"] = ss.site_prefill
    if dict(st.query_params) != d:
        st.query_params.from_dict(d)


def _start_from_link() -> None:
    """Once per visit: where the link says to start, and what it fills in."""
    qp = st.query_params
    check = LINK_CHECKS.get((qp.get("check") or "").strip().lower())
    if not check and qp.get("tool") == "website":
        check = funnel.TOOL_WEBSITE
    ss.src = (qp.get("src") or "")[:40] or None
    ss.site_prefill = (qp.get("site") or "").strip()[:120]
    ss.plan = [check] if check else []
    ss.done, ss.skipped, ss.editing = [], [], []
    ss.step = check or "scope"
    ss.direct = bool(check)
    _event("check_landing", check)


if "step" not in ss and not _restore_from_url():
    _start_from_link()


def _go(step: str) -> None:
    ss.step = step
    ss.scroll_top = ss.get("scroll_top", 0) + 1
    st.rerun()


def _scroll_to_top() -> None:
    """A new page starts at its top (D-136): Streamlit keeps the scroll
    position across reruns, so a "Next" from the bottom of a long check used
    to land halfway down the next one. A zero-height component scrolls the
    app's own scroll container; the counter makes each one new."""
    n = ss.pop("scroll_top", 0)
    if not n:
        return
    import streamlit.components.v1 as components
    components.html(
        f"""<script>/* {n} {ss.step} */
        const doc = window.parent.document;
        for (const sel of ['[data-testid="stMain"]', '[data-testid="stAppViewContainer"]', 'section.main']) {{
            const el = doc.querySelector(sel); if (el) el.scrollTo(0, 0);
        }}
        window.parent.scrollTo(0, 0);</script>""", height=0)


def _next_step() -> str:
    for tool in ss.plan:
        if tool not in ss.done and tool not in ss.skipped:
            return tool
    return "results"


def _take(tool: str) -> None:
    """Open another check (from the results page or a result)."""
    if tool not in ss.plan:
        ss.plan.append(tool)
    if tool in ss.skipped:
        ss.skipped.remove(tool)
    _go(tool)


def _pending() -> dict | None:
    """Everything taken so far, as the account will carry it."""
    answers = ss.get("quiz_answers")
    ai = ss.get("ai_answers")
    gdpr = ss.get("gdpr_answers")
    site = (ss.get("site_result") or {}).get("domain")
    scope = ss.get("scope")
    return funnel.pending_from_params(
        funnel.encode_answers(answers) if answers else None, site,
        funnel.encode_scope(scope) if scope else None,
        funnel.encode_answers(ai) if ai else None,
        funnel.encode_answers(gdpr) if gdpr else None)


# ── Page parts ────────────────────────────────────────────────────────────

def _header() -> None:
    st.html(_CSS)
    # D-175: same Umami Cloud property as recosa.eu and the login page, so
    # the free check's traffic shows there too — see login_page.py's own
    # comment for what this does and doesn't give (no cookies, no identity
    # stitching; the query string, including ?check= and &src=, is what
    # actually says which path a visitor took).
    st.html('<script defer src="https://cloud.umami.is/script.js" '
           'data-website-id="de0d5db7-3b2c-4dae-b5e5-9522a7dbfde5" '
           'data-domains="recosa.eu,www.recosa.eu,app.recosa.eu,check.recosa.eu"></script>')
    st.markdown(
        '<div class="fc-top"><div class="fc-mark">R</div><span class="fc-name">RECOSA</span>'
        f'<a class="fc-back" href="{WEBSITE_URL}" target="_top">Back to recosa.eu</a></div>',
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
        funnel.TOOL_GDPR:    ("GDPR Quick Check",
                              "Where you stand on what GDPR asks behind your website."),
        funnel.TOOL_AI:      ("AI Act Quick Check",
                              "Where you stand on what the AI Act asks of companies that "
                              "use AI tools."),
        "results": ("Your results", "The headline is free. The full report comes with a free account."),
    }
    h, sub = titles[ss.step]
    st.markdown(f'<span class="fc-pill">Free · no credit card · a few minutes</span>'
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
    prev = ss.get("scope") or {}

    def _at(options, key):
        # The earlier answer pre-selected when the answers are changed.
        return options.index(prev[key]) if prev.get(key) in options else None

    sizes, sectors = list(funnel.SIZES), list(funnel.SECTOR_OPTIONS)
    yes_no, yes_no_unsure = [funnel.YES, funnel.NO], [funnel.YES, funnel.NO, funnel.UNSURE]
    with st.form("scope_form"):
        size = st.radio("How big is your company?", sizes,
                        format_func=funnel.SIZES.get, index=_at(sizes, "size"))
        sector = st.selectbox("What does it do?", sectors,
                              format_func=funnel.SECTOR_OPTIONS.get, index=_at(sectors, "sector"),
                              placeholder="Choose the closest — or None of these")
        website = st.radio("Do you have a website?", yes_no,
                           format_func={funnel.YES: "Yes", funnel.NO: "No"}.get,
                           index=_at(yes_no, "website"), horizontal=True)
        ai = st.radio("Does anyone at your company use AI tools for work?", yes_no_unsure,
                      format_func={funnel.YES: "Yes", funnel.NO: "No",
                                   funnel.UNSURE: "Not sure"}.get,
                      index=_at(yes_no_unsure, "ai"), horizontal=True)
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
    # GDPR always applies, so the plan always holds at least its check (D-137).
    st.markdown("#### Your free checks")
    for tool in ss.plan:
        icon, name, time, what = CHECK_LABELS[tool]
        st.markdown(f"{icon} **{name}** · {time}  \n:gray[{what}]")
    if st.button(f"Start the {IN_TEXT[ss.plan[0]]}", type="primary", use_container_width=True):
        _go(ss.plan[0])
    if st.button("Change my answers", type="tertiary"):
        _go("scope")


# ── Navigation (D-135) ────────────────────────────────────────────────────
# Every check page: the checks bar on top (each check in the plan, any one a
# click away), and at the bottom one way forward — "Next: …" / "See my full
# results" once answered, "Skip to …" before — and "← Back" to the page
# before, in the order the visit goes: what applies → each check → results.

def _sequence() -> list[str]:
    extra = [t for t in ss.done if t not in ss.plan]
    return (["plan"] if ss.get("scope") else []) + ss.plan + extra + ["results"]


def _prev_step(current: str) -> str | None:
    seq = _sequence()
    if current not in seq:
        return seq[-2] if len(seq) > 1 else None
    i = seq.index(current)
    return seq[i - 1] if i > 0 else None


def _step_name(step: str) -> str:
    return {"plan": "What applies to you", "results": "Your results"}.get(
        step, CHECK_LABELS.get(step, ("", step))[1])


def _forward_label(nxt: str, skipping: bool) -> str:
    if skipping:
        return f"Skip to the {IN_TEXT[nxt]} →" if nxt != "results" else "Skip to my results →"
    return f"Next: the {IN_TEXT[nxt]} →" if nxt != "results" else "See my full results →"


def _checks_bar(current: str) -> None:
    """On top of a check: every check of the visit, the current one marked,
    the others a click away."""
    tools = ss.plan + [t for t in ss.done if t not in ss.plan]
    if len(tools) < 2:
        return
    cols = st.columns(len(tools))
    for col, tool in zip(cols, tools):
        icon, name, _, _ = CHECK_LABELS[tool]
        mark = "✓ " if tool in ss.done else ""
        if tool == current:
            col.markdown(f'<div class="fc-step on" style="text-align:center">{icon} {name}</div>',
                         unsafe_allow_html=True)
        elif col.button(f"{mark}{icon} {name}", type="tertiary", key=f"bar_{current}_{tool}",
                        use_container_width=True):
            _go(tool)


def _next_after(tool: str) -> str:
    """The next check still to take after this one in the plan (then any
    earlier one left), else the results."""
    plan = ss.plan if tool in ss.plan else ss.plan + [tool]
    i = plan.index(tool)
    for t in plan[i + 1:] + plan[:i]:
        if t not in ss.done and t not in ss.skipped:
            return t
    return "results"


def _nav(tool: str) -> None:
    """At the bottom of a check: forward, then back."""
    nxt = _next_after(tool)
    if tool in ss.done:
        if st.button(_forward_label(nxt, False), type="primary", use_container_width=True,
                     key=f"next_{tool}"):
            _go(nxt)
    elif st.button(_forward_label(nxt, True), use_container_width=True, key=f"skip_{tool}"):
        if tool not in ss.skipped:
            ss.skipped.append(tool)
        _go(nxt)
    _back_button(tool)


def _back_button(current: str) -> None:
    prev = _prev_step(current)
    if prev and st.button(f"← Back: {_step_name(prev)}", type="tertiary", key=f"back_{current}"):
        _go(prev)


def _render_site(check: dict) -> None:
    """The website result, locked: the findings while the session has them,
    the summary when the visit came back from the address."""
    if check.get("audit") is not None:
        from audit_view import render_results
        render_results(check["audit"], locked=True)
        return
    sm = check["summary"]
    c1, c2 = st.columns(2)
    c1.metric("Score", f"{sm['score']}/100")
    c2.metric("Risk level", sm["risk"])
    st.markdown(f"✅ {sm['ok']} compliant · ⚠️ {sm['warn']} need attention · ❌ {sm['fail']} missing")
    st.caption("🔒 Every finding and how to fix it is in the full report.")


def _website_step() -> None:
    _checks_bar(funnel.TOOL_WEBSITE)
    check = ss.get("site_result")
    if check and funnel.TOOL_WEBSITE not in ss.editing:
        st.markdown(f"#### Your result for {check['domain']}")
        _render_site(check)
        if st.button("Check another website", type="tertiary", key="site_again"):
            ss.editing.append(funnel.TOOL_WEBSITE)
            st.rerun()
        _nav(funnel.TOOL_WEBSITE)
        return

    st.markdown(
        '<div class="fc-note"><b>For your own website.</b> The full report goes to an email '
        'address at the site\'s domain — you@yourcompany.com for yourcompany.com. Email on another '
        'domain, for a brand or product site? You can prove the site is yours after signing up. '
        'Paid plans check any number of sites.</div>', unsafe_allow_html=True)
    with st.form("site_check"):
        url = st.text_input("Website", value=(check or {}).get("domain") or ss.get("site_prefill") or "",
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
                if funnel.TOOL_WEBSITE in ss.editing:
                    ss.editing.remove(funnel.TOOL_WEBSITE)
                st.rerun()
    if check and st.button("Keep my result for " + check["domain"], type="tertiary", key="site_keep"):
        ss.editing.remove(funnel.TOOL_WEBSITE)
        st.rerun()
    if not check:
        _nav(funnel.TOOL_WEBSITE)


def _questions_step(tool: str, kind: dict, key: str, state_key: str) -> None:
    """A quick check: its questions, then its result alone (D-133)."""
    _checks_bar(tool)
    answers = ss.get(state_key)
    if answers and tool not in ss.editing:
        render_quiz_score(answers, kind)
        render_quiz_breakdown(answers, locked=True, kind=kind)
        if st.button("Change my answers", type="tertiary", key=f"edit_{tool}"):
            ss.editing.append(tool)
            st.rerun()
        _nav(tool)
        return
    new = render_quiz_form(key, kind, previous=answers, submit_label="See my score")
    if new is not None:
        ss[state_key] = new
        if tool not in ss.done:
            ss.done.append(tool)
        if tool in ss.editing:
            ss.editing.remove(tool)
        _event("quiz_completed", tool)
        st.rerun()
    if answers and st.button("Keep my answers", type="tertiary", key=f"keep_{tool}"):
        ss.editing.remove(tool)
        st.rerun()
    if not answers:
        _nav(tool)


def _quiz_step() -> None:
    _questions_step(funnel.TOOL_QUIZ, funnel.NIS2, "nis2_quiz", "quiz_answers")


def _gdpr_step() -> None:
    _questions_step(funnel.TOOL_GDPR, funnel.GDPR, "gdpr_check", "gdpr_answers")


def _ai_step() -> None:
    _questions_step(funnel.TOOL_AI, funnel.AI_ACT, "ai_act", "ai_answers")


def _result_line(tool: str) -> None:
    """One check on the results page: its headline, the locked teaser folded."""
    icon, name, _, _ = CHECK_LABELS[tool]
    if tool == funnel.TOOL_WEBSITE:
        check = ss.site_result
        sm = check.get("summary") or _site_summary(check["audit"])
        st.markdown(f"{icon} **{name} — {check['domain']}** · {sm['score']}/100 · {sm['risk']} risk")
        with st.expander("What we found 🔒"):
            _render_site(check)
        _change_link(tool, "Check another website")
        return
    kind = funnel.QUICK_CHECKS[tool][0]
    answers = ss[{funnel.TOOL_QUIZ: "quiz_answers", funnel.TOOL_AI: "ai_answers",
                  funnel.TOOL_GDPR: "gdpr_answers"}[tool]]
    label, _ = funnel.band(funnel.score(answers), kind, len(answers))
    weak = funnel.weak_areas(answers)
    st.markdown(f"{icon} **{name}** · {funnel.score(answers)}/{funnel.max_score(kind, answers)} · {label}"
                f"  \n:gray[{weak} of {len(answers)} areas need attention]")
    with st.expander("Your breakdown 🔒"):
        render_quiz_score(answers, kind)
        render_quiz_breakdown(answers, locked=True, kind=kind)
    _change_link(tool, "Change my answers")


def _change_link(tool: str, label: str) -> None:
    if st.button(label, type="tertiary", key=f"change_{tool}"):
        if tool not in ss.editing:
            ss.editing.append(tool)
        _go(tool)


def _results_step() -> None:
    taken = [t for t in ALL_CHECKS if t in ss.done]
    if ss.get("scope"):
        with st.expander("What applies to you"):
            render_rules(funnel.applicable_rules(ss.scope))
            if st.button("Change my answers", type="tertiary", key="change_scope"):
                _go("scope")
    pending = _pending()
    if not pending:
        st.markdown(
            '<div class="fc-note">Take a check to see where you stand.</div>',
            unsafe_allow_html=True)
        for tool in ALL_CHECKS:
            icon, name, time, what = CHECK_LABELS[tool]
            if st.button(f"{icon} {name} · {time}", use_container_width=True, key=f"also_{tool}"):
                _take(tool)
        return

    with st.container(border=True):
        st.markdown("**Your results**")
        for tool in taken:
            _result_line(tool)

    st.write("")
    _account_form(pending)

    # The checks not taken: offered, not pushed (D-133) — one quiet line under
    # the form, and the account carries every check taken.
    missing = [t for t in ALL_CHECKS if t not in ss.done]
    if missing:
        st.write("")
        st.markdown('<div class="fc-fine"><b>Also free</b> — added to the same report:</div>',
                    unsafe_allow_html=True)
        cols = st.columns(len(missing))
        for col, tool in zip(cols, missing):
            icon, name, time, _ = CHECK_LABELS[tool]
            if col.button(f"{icon} {name} · {time}", type="tertiary", key=f"also_{tool}"):
                _take(tool)
    if not ss.get("scope") and st.button("Not sure which rules apply to you? Four questions",
                                         type="tertiary"):
        ss.direct = False
        _go("scope")
    _back_button("results")


def _and(items: list[str]) -> str:
    """"a", "a and b", "a, b and c"."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _account_form(pending: dict) -> None:
    """The one step: complete the form, get the full results in the app and
    by email once the address is confirmed."""
    site, quiz, ai = funnel.has_site(pending), funnel.has_quiz(pending), funnel.has_ai(pending)
    gdpr = funnel.has_gdpr(pending)
    # The login link carries the checks, so an existing account keeps them.
    login_url = funnel.signup_url(APP_BASE_URL, ss.get("src") or pending["tool"],
                                  answers=funnel.decode_answers(pending.get("answers")),
                                  site=pending.get("site"), scope=pending.get("scope"),
                                  ai_answers=funnel.decode_answers(pending.get("ai_answers"),
                                                                   funnel.AI_ACT),
                                  gdpr_answers=funnel.decode_answers(pending.get("gdpr_answers"),
                                                                     funnel.GDPR),
                                  login=True)
    if ss.get("account_done"):
        st.success(ss.account_done)
        # D-133: a check taken after the form went is not on the new account
        # (a second sign-up with the same address does nothing). The login
        # link carries every check, so logging in once confirmed adds it.
        added = [IN_TEXT[t] for t in ALL_CHECKS
                 if funnel.has_check(pending, t) and not funnel.has_check(ss.signed_pending, t)]
        if added:
            st.info(f"To add your {_and(added)} result to your account: confirm your address, "
                    f"then [log in with this link]({login_url}). It brings every result on "
                    "this page with it.")
        return
    parts = ((["a PDF of the website findings and how to fix them"] if site else [])
             + (["your GDPR breakdown"] if gdpr else [])
             + (["your NIS2 breakdown"] if quiz else [])
             + (["your AI Act breakdown"] if ai else []))
    with st.form("account", border=True):
        st.markdown(
            "**Get the full report — " + (
                _and(parts) + "." if len(parts) > 1 else
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
        st.markdown(f'<div class="fc-fine">This creates your free RECOSA account — no credit card. We use '
                    f'your email to send the results and to log you in; updates only if you tick '
                    f'the box. <a href="{PRIVACY_POLICY_URL}" target="_blank">Privacy policy</a></div>',
                    unsafe_allow_html=True)
        go = st.form_submit_button("Get my full report", type="primary", use_container_width=True)
    if not go:
        st.markdown(f'<div class="fc-fine">Already have an account? '
                    f'<a href="{login_url}" target="_top">Log in to RECOSA</a></div>',
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
        ss.signed_pending = pending
        own = not site or funnel.domains_match(email, pending["site"])
        results = ((["your GDPR breakdown"] if gdpr else []) + (["your NIS2 breakdown"] if quiz else [])
                   + (["your AI Act breakdown"] if ai else []))
        if own:
            what = (_and((["the website report as a PDF"] if site else []) + results)
                    + " come to you by email" if len(parts) > 1 else
                    "the full report comes to you by email, as a PDF" if site else
                    "your full result comes to you by email")
            body = f"Confirm your address and {what}; log in to RECOSA to see it straight away."
        else:
            body = (((f"Confirm your address and {_and(results)} "
                      f"{'come' if len(results) > 1 else 'comes'} to you by email. ")
                     if results else "")
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
_scroll_to_top()
{
    "scope": _scope_step,
    "plan": _plan_step,
    funnel.TOOL_WEBSITE: _website_step,
    funnel.TOOL_GDPR: _gdpr_step,
    funnel.TOOL_QUIZ: _quiz_step,
    funnel.TOOL_AI: _ai_step,
    "results": _results_step,
}[ss.step]()
_save_to_url()
