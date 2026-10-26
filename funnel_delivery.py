"""
funnel_delivery.py — S49 part 2 (D-119). The free check's full result,
delivered once the address is confirmed.

The public app's one form creates the free account and puts what it knows on
the account itself, as Supabase user metadata (no database change):

    recosa_pending           {"tool": "nis2_quiz", "answers": "0123…"} or
                             {"tool": "website_check", "site": "acme.be"}
    recosa_source            nis2_quiz / website_check
    recosa_marketing         True if the box was ticked
    recosa_consent_version   funnel.CONSENT_VERSION when it was
    recosa_report_sent       set here once the result has been emailed

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
    at signup, so re-validated here)."""
    p = (metadata or {}).get("recosa_pending") or {}
    if p.get("tool") == funnel.TOOL_QUIZ:
        return funnel.pending_from_params(p.get("answers"), None)
    if p.get("tool") == funnel.TOOL_WEBSITE:
        return funnel.pending_from_params(None, p.get("site"))
    return None


def site_proven(email: str, pending: dict) -> bool:
    """The website report may go to this address: same domain, or proven."""
    return bool(pending.get("site_verified")) or funnel.domains_match(email, pending.get("site") or "")


def eligible(email: str, pending: dict | None) -> bool:
    if not pending:
        return False
    if pending["tool"] == funnel.TOOL_QUIZ:
        return True
    return site_proven(email, pending)


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

def send_result(email: str, pending: dict) -> bool:
    """Email the full result: the quiz breakdown, or the website report with
    its PDF (the site is checked again now, so the report is current)."""
    import os
    base = (os.environ.get("APP_BASE_URL") or "").rstrip("/") + "/"
    if pending["tool"] == funnel.TOOL_QUIZ:
        from email_sender import send_quiz_result
        return send_quiz_result(email, funnel.decode_answers(pending["answers"]), base)
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
        warn_count=audit.warn_count, fail_count=audit.fail_count, cta_url=base,
    )


def deliver(user) -> str:
    """Send the result to this confirmed account if it is due. Returns what
    happened: 'sent', 'already', 'not_confirmed', 'none', 'not_proven',
    'failed'. `user` is a Supabase admin User object."""
    from database import get_supabase_admin, record_funnel_event
    meta = dict(user.user_metadata or {})
    if meta.get("recosa_report_sent"):
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
    if not eligible(user.email, pending):
        return "not_proven"
    if not send_result(user.email, pending):
        return "failed"
    admin.auth.admin.update_user_by_id(user.id, {"user_metadata": {
        **meta, "recosa_report_sent": datetime.now(timezone.utc).isoformat()}})
    # The lead record: consent as given at signup, linked to the account.
    try:
        admin.table("leads").insert({
            "tool": pending["tool"], "email": user.email.lower(),
            "answers": pending.get("answers"), "site_domain": pending.get("site"),
            "marketing_consent": bool(meta.get("recosa_marketing")),
            "consent_version": meta.get("recosa_consent_version") if meta.get("recosa_marketing") else None,
            "source": meta.get("recosa_source") or "direct",
            "converted_profile_id": user.id,
        }).execute()
    except Exception as e:
        print(f"lead record failed: {e}")
    record_funnel_event("signup", pending["tool"], "confirmed")
    return "sent"
