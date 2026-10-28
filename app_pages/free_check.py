"""
pages/free_check.py — S49 (D-115). A free account's own page: the full
result of the free checks it signed up with, and the way to the trial.

The result comes from profiles.pending_result, written at signup from the
link the public app's CTA carried (?quiz= / ?site= / ?scope=), so it
survives email confirmation and a different browser. Since D-129 it may hold
both checks, and the scope answers; a check not taken yet can be taken
here, and is added to the same result.

The quiz answers are also written to the obligation register as DECLARED
answers — the lowest precedence (obligation_register.py), so any analysis,
document or derivation overrides them — and only where the client has
recorded nothing for that obligation yet.
"""

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

st.title("Your free check")


def _store(result: dict | None) -> None:
    save_pending_result(user_id, result)
    st.rerun()


def _add_quiz(key: str) -> None:
    answers = render_quiz_form(key)
    if answers is not None:
        _store({**pending, "tool": pending.get("tool") or funnel.TOOL_QUIZ,
                "answers": funnel.encode_answers(answers)})


def _add_site(key: str) -> None:
    with st.form(key):
        url = st.text_input("Website", value=(client or {}).get("website_url") or "",
                            placeholder="https://yourcompany.com")
        if st.form_submit_button("Check my website", type="primary"):
            from crawler import extract_domain, normalise_url
            pend = funnel.pending_from_params(None, extract_domain(normalise_url(url)))
            if pend:
                _store({**pending, "tool": pending.get("tool") or funnel.TOOL_WEBSITE,
                        "site": pend["site"]})
            else:
                st.error("Please enter a valid website address.")


# ── No check yet: take one here ───────────────────────────────────────────
if not (funnel.has_quiz(pending) or funnel.has_site(pending)):
    st.caption("Take one of the two free checks to see where you stand.")
    tab_site, tab_quiz = st.tabs(["🌐 Website check", "🛡️ NIS2 Quick Check"])
    with tab_site:
        _add_site("app_site")
    with tab_quiz:
        _add_quiz("app_quiz")
    st.stop()

scope = funnel.decode_scope(pending.get("scope"))
if scope:
    with st.container(border=True):
        st.markdown("**The rules that apply to you** — a first indication from your answers")
        render_rules(funnel.applicable_rules(scope))

# ── Website check result ──────────────────────────────────────────────────
answers = funnel.decode_answers(pending.get("answers"))
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
            pending = {**pending, "audited": True}
            save_pending_result(user_id, pending)
        render_results(audit, locked=False)

# ── NIS2 Quick Check result ───────────────────────────────────────────────
if answers is not None:
    if funnel.has_site(pending):
        st.divider()
    st.subheader("NIS2 Quick Check")
    render_quiz_score(answers)
    render_quiz_breakdown(answers, locked=False)
    if client:
        st.caption(
            f"Your answers are recorded in **{client['company_name']}**'s obligations "
            "register as your own declarations. A full assessment replaces them."
        )

# ── The check not taken yet ───────────────────────────────────────────────
if not funnel.has_site(pending):
    with st.expander("🌐 Also check your website — 30 seconds"):
        _add_site("app_site_more")
elif answers is None:
    with st.expander("🛡️ Also take the NIS2 Quick Check — 2 minutes"):
        _add_quiz("app_quiz_more")

# The emailed copy (S49 part 2): sent once per check, to a confirmed account
# whose free check came from the public form — here or by monitor_funnel.py,
# whichever comes first.
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
        if FD.pending_of(u.user_metadata):
            print(f"free check delivery {uid}: {FD.deliver(u)}")
    except Exception as e:
        print(f"free check delivery {uid}: failed — {e}")


if FD.eligible(email, {**pending, "site_verified": FD.site_proven(email, pending)}):
    _meta = getattr(st.session_state.user, "user_metadata", None) or {}
    if _meta.get("recosa_pending"):
        _flag = f"delivery_started_{user_id}"
        if not st.session_state.get(_flag):
            st.session_state[_flag] = True
            threading.Thread(target=_deliver_in_background, args=(user_id,), daemon=True).start()
        st.success("A copy is on its way to your inbox" + (" — the website report as a PDF."
                   if funnel.has_site(pending) and FD.site_proven(email, pending) else ".")
                   + " If it doesn't arrive within a few minutes, check your spam folder.")

st.divider()
render_trial_cta(profile)

# Last, so the result and the next step are on screen first: each response
# is a few round trips. Idempotent — an interrupted run is finished on the
# next visit, and nothing the client already recorded is overwritten.
if answers is not None and client and pending.get("applied_to") != client["id"]:
    import obligation_store as STORE
    existing = STORE.load_responses(client["id"], user_id)
    for ob_id, status in funnel.declared_responses(answers).items():
        if ob_id not in existing:
            STORE.save_response(
                user_id, client["id"], ob_id, status=status,
                statement_en="Self-declared in the NIS2 Quick Check.",
            )
    save_pending_result(user_id, {**pending, "applied_to": client["id"]})
