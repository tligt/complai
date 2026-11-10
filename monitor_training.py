"""
RECOSA Training Reminders — S60 (D-159)

Weekly. For every company with people on its training register, works out
the same matrix the Training page shows (training_rules.py) and, when someone
is not trained, has lapsed, or lapses within EXPIRING_DAYS, emails the
company's owner a content-free nudge — at most once every NUDGE_DAYS,
recorded in clients.training_nudged_at.

Run via GitHub Actions cron (.github/workflows/training_reminders.yml) or
manually. Same skeleton as monitor_incidents.py: service-role client only,
print() for logging, per-company try/except-and-continue.
"""

from datetime import date, datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

import training_rules as TR
from database import get_supabase_admin
from email_sender import send_training_nudge

NUDGE_DAYS = 30


def run(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    sb = get_supabase_admin()
    reqs = [TR.requirement(r) for r in
            (sb.table("reference_values").select("*").eq("value_type", "training_requirement")
             .eq("active", True).is_("workspace_id", "null").execute().data or [])]
    client_ids = sorted({r["client_id"] for r in
                         (sb.table("employees").select("client_id").execute().data or [])})
    print(f"RECOSA Training Reminders — {now:%Y-%m-%d %H:%M} UTC — {len(client_ids)} company(ies)")
    sent = errors = 0

    for cid in client_ids:
        try:
            client = (sb.table("clients").select("*").eq("id", cid).execute().data or [{}])[0]
            last = client.get("training_nudged_at")
            if last and datetime.fromisoformat(str(last).replace("Z", "+00:00")) > now - timedelta(days=NUDGE_DAYS):
                continue
            applicable = [r for r in TR.applicable(reqs, client) if TR.in_force(r, today)]
            employees = sb.table("employees").select("*").eq("client_id", cid).execute().data or []
            active = [e for e in employees if TR.is_active(e, today)]
            if not applicable or not active:
                continue
            sessions = sb.table("training_sessions").select("*").eq("client_id", cid).execute().data or []
            attendance = (sb.table("training_attendance").select("session_id, employee_id")
                          .eq("client_id", cid).execute().data or [])
            cov = TR.coverage(TR.matrix(active, applicable, sessions, attendance, today), applicable)
            if not TR.needs_attention(cov):
                continue
            p = sb.table("profiles").select("email").eq("id", client.get("user_id")).execute().data or []
            to = (p[0].get("email") if p else None) or ""
            if not to:
                print(f"  {cid}: no owner email, skipped")
                continue
            if not send_training_nudge(to):
                errors += 1
                continue
            sb.table("clients").update({"training_nudged_at": now.isoformat()}).eq("id", cid).execute()
            sent += 1
            print(f"  {cid}: nudged")
        except Exception as e:
            errors += 1
            print(f"  {cid}: failed — {e}")

    print(f"Done: {sent} email(s) sent, {errors} error(s).")
    return {"sent": sent, "errors": errors}


if __name__ == "__main__":
    run()
