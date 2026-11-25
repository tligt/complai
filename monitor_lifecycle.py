"""
monitor_lifecycle.py — D-212/D-213. Sends the lifecycle emails of accounts on
trial: onboarding (flow 1, days 0–9, onboarding.py) and trial ending
(flow 2, days 10–13, trial_ending.py). Run hourly by cron (deploy/crontab).
Was monitor_onboarding.py.

    python monitor_lifecycle.py            # send
    python monitor_lifecycle.py --dry-run  # print what would be sent, send nothing

At most one email per account per run, and none within 20 hours of the
last lifecycle email of any flow. Left out: admins, test accounts
(signup_source "test"), people who used the "stop these emails" link, and
accounts with no owner email. Sent to the account's owner only, in their
language; each send is recorded in lifecycle_emails, so nothing goes out
twice.
"""

import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import onboarding as OB
import onboarding_emails as OE
import trial_ending as TE
import trial_ending_emails as TEE
from database import TRIAL_DAYS, get_supabase_admin
from email_sender import _lang, send_lifecycle_email


def _ts(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def run(dry_run: bool = False) -> None:
    sb = get_supabase_admin()
    now = datetime.now(timezone.utc)
    base_url = (os.environ.get("APP_BASE_URL") or "https://app.recosa.eu").rstrip("/")

    accounts = sb.table("accounts").select("id, owner_user_id, trial_ends_at, status") \
        .eq("status", "trial").execute().data or []
    print(f"{now:%Y-%m-%d %H:%M} — {len(accounts)} account(s) on trial")
    for acc in accounts:
        try:
            ends = _ts(acc.get("trial_ends_at"))
            if not (ends and acc.get("owner_user_id")) or ends <= now:
                continue
            day = OB.trial_day(ends, now, TRIAL_DAYS)
            owner = (sb.table("profiles").select(
                "id, email, ui_language, role, signup_source, lifecycle_emails_off_at")
                .eq("id", acc["owner_user_id"]).limit(1).execute().data or [None])[0]
            if (not owner or not owner.get("email") or owner.get("role") == "admin"
                    or owner.get("signup_source") == "test" or owner.get("lifecycle_emails_off_at")):
                continue

            rows = sb.table("lifecycle_emails").select("flow, email_key, sent_at") \
                .eq("account_id", acc["id"]).execute().data or []
            if rows and now - max(_ts(r["sent_at"]) for r in rows) < OB.MIN_GAP:
                continue
            sent_by_flow: dict[str, dict] = {}
            for r in rows:
                sent_by_flow.setdefault(r["flow"], {})[r["email_key"]] = _ts(r["sent_at"])

            client = (sb.table("clients").select("id, company_name, legal_name, contact_email")
                      .eq("account_id", acc["id"]).order("created_at").limit(1)
                      .execute().data or [None])[0]
            lang = _lang(owner.get("ui_language"))
            stop_url = f"{base_url}/?stop_emails={OB.stop_token(owner['id'])}"
            company = (client or {}).get("company_name")

            flow, key, detail, email = None, None, None, None
            if day < OB.FLOW_END_DAY:
                done = OB.step_status(sb, client)
                key = OB.next_email(day, sent_by_flow.get(OB.FLOW, {}), now, all(done.values()))
                if key:
                    flow = OB.FLOW
                    detail = OB.first_pending(done) if key in OB.STEP_EMAILS + ("wrapup",) else None
                    email = OE.compose(key, lang=lang, base_url=base_url, stop_url=stop_url,
                                       company=company, done=done)
            else:
                key = TE.next_email(day, set(sent_by_flow.get(TE.FLOW, {})))
                if key:
                    flow = TE.FLOW
                    figs = TE.figures(sb, client) if key == "four_days" else {}
                    detail = ", ".join(f"{k}={v}" for k, v in figs.items() if v) or None
                    email = TEE.compose(key, lang=lang, base_url=base_url, stop_url=stop_url,
                                        company=company, ends_at=ends, figures=figs)
            if not email:
                continue

            line = (f"  day {day} · {owner['email']} · {flow}/{key}"
                    f"{f' ({detail})' if detail else ''} · {email.subject}")
            if dry_run:
                print("  [dry run]" + line)
                continue
            if send_lifecycle_email(owner["email"], email.subject, email.text, email.html, email.sender):
                sb.table("lifecycle_emails").insert({
                    "account_id": acc["id"], "user_id": owner["id"], "flow": flow,
                    "email_key": key, "detail": detail}).execute()
                print("  sent" + line)
            else:
                print("  NOT sent" + line)
        except Exception as e:
            print(f"  account {acc.get('id')}: {e}")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
