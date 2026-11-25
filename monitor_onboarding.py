"""
monitor_onboarding.py — D-212. Sends the onboarding emails (flow 1): run
hourly by cron (deploy/crontab). Each run looks at every account on trial,
works out its five setup steps and its trial day, and sends at most one
email per account (onboarding.next_email decides which).

    python monitor_onboarding.py            # send
    python monitor_onboarding.py --dry-run  # print what would be sent, send nothing

Left out: admins, test accounts (signup_source "test"), people who used the
"stop these emails" link, and accounts with no owner email. Sent to the
account's owner only, in their language. Each send is recorded in
lifecycle_emails, so nothing goes out twice.
"""

import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import onboarding as OB
import onboarding_emails as OE
from database import TRIAL_DAYS, get_supabase_admin
from email_sender import _lang, send_lifecycle_email


def _ts(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def run(dry_run: bool = False) -> None:
    import os
    sb = get_supabase_admin()
    now = datetime.now(timezone.utc)
    base_url = (os.environ.get("APP_BASE_URL") or "https://app.recosa.eu").rstrip("/")

    accounts = sb.table("accounts").select("id, owner_user_id, trial_ends_at, status") \
        .eq("status", "trial").execute().data or []
    print(f"{now:%Y-%m-%d %H:%M} — {len(accounts)} account(s) on trial")
    for acc in accounts:
        try:
            ends = _ts(acc.get("trial_ends_at"))
            if not (ends and acc.get("owner_user_id")):
                continue
            day = OB.trial_day(ends, now, TRIAL_DAYS)
            if day >= OB.FLOW_END_DAY:
                continue
            owner = (sb.table("profiles").select(
                "id, email, ui_language, role, signup_source, lifecycle_emails_off_at")
                .eq("id", acc["owner_user_id"]).limit(1).execute().data or [None])[0]
            if (not owner or not owner.get("email") or owner.get("role") == "admin"
                    or owner.get("signup_source") == "test" or owner.get("lifecycle_emails_off_at")):
                continue
            sent = {r["email_key"]: _ts(r["sent_at"]) for r in (
                sb.table("lifecycle_emails").select("email_key, sent_at")
                .eq("account_id", acc["id"]).eq("flow", OB.FLOW).execute().data or [])}
            client = (sb.table("clients").select("id, company_name, legal_name, contact_email")
                      .eq("account_id", acc["id"]).order("created_at").limit(1)
                      .execute().data or [None])[0]
            done = OB.step_status(sb, client)
            key = OB.next_email(day, sent, now, all(done.values()))
            if not key:
                continue
            email = OE.compose(
                key, lang=_lang(owner.get("ui_language")), base_url=base_url,
                stop_url=f"{base_url}/?stop_emails={OB.stop_token(owner['id'])}",
                company=(client or {}).get("company_name"), done=done)
            detail = OB.first_pending(done) if key in OB.STEP_EMAILS + ("wrapup",) else None
            line = f"  day {day} · {owner['email']} · {key}{f' ({detail})' if detail else ''} · {email.subject}"
            if dry_run:
                print("  [dry run]" + line)
                continue
            if send_lifecycle_email(owner["email"], email.subject, email.text, email.html, email.sender):
                sb.table("lifecycle_emails").insert({
                    "account_id": acc["id"], "user_id": owner["id"], "flow": OB.FLOW,
                    "email_key": key, "detail": detail}).execute()
                print("  sent" + line)
            else:
                print("  NOT sent" + line)
        except Exception as e:
            print(f"  account {acc.get('id')}: {e}")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
