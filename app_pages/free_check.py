"""
pages/free_check.py — S49 (D-115). A free account's own page: the full
result of the free checks it signed up with, and the way to the trial.

The result comes from profiles.pending_result, written at signup from the
link the public app's CTA carried (?quiz= / ?site= / ?aiact= / ?scope=), so
it survives email confirmation and a different browser. Since D-129 it may
hold several checks (the AI Act Quick Check since S55), and the scope
answers; a check not taken yet can be taken here, and is added to the same
result.

The NIS2 and AI Act answers are also written to the obligation register as
DECLARED answers — the lowest precedence (obligation_register.py), so any analysis,
document or derivation overrides them — and only where the client has
recorded nothing for that obligation yet.
"""
from i18n import tr  # S64 interface translation (D-164)

import streamlit as st

import funnel
from funnel_ui import (render_quiz_form, render_quiz_score, render_quiz_breakdown,
                       render_rules)
from audit_view import render_results
from auth import get_user_id
from cached_reads import load_accessible_clients
from database import get_user_profile, save_pending_result, save_audit
from subscribe_view import render_trial_cta

user_id = get_user_id()
profile = get_user_profile(user_id)
pending = profile.get("pending_result") or {}
clients = load_accessible_clients(user_id) or []
client = st.session_state.get("selected_client") or (clients[0] if clients else None)
email = st.session_state.user.email

st.title(tr("Your free check"))


def _store(result: dict | None) -> None:
    save_pending_result(user_id, result)
    st.rerun()


def _add_quiz(key: str) -> None:
    answers = render_quiz_form(key)
    if answers is not None:
        _store({**pending, "tool": pending.get("tool") or funnel.TOOL_QUIZ,
                "answers": funnel.encode_answers(answers)})


def _add_ai(key: str) -> None:
    answers = render_quiz_form(key, funnel.AI_ACT)
    if answers is not None:
        _store({**pending, "tool": pending.get("tool") or funnel.TOOL_AI,
                "ai_answers": funnel.encode_answers(answers)})


def _add_gdpr(key: str) -> None:
    answers = render_quiz_form(key, funnel.GDPR)
    if answers is not None:
        _store({**pending, "tool": pending.get("tool") or funnel.TOOL_GDPR,
                "gdpr_answers": funnel.encode_answers(answers)})


def _add_site(key: str) -> None:
    with st.form(key):
        url = st.text_input(tr("Website"), value=(client or {}).get("website_url") or "",
                            placeholder=tr("https://yourcompany.com"))
        if st.form_submit_button(tr("Check my website"), type="primary"):
            from crawler import extract_domain, normalise_url
            pend = funnel.pending_from_params(None, extract_domain(normalise_url(url)))
            if pend:
                _store({**pending, "tool": pending.get("tool") or funnel.TOOL_WEBSITE,
                        "site": pend["site"]})
            else:
                st.error(tr("Please enter a valid website address."))


# ── No check yet: take one here ───────────────────────────────────────────
if not any(funnel.has_check(pending, t) for t in funnel.ALL_CHECKS):
    st.caption(tr("Take one of the free checks to see where you stand."))
    tab_site, tab_gdpr, tab_quiz, tab_ai = st.tabs([tr("🌐 Website check"), tr("🔐 GDPR Quick Check"),
                                                    tr("🛡️ NIS2 Quick Check"), tr("🤖 AI Act Quick Check")])
    with tab_site:
        _add_site("app_site")
    with tab_gdpr:
        _add_gdpr("app_gdpr")
    with tab_quiz:
        _add_quiz("app_quiz")
    with tab_ai:
        _add_ai("app_ai")
    st.stop()

scope = funnel.decode_scope(pending.get("scope"))
if scope:
    with st.container(border=True):
        st.markdown(tr("**The rules that apply to you** — a first indication from your answers"))
        render_rules(funnel.applicable_rules(scope))

# ── Website check result ──────────────────────────────────────────────────
answers = funnel.decode_answers(pending.get("answers"))
ai_answers = funnel.decode_answers(pending.get("ai_answers"), funnel.AI_ACT)
gdpr_answers = funnel.decode_answers(pending.get("gdpr_answers"), funnel.GDPR)
if funnel.has_site(pending):
    import funnel_delivery as FD
    site = pending["site"]
    # S49 part 2 (D-119): own site only — an address at its domain, or the
    # site proven this account's (meta tag or DNS TXT).
    proven = FD.site_proven(email, pending)
    key = f"free_check_{site}"
    st.subheader(f"Website check — {site}")
    if key not in st.session_state:
        from crawler import crawl
        from checklist import run_checklist
        with st.spinner(f"Checking {site}…"):
            crawl_result = crawl(site)
        st.session_state[key] = ((run_checklist(crawl_result), crawl_result.url)
                                 if not crawl_result.error else (None, crawl_result.error))
    audit, site_url = st.session_state[key]
    if audit is None:
        st.error(site_url)
    elif not proven:
        render_results(audit, locked=True)
        token = pending.get("site_token")
        if not token:
            token = FD.new_token()
            pending = {**pending, "site_token": token}
            save_pending_result(user_id, pending)
        with st.container(border=True):
            st.markdown(f"**Prove that {site} is yours to unlock the full report**")
            st.caption(f"Your email ({email}) is not at {site}. Free checks are for your own "
                       "website, so add one of these, then verify. Paid plans check any site.")
            st.markdown("**Either** a meta tag in the `<head>` of the homepage:")
            st.code(f'<meta name="{FD.META_NAME}" content="{token}">', language="html")
            st.markdown(f"**or** a DNS TXT record on {site}:")
            st.code(f"{FD.META_NAME}={token}", language="text")
            if st.button(tr("Verify the site"), type="primary", key="verify_site"):
                with st.spinner(tr("Looking for it…")):
                    ok, how = FD.check_site(site, token)
                if ok:
                    save_pending_result(user_id, {**pending, "site_verified": True, "verified_by": how})
                    st.rerun()
                st.error(tr("Not found yet. Check the tag is on the homepage itself, or wait for the "
                         "DNS record to spread (it can take an hour), then try again."))
    else:
        if not pending.get("audited"):
            save_audit(
                email=email, email_domain=email.split("@")[-1].lower(),
                website_url=site_url, audit_result=audit,
                user_id=user_id, client_id=(client or {}).get("id"),
                site_domain=site,
            )
            pending = {**pending, "audited": True}
            save_pending_result(user_id, pending)
        render_results(audit, locked=False)

# ── NIS2 Quick Check result ───────────────────────────────────────────────
if answers is not None:
    if funnel.has_site(pending):
        st.divider()
    st.subheader(tr("NIS2 Quick Check"))
    render_quiz_score(answers)
    render_quiz_breakdown(answers, locked=False)
    if client:
        st.caption(
            f"Your answers are recorded in **{client['company_name']}**'s obligations "
            "register as your own declarations. A full assessment replaces them."
        )

# ── GDPR Quick Check result (D-137) ───────────────────────────────────────
if gdpr_answers is not None:
    if funnel.has_site(pending) or answers is not None:
        st.divider()
    st.subheader(tr("GDPR Quick Check"))
    render_quiz_score(gdpr_answers, funnel.GDPR)
    render_quiz_breakdown(gdpr_answers, locked=False, kind=funnel.GDPR)
    if client:
        st.caption(
            f"Your answers are recorded in **{client['company_name']}**'s obligations "
            "register as your own declarations. A full assessment replaces them."
        )

# ── AI Act Quick Check result (S55) ───────────────────────────────────────
if ai_answers is not None:
    if funnel.has_site(pending) or answers is not None or gdpr_answers is not None:
        st.divider()
    st.subheader(tr("AI Act Quick Check"))
    render_quiz_score(ai_answers, funnel.AI_ACT)
    render_quiz_breakdown(ai_answers, locked=False, kind=funnel.AI_ACT)
    if client:
        st.caption(
            f"Your answers are recorded in **{client['company_name']}**'s obligations "
            "register as your own declarations. A full assessment replaces them."
        )

# ── The checks not taken yet ──────────────────────────────────────────────
# D-133: offered, not pushed — a quiet line under the results; each opens in
# place, and its result is added to this page and emailed like the others.
if funnel.missing_checks(pending):
    st.write("")
    st.caption(tr("**Complete your picture** — also free, added to this page and sent to you"))
if not funnel.has_site(pending):
    with st.expander(tr("🌐 Website check — 30 seconds")):
        _add_site("app_site_more")
if gdpr_answers is None:
    with st.expander(tr("🔐 GDPR Quick Check — 2 minutes")):
        _add_gdpr("app_gdpr_more")
if answers is None:
    with st.expander(tr("🛡️ NIS2 Quick Check — 3 minutes")):
        _add_quiz("app_quiz_more")
if ai_answers is None:
    with st.expander(tr("🤖 AI Act Quick Check — 2 minutes")):
        _add_ai("app_ai_more")

# The emailed copy (S49 part 2): sent once per check, to a confirmed account
# — here or by monitor_funnel.py, whichever comes first. D-133: also a check
# taken on this page, or brought by "Log in instead": deliver() reads the
# profile too, and a delivery starts whenever a check is not sent yet.
#
# In a background thread, not in the page run: re-checking the site, the PDF
# and the send take 10–15 s, and a rerun in that time (any click) stopped
# the script silently — no error, no log, no email (found in the live test,
# 26 Oct). The thread finishes regardless and logs its result.
import threading
import funnel_delivery as FD


def _deliver_in_background(uid: str) -> None:
    try:
        from database import get_supabase_admin
        u = get_supabase_admin().auth.admin.get_user_by_id(uid).user
        print(f"free check delivery {uid}: {FD.deliver(u)}")
    except Exception as e:
        print(f"free check delivery {uid}: failed — {e}")


_meta = getattr(st.session_state.user, "user_metadata", None) or {}
_due = FD.unsent(_meta, pending, email)
if _due:
    # Keyed by what is due, so a check added later starts its own delivery
    # (the metadata in the session is the one read at login).
    _flag = f"delivery_started_{user_id}_{'_'.join(_due)}"
    if not st.session_state.get(_flag):
        st.session_state[_flag] = True
        threading.Thread(target=_deliver_in_background, args=(user_id,), daemon=True).start()
    st.success("A copy is on its way to your inbox" + (" — the website report as a PDF."
               if funnel.TOOL_WEBSITE in _due else ".")
               + " If it doesn't arrive within a few minutes, check your spam folder.")

st.divider()
render_trial_cta(profile)

# Last, so the result and the next step are on screen first: each response
# is a few round trips. Idempotent — an interrupted run is finished on the
# next visit, and nothing the client already recorded is overwritten.
# One flag per check: the AI Act answers may come later than the NIS2 ones.
for _ans, _kind, _flag in ((answers, funnel.NIS2, "applied_to"),
                           (ai_answers, funnel.AI_ACT, "ai_applied_to"),
                           (gdpr_answers, funnel.GDPR, "gdpr_applied_to")):
    if _ans is None or not client or pending.get(_flag) == client["id"]:
        continue
    import obligation_store as STORE
    existing = STORE.load_responses(client["id"], user_id)
    for ob_id, status in funnel.declared_responses(_ans, _kind).items():
        if ob_id not in existing:
            STORE.save_response(
                user_id, client["id"], ob_id, status=status,
                statement_en=f"Self-declared in the {_kind['name']}.",
            )
    pending = {**pending, _flag: client["id"]}
    save_pending_result(user_id, pending)
