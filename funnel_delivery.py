"""
funnel_delivery.py — S49 part 2 (D-119). The free check's full result,
delivered once the address is confirmed.

The public app's one form creates the free account and puts what it knows on
the account itself, as Supabase user metadata (no database change):

    recosa_pending           {"tool": …, "answers": "0123…", "site": "acme.be",
                             "ai_answers": "0123…", "gdpr_answers": "0123…",
                             "scope": "medium.food.yes.no"}
                             — the checks taken, any of the three (D-129, S55),
                             and the scope answers
    recosa_source            where the visitor came from (the link's src, or
                             the first check)
    recosa_marketing         True if the box was ticked
    recosa_consent_version   funnel.CONSENT_VERSION when it was
    recosa_quiz_sent /       set here once that result has been emailed
    recosa_site_sent /
    recosa_ai_sent
    recosa_report_sent       set once everything carried has been emailed

Two callers, whichever comes first, and the flag stops a second email:
  - the client app, on first login (the account is confirmed by then);
  - monitor_funnel.py, every 15 minutes, for confirmed accounts that have
    not logged in — the form promised the PDF, not a login.

D-133: a check taken in the client app (Your free check), or brought by the
public app's "Log in instead" link, lives on the profile only, not in the
metadata. deliver() reads both, so those checks are emailed too — by the
app, which starts a delivery whenever a check is not sent yet. Every email
ends with links to the checks not taken yet (FREE_CHECK_URL).

OWN SITE ONLY. The website report is sent only when the address is at the
checked site's domain (S43), or once the site has been proven to be the
account's: a meta tag on its homepage or a DNS TXT record carrying a token
(for a brand site on another domain — iphone.com, email at apple.com).
Paid plans check any site from the Web Audit page.

Service role throughout: called from the app's server side and from the job.
No Streamlit here.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

import funnel

META_NAME = "recosa-site-verification"


# ── Who gets what ─────────────────────────────────────────────────────────

def pending_of(metadata: dict | None) -> dict | None:
    """The validated pending result from user metadata (visitor-controlled
    at signup, so re-validated here). Since D-129 it may hold several checks."""
    p = (metadata or {}).get("recosa_pending") or {}
    return funnel.pending_from_params(p.get("answers"), p.get("site"), p.get("scope"),
                                      p.get("ai_answers"), p.get("gdpr_answers"))


def site_proven(email: str, pending: dict) -> bool:
    """The website report may go to this address: same domain, or proven."""
    return bool(pending.get("site_verified")) or funnel.domains_match(email, pending.get("site") or "")


def eligible(email: str, pending: dict | None) -> bool:
    """Something can be sent now: a quiz result always, the website report
    once the site is proven."""
    if not pending:
        return False
    return (funnel.has_quiz(pending) or funnel.has_ai(pending) or funnel.has_gdpr(pending)
            or (funnel.has_site(pending) and site_proven(email, pending)))


# ── Proving a site is yours ───────────────────────────────────────────────

def new_token() -> str:
    return secrets.token_urlsafe(18)


def check_site(site: str, token: str) -> tuple[bool, str]:
    """(verified, how) — the meta tag on the homepage, or a DNS TXT record."""
    from crawler import _get_public  # public addresses only, every hop
    for url in (f"https://{site}", f"https://www.{site}"):
        try:
            html = _get_public(url).text
        except Exception:
            continue
        from bs4 import BeautifulSoup
        tag = BeautifulSoup(html, "html.parser").find("meta", attrs={"name": META_NAME})
        if tag and (tag.get("content") or "").strip() == token:
            return True, "meta tag"
    try:
        import dns.resolver
        for rr in dns.resolver.resolve(site, "TXT", lifetime=8):
            txt = b"".join(rr.strings).decode("utf-8", "ignore").strip()
            if txt == f"{META_NAME}={token}":
                return True, "DNS TXT record"
    except Exception:
        pass
    return False, ""


# ── Sending ───────────────────────────────────────────────────────────────
# One email per check: the quiz breakdown, the website report with its PDF.
# Each has its own flag on the account, so a quiz result goes out at
# confirmation while the website report waits for the site to be proven.
# recosa_report_sent is set once everything the account carries has gone
# (monitor_funnel.py skips the account from then on); an account flagged
# before D-129 carried one check, so that flag alone still means "all sent".

QUIZ_SENT, SITE_SENT, ALL_SENT = "recosa_quiz_sent", "recosa_site_sent", "recosa_report_sent"
AI_SENT = "recosa_ai_sent"  # S55
GDPR_SENT = "recosa_gdpr_sent"  # D-137
_FLAGS = {funnel.TOOL_QUIZ: QUIZ_SENT, funnel.TOOL_WEBSITE: SITE_SENT,  # tool -> flag
          funnel.TOOL_AI: AI_SENT, funnel.TOOL_GDPR: GDPR_SENT}


def _base_url() -> str:
    import os
    return (os.environ.get("APP_BASE_URL") or "").rstrip("/") + "/"


def _more(pending: dict) -> list[tuple[str, str]]:
    """(label, link) for each free check this account has not taken: the
    last line of every result email."""
    import os
    base = os.environ.get("FREE_CHECK_URL") or "https://recosa-checklist.streamlit.app"
    out = []
    for tool in funnel.missing_checks(pending):
        name, time = funnel.CHECK_NAMES[tool]
        out.append((f"{name} ({time})", funnel.check_url(base, tool, src="email")))
    return out


def unsent(meta: dict | None, pending: dict | None, email: str) -> list[str]:
    """The checks due now and not emailed yet, by the flags in `meta`."""
    meta = meta or {}
    if not pending:
        return []
    legacy = _legacy_sent(meta)
    out = []
    for tool, flag in _FLAGS.items():
        if not funnel.has_check(pending, tool) or meta.get(flag) or tool in legacy:
            continue
        if tool == funnel.TOOL_WEBSITE and not site_proven(email, pending):
            continue
        out.append(tool)
    return out


def _legacy_sent(meta: dict) -> set[str]:
    """Before D-129 an account carried one check and only recosa_report_sent
    was set once it went: that check counts as sent."""
    if not meta.get(ALL_SENT) or any(meta.get(f) for f in _FLAGS.values()):
        return set()
    p = pending_of(meta) or {}
    return {t for t in funnel.ALL_CHECKS if funnel.has_check(p, t)}


def send_quiz(email: str, pending: dict) -> bool:
    from email_sender import send_quiz_result
    return send_quiz_result(email, funnel.decode_answers(pending["answers"]), _base_url(),
                            more=_more(pending))


def send_gdpr(email: str, pending: dict) -> bool:
    from email_sender import send_quiz_result
    return send_quiz_result(email, funnel.decode_answers(pending["gdpr_answers"], funnel.GDPR),
                            _base_url(), kind=funnel.GDPR, more=_more(pending))


def send_ai(email: str, pending: dict) -> bool:
    from email_sender import send_quiz_result
    return send_quiz_result(email, funnel.decode_answers(pending["ai_answers"], funnel.AI_ACT),
                            _base_url(), kind=funnel.AI_ACT, more=_more(pending))


def send_site(email: str, pending: dict) -> bool:
    """The website report with its PDF (the site is checked again now, so the
    report is current)."""
    from crawler import crawl
    from checklist import run_checklist
    from report import generate_pdf
    from email_sender import send_audit_report
    result = crawl(pending["site"])
    if result.error:
        print(f"website report for {pending['site']}: {result.error}")
        return False
    audit = run_checklist(result)
    return send_audit_report(
        to_email=email, website_url=result.url, pdf_bytes=generate_pdf(audit),
        score=audit.score, risk_level=audit.risk_level, ok_count=audit.ok_count,
        warn_count=audit.warn_count, fail_count=audit.fail_count, cta_url=_base_url(),
        more=_more(pending),
    )


def deliver(user) -> str:
    """Send this confirmed account whatever is due. Returns what happened:
    'sent', 'already', 'not_confirmed', 'none', 'not_proven', 'failed'.
    `user` is a Supabase admin User object."""
    from database import get_supabase_admin, record_funnel_event
    meta = dict(user.user_metadata or {})
    if not getattr(user, "email_confirmed_at", None):
        return "not_confirmed"
    admin = get_supabase_admin()
    prof = (admin.table("profiles").select("pending_result").eq("id", user.id)
            .execute().data or [{}])[0]
    prof_p = prof.get("pending_result") or {}
    # D-133: the form's checks (metadata), plus those on the profile only —
    # taken in the app, or brought by "Log in instead". The form's own win
    # where both hold one.
    pending = dict(pending_of(meta) or {})
    extra = funnel.pending_from_params(prof_p.get("answers"), prof_p.get("site"), None,
                                       prof_p.get("ai_answers"), prof_p.get("gdpr_answers")) or {}
    for k in ("answers", "site", "ai_answers", "gdpr_answers"):
        if k in extra and k not in pending:
            pending[k] = extra[k]
    if not any(funnel.has_check(pending, t) for t in funnel.ALL_CHECKS):
        return "none"
    pending.setdefault("tool", extra.get("tool"))
    # The proof is recorded on the profile (the app writes it there).
    if prof_p.get("site_verified") and prof_p.get("site") == pending.get("site"):
        pending["site_verified"] = True
    legacy = _legacy_sent(meta)
    for tool in legacy:
        meta[_FLAGS[tool]] = meta[ALL_SENT]

    now = datetime.now(timezone.utc).isoformat()
    sent, failed, waiting = [], False, False
    parts = []
    if funnel.has_quiz(pending):
        parts.append((QUIZ_SENT, funnel.TOOL_QUIZ, send_quiz, True))
    if funnel.has_site(pending):
        parts.append((SITE_SENT, funnel.TOOL_WEBSITE, send_site,
                      site_proven(user.email, pending)))
    if funnel.has_gdpr(pending):
        parts.append((GDPR_SENT, funnel.TOOL_GDPR, send_gdpr, True))
    if funnel.has_ai(pending):
        parts.append((AI_SENT, funnel.TOOL_AI, send_ai, True))
    for flag, tool, send, due in parts:
        if meta.get(flag):
            continue
        if not due:
            waiting = True
            continue
        if send(user.email, pending):
            meta[flag] = now
            sent.append(tool)
        else:
            failed = True
    if all(meta.get(flag) for flag, *_ in parts):
        meta[ALL_SENT] = meta.get(ALL_SENT) or now
    if sent:
        admin.auth.admin.update_user_by_id(user.id, {"user_metadata": meta})

    # The lead record, one per check sent: consent as given at signup,
    # linked to the account.
    for tool in sent:
        try:
            admin.table("leads").insert({
                "tool": tool, "email": user.email.lower(),
                "answers": (pending.get("answers") if tool == funnel.TOOL_QUIZ else
                            pending.get("ai_answers") if tool == funnel.TOOL_AI else
                            pending.get("gdpr_answers") if tool == funnel.TOOL_GDPR else None),
                "site_domain": pending.get("site") if tool == funnel.TOOL_WEBSITE else None,
                "marketing_consent": bool(meta.get("recosa_marketing")),
                "consent_version": meta.get("recosa_consent_version") if meta.get("recosa_marketing") else None,
                "source": meta.get("recosa_source") or "direct",
                "converted_profile_id": user.id,
            }).execute()
        except Exception as e:
            print(f"lead record failed: {e}")
        record_funnel_event("signup", tool, "confirmed")
    if sent:
        return "sent"
    if failed:
        return "failed"
    return "not_proven" if waiting else "already"
