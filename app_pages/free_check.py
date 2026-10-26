"""
pages/free_check.py — S49 (D-115). A free account's own page: the full
result of the free check it signed up with, and the way to the trial.

The result comes from profiles.pending_result, written at signup from the
link the public app's CTA carried (?quiz= / ?site=), so it survives email
confirmation and a different browser. An account that signed up without a
check can take either one here.

The quiz answers are also written to the obligation register as DECLARED
answers — the lowest precedence (obligation_register.py), so any analysis,
document or derivation overrides them — and only where the client has
recorded nothing for that obligation yet.
"""

import streamlit as st

import funnel
from funnel_ui import render_quiz_form, render_quiz_score, render_quiz_breakdown
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

st.title("Your free check")


def _store(result: dict) -> None:
    save_pending_result(user_id, result)
    st.rerun()


# ── No check yet: take one here ───────────────────────────────────────────
if pending.get("tool") not in (funnel.TOOL_QUIZ, funnel.TOOL_WEBSITE):
    st.caption("Take one of the two free checks to see where you stand.")
    tab_quiz, tab_site = st.tabs(["🛡️ NIS2 Quick Check", "🌐 GDPR website check"])
    with tab_quiz:
        answers = render_quiz_form("app_quiz")
        if answers is not None:
            _store({"tool": funnel.TOOL_QUIZ, "answers": funnel.encode_answers(answers)})
    with tab_site:
        with st.form("app_site"):
            url = st.text_input("Website", value=(client or {}).get("website_url") or "",
                                placeholder="https://yourcompany.com")
            if st.form_submit_button("Check my website", type="primary"):
                from crawler import extract_domain, normalise_url
                pend = funnel.pending_from_params(None, extract_domain(normalise_url(url)))
                if pend:
                    _store(pend)
                else:
                    st.error("Please enter a valid website address.")
    st.stop()

# ── NIS2 Quick Check result ───────────────────────────────────────────────
if pending["tool"] == funnel.TOOL_QUIZ:
    answers = funnel.decode_answers(pending.get("answers"))
    if answers is None:
        _store(None)
    render_quiz_score(answers)
    render_quiz_breakdown(answers, locked=False)

    if client:
        st.caption(
            f"Your answers are recorded in **{client['company_name']}**'s obligations "
            "register as your own declarations. A full assessment replaces them."
        )

# ── Website check result ──────────────────────────────────────────────────
else:
    import funnel_delivery as FD
    site = pending.get("site")
    email = st.session_state.user.email
    # S49 part 2 (D-119): own site only — an address at its domain, or the
    # site proven this account's (meta tag or DNS TXT).
    proven = FD.site_proven(email, pending)
    key = f"free_check_{site}"
    if key not in st.session_state:
        from crawler import crawl
        from checklist import run_checklist
        with st.spinner(f"Checking {site}…"):
            crawl_result = crawl(site)
        if crawl_result.error:
            st.error(crawl_result.error)
            st.stop()
        st.session_state[key] = (run_checklist(crawl_result), crawl_result.url)
    audit, site_url = st.session_state[key]
    st.subheader(f"Website check — {site}")

    if not proven:
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
            if st.button("Verify the site", type="primary", key="verify_site"):
                with st.spinner("Looking for it…"):
                    ok, how = FD.check_site(site, token)
                if ok:
                    save_pending_result(user_id, {**pending, "site_verified": True, "verified_by": how})
                    st.rerun()
                st.error("Not found yet. Check the tag is on the homepage itself, or wait for the "
                         "DNS record to spread (it can take an hour), then try again.")
    else:
        if not pending.get("audited"):
            save_audit(
                email=email, email_domain=email.split("@")[-1].lower(),
                website_url=site_url, audit_result=audit,
                user_id=user_id, client_id=(client or {}).get("id"),
                site_domain=site,
            )
            save_pending_result(user_id, {**pending, "audited": True})
        render_results(audit, locked=False)

# The emailed copy (S49 part 2): sent once, to a confirmed account whose
# free check came from the public form — here or by monitor_funnel.py,
# whichever comes first.
import funnel_delivery as FD
_res = None
if FD.eligible(st.session_state.user.email, pending if pending["tool"] == funnel.TOOL_QUIZ
               else {**pending, "site_verified": FD.site_proven(st.session_state.user.email, pending)}):
    try:
        from database import get_supabase_admin
        _user = get_supabase_admin().auth.admin.get_user_by_id(user_id).user
        if FD.pending_of(_user.user_metadata):
            with st.spinner("Sending your copy by email…"):
                _res = FD.deliver(_user)
    except Exception as e:
        print(f"free check delivery: {e}")
if _res == "sent":
    st.success("A copy has been emailed to you" + (" — the full report as a PDF."
               if pending["tool"] == funnel.TOOL_WEBSITE else "."))
elif _res == "already":
    st.caption("A copy has already been emailed to you.")

st.divider()
render_trial_cta(profile)

# Last, so the result and the next step are on screen first: each response
# is a few round trips. Idempotent — an interrupted run is finished on the
# next visit, and nothing the client already recorded is overwritten.
if pending["tool"] == funnel.TOOL_QUIZ and client and pending.get("applied_to") != client["id"]:
    import obligation_store as STORE
    existing = STORE.load_responses(client["id"], user_id)
    for ob_id, status in funnel.declared_responses(answers).items():
        if ob_id not in existing:
            STORE.save_response(
                user_id, client["id"], ob_id, status=status,
                statement_en="Self-declared in the NIS2 Quick Check.",
            )
    save_pending_result(user_id, {**pending, "applied_to": client["id"]})
