"""
RECOSA Incident Reminders — S53 (D-117)

Hourly. For every incident not yet closed, works out its deadlines with the
same rules the page uses (incident_rules.py) and emails the account when one
is under DUE_SOON_HOURS away ('soon') or has passed ('overdue') — once per
deadline and stage, recorded as a 'reminder' event on the incident so the
next run does not send it again.

Recipients: the person who logged the incident and the client's owner,
de-duplicated. The email says only that a clock is running; what happened
stays in RECOSA.

Run via GitHub Actions cron (.github/workflows/incident_reminders.yml) or
manually. Same skeleton as monitor_audits.py: service-role client only,
print() for logging, per-incident try/except-and-continue. No monitor_runs
row: an hourly job would add 24 rows a day saying nothing happened.
"""

from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

import incident_rules as R
from database import get_supabase_admin
from email_sender import send_incident_reminder


def _rows(table: str, **eq) -> list[dict]:
    q = get_supabase_admin().table(table).select("*")
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.execute().data or []


def run(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    sb = get_supabase_admin()
    incidents = sb.table("incidents").select("*").neq("status", "closed").execute().data or []
    print(f"RECOSA Incident Reminders — {now:%Y-%m-%d %H:%M} UTC — {len(incidents)} open incident(s)")
    sent = errors = 0

    clients: dict[str, dict] = {}
    contexts: dict[str, dict] = {}
    emails: dict[str, str] = {}

    def email_of(uid: str | None) -> str | None:
        if uid and uid not in emails:
            p = sb.table("profiles").select("email").eq("id", uid).execute().data or []
            emails[uid] = (p[0].get("email") if p else None) or ""
        return emails.get(uid) or None

    for inc in incidents:
        try:
            cid = inc["client_id"]
            if cid not in clients:
                clients[cid] = (_rows("clients", id=cid) or [{}])[0]
                contexts[cid] = {
                    "activities": _rows("processing_activities", client_id=cid),
                    "activity_systems": _rows("activity_systems", client_id=cid),
                    "activity_counterparties": _rows("activity_counterparties", client_id=cid),
                    "counterparties": _rows("processing_counterparties", client_id=cid),
                }
            client = clients[cid]
            events = _rows("incident_events", incident_id=inc["id"])
            done = {e.get("body") for e in events if e["event_type"] == "reminder"}
            processor = bool(R.affected_controllers(inc.get("system_ids") or [], **contexts[cid]))

            due = []
            for d in R.deadlines(inc, client, events, processor, now):
                stage = R.reminder_stage(d)
                tag = f"{d['kind']}:{stage}"
                if stage and tag not in done:
                    due.append((d, stage, tag))
            if not due:
                continue

            to = sorted({e for e in (email_of(inc.get("user_id")), email_of(client.get("user_id"))) if e})
            if not to:
                print(f"  {inc['id']}: no recipient email, skipped")
                continue
            overdue = any(s == "overdue" for _, s, _ in due)
            ok = send_incident_reminder(
                to, client.get("company_name") or "", inc["title"],
                [(R.LABELS["en"][d["kind"]], R.describe_left(d, "en")) for d, _, _ in due],
                overdue,
            )
            if not ok:
                errors += 1
                continue
            for d, stage, tag in due:
                sb.table("incident_events").insert({
                    "incident_id": inc["id"], "client_id": cid, "user_id": None,
                    "event_type": "reminder", "kind": d["kind"], "body": tag,
                }).execute()
            sent += 1
            print(f"  {inc['id']}: reminded {len(to)} recipient(s) about {[t for _, _, t in due]}")
        except Exception as e:
            errors += 1
            print(f"  {inc.get('id')}: failed — {e}")

    print(f"Done: {sent} email(s) sent, {errors} error(s).")
    return {"sent": sent, "errors": errors}


if __name__ == "__main__":
    run()
