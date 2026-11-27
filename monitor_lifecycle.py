"""
monitor_lifecycle.py — D-212/D-213/D-214. Sends the lifecycle emails, run
hourly by cron (deploy/crontab). Was monitor_onboarding.py.

    on trial   days 0–9    onboarding      (flow 1, onboarding.py)
               days 10–13  trial ending    (flow 2, trial_ending.py)
    expired    days 0–59   expired trial   (flow 3, expired_trial.py), from the trial's end
               day 60      deleted         (D-222, account_deletion.py), then a last email

    python monitor_lifecycle.py            # send
    python monitor_lifecycle.py --dry-run  # print what would be sent, send or change nothing

A trial past its end is switched to 'expired' here (D-214): the app only did
it at the owner's next login, so an owner who never came back stayed "on
trial" for ever, in the back office too.

At most one email per account per run, and none within 20 hours of the last
lifecycle email of any flow. Left out: admins, test accounts (signup_source
"test") and accounts with no owner email. The "stop these emails" link stops
every email here except the access and deletion notices (flow 3), which
concern the service itself; so does an address on email_suppressions (kept
after a deletion). Sent to the account's owner only, in their language; each
send is recorded in lifecycle_emails, so nothing goes out twice.
"""

import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import account_deletion as AD
import expired_trial as ET
import expired_trial_emails as ETE
import onboarding as OB
import onboarding_emails as OE
import trial_ending as TE
import trial_ending_emails as TEE
from database import TRIAL_DAYS, expire_account_trial_if_due, get_supabase_admin
from email_sender import _lang, send_lifecycle_email


def _ts(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def run(dry_run: bool = False) -> None:
    sb = get_supabase_admin()
    now = datetime.now(timezone.utc)
    base_url = (os.environ.get("APP_BASE_URL") or "https://app.recosa.eu").rstrip("/")

    accounts = sb.table("accounts").select("*").in_("status", ["trial", "expired"]) \
        .execute().data or []
    print(f"{now:%Y-%m-%d %H:%M} — {len(accounts)} account(s) on trial or expired")
    for acc in accounts:
        try:
            ends = _ts(acc.get("trial_ends_at"))
            if not (ends and acc.get("owner_user_id")):
                continue
            status = acc["status"]
            if status == "trial" and ends <= now:
                if dry_run:
                    print(f"  [dry run] would switch account {acc['id']} to expired")
                else:
                    expire_account_trial_if_due(acc)
                    print(f"  switched account {acc['id']} to expired (trial ended {ends:%d %b})")
                status = "expired"

            owner = (sb.table("profiles").select(
                "id, email, ui_language, role, signup_source, lifecycle_emails_off_at")
                .eq("id", acc["owner_user_id"]).limit(1).execute().data or [None])[0]
            if (not owner or not owner.get("email") or owner.get("role") == "admin"
                    or owner.get("signup_source") == "test"):
                continue
            opted_out = bool(owner.get("lifecycle_emails_off_at")) or bool(
                sb.table("email_suppressions").select("email")
                .eq("email", owner["email"].lower()).limit(1).execute().data)

            rows = sb.table("lifecycle_emails").select("flow, email_key, sent_at") \
                .eq("account_id", acc["id"]).execute().data or []

            # D-222: day 60, every notice sent: delete, then say so.
            if status == "expired" and ET.deletion_due(
                    acc, {r["email_key"] for r in rows if r["flow"] == ET.FLOW}, now, _ts):
                _delete(sb, acc, owner, ends, now, base_url, dry_run)
                continue
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

            flow, key, detail, email, new_dates = None, None, None, None, None
            if status == "trial":
                if opted_out:
                    continue
                day = OB.trial_day(ends, now, TRIAL_DAYS)
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
            else:
                day = ET.days_since(ends, now)
                closes, gone = _ts(acc.get("access_closes_at")), _ts(acc.get("delete_after"))
                key = ET.next_email(day, set(sent_by_flow.get(ET.FLOW, {})), opted_out,
                                    closes, gone, now)
                if key:
                    flow = ET.FLOW
                    if key == "access_closing":
                        # D-222: the dates are fixed by this first notice.
                        closes, gone = ET.plan_dates(ends, now)
                        new_dates = {"access_closes_at": closes.isoformat(),
                                     "delete_after": gone.isoformat()}
                    missed = ET.missed_updates(sb, client, ends) if key == "missing" else (0, 0)
                    detail = (f"updates={missed[0]}, theirs={missed[1]}" if key == "missing"
                              else f"closes {closes:%d %b}, deleted {gone:%d %b}"
                              if key in ET.DELETION_EMAILS else None)
                    email = ETE.compose(key, lang=lang, base_url=base_url, stop_url=stop_url,
                                        company=company, ended_at=ends, now=now, missed=missed,
                                        closes_at=closes, delete_after=gone)
            if not email:
                continue

            line = (f"  day {day} · {owner['email']} · {flow}/{key}"
                    f"{f' ({detail})' if detail else ''} · {email.subject}")
            if dry_run:
                print("  [dry run]" + line)
                continue
            if send_lifecycle_email(owner["email"], email.subject, email.text, email.html, email.sender):
                if new_dates:
                    sb.table("accounts").update(new_dates).eq("id", acc["id"]).execute()
                sb.table("lifecycle_emails").insert({
                    "account_id": acc["id"], "user_id": owner["id"], "flow": flow,
                    "email_key": key, "detail": detail}).execute()
                print("  sent" + line)
            else:
                print("  NOT sent" + line)
        except Exception as e:
            print(f"  account {acc.get('id')}: {e}")


def _delete(sb, acc, owner, ends, now, base_url, dry_run) -> None:
    """D-222: delete an expired trial whose date has come, then email the
    owner that it is done (captured before: the profile goes with it)."""
    client = (sb.table("clients").select("company_name").eq("account_id", acc["id"])
              .order("created_at").limit(1).execute().data or [None])[0]
    company = (client or {}).get("company_name")
    lang = _lang(owner.get("ui_language"))
    if dry_run:
        plan = AD.delete_account(sb, acc["id"], dry_run=True)
        print(f"  [dry run] would delete account {acc['id']} ({owner['email']}, "
              f"{company or 'no company'}, {plan['files']} files)")
        return
    result = AD.delete_account(sb, acc["id"])
    print(f"  DELETED account {acc['id']} ({owner['email']}, {company or 'no company'}): "
          f"{result['files']} files, {result['deleted']}")
    email = ETE.compose("deleted", lang=lang, base_url=base_url, stop_url="", company=company,
                        ended_at=ends, now=now, closes_at=_ts(acc.get("access_closes_at")),
                        delete_after=_ts(acc.get("delete_after")))
    if not send_lifecycle_email(owner["email"], email.subject, email.text, email.html, email.sender):
        print(f"  deletion email NOT sent to {owner['email']}")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
