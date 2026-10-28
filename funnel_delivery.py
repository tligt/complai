"""
funnel_delivery.py — S49 part 2 (D-119). The free check's full result,
delivered once the address is confirmed.

The public app's one form creates the free account and puts what it knows on
the account itself, as Supabase user metadata (no database change):

    recosa_pending           {"tool": …, "answers": "0123…", "site": "acme.be",
                             "scope": "medium.food.yes.no"} — the checks taken,
                             one or both (D-129), and the scope answers
    recosa_source            where the visitor came from (the link's src, or
                             the first check)
    recosa_marketing         True if the box was ticked
    recosa_consent_version   funnel.CONSENT_VERSION when it was
    recosa_quiz_sent /       set here once that result has been emailed
    recosa_site_sent
    recosa_report_sent       set once everything carried has been emailed

Two callers, whichever comes first, and the flag stops a second email:
  - the client app, on first login (the account is confirmed by then);
  - monitor_funnel.py, every 15 minutes, for confirmed accounts that have
    not logged in — the form promised the PDF, not a login.

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
    at signup, so re-validated here). Since D-129 it may hold both checks."""
    p = (metadata or {}).get("recosa_pending") or {}
    return funnel.pending_from_params(p.get("answers"), p.get("site"), p.get("scope"))


def site_proven(email: str, pending: dict) -> bool:
    """The website report may go to this address: same domain, or proven."""
    return bool(pending.get("site_verified")) or funnel.domains_match(email, pending.get("site") or "")


def eligible(email: str, pending: dict | None) -> bool:
    """Something can be sent now: the quiz result always, the website report
    once the site is proven."""
    if not pending:
        return False
    return funnel.has_quiz(pending) or (funnel.has_site(pending) and site_proven(email, pending))


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


def _base_url() -> str:
    import os
    return (os.environ.get("APP_BASE_URL") or "").rstrip("/") + "/"


def send_quiz(email: str, pending: dict) -> bool:
    from email_sender import send_quiz_result
    return send_quiz_result(email, funnel.decode_answers(pending["answers"]), _base_url())


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
    )


def deliver(user) -> str:
    """Send this confirmed account whatever is due. Returns what happened:
    'sent', 'already', 'not_confirmed', 'none', 'not_proven', 'failed'.
    `user` is a Supabase admin User object."""
    from database import get_supabase_admin, record_funnel_event
    meta = dict(user.user_metadata or {})
    if meta.get(ALL_SENT):
        return "already"
    if not getattr(user, "email_confirmed_at", None):
        return "not_confirmed"
    pending = pending_of(meta)
    if not pending:
        return "none"
    # The proof is recorded on the profile (the app writes it there).
    admin = get_supabase_admin()
    prof = (admin.table("profiles").select("pending_result").eq("id", user.id)
            .execute().data or [{}])[0]
    if (prof.get("pending_result") or {}).get("site_verified"):
        pending["site_verified"] = True

    now = datetime.now(timezone.utc).isoformat()
    sent, failed, waiting = [], False, False
    parts = []
    if funnel.has_quiz(pending):
        parts.append((QUIZ_SENT, funnel.TOOL_QUIZ, send_quiz, True))
    if funnel.has_site(pending):
        parts.append((SITE_SENT, funnel.TOOL_WEBSITE, send_site,
                      site_proven(user.email, pending)))
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
        meta[ALL_SENT] = now
    if sent:
        admin.auth.admin.update_user_by_id(user.id, {"user_metadata": meta})

    # The lead record, one per check sent: consent as given at signup,
    # linked to the account.
    for tool in sent:
        try:
            admin.table("leads").insert({
                "tool": tool, "email": user.email.lower(),
                "answers": pending.get("answers") if tool == funnel.TOOL_QUIZ else None,
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
