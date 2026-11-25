"""
RECOSA Compliance Heartbeat — S67 (D-188)

Nightly. For every company: runs heartbeat.py's rules (stale legal holds,
superseded versions nearing deletion, documents not reviewed in a year,
systems tied to no activity), records what opened and closed in the task
history, and emails the company's owner ONE content-free message when there
is something to look at.

    python monitor_heartbeat.py            # the real run (server crontab)
    python monitor_heartbeat.py --dry-run  # reports, writes nothing, sends nothing

Same skeleton as monitor_training.py: service-role client, print() for
logging, per-company try/except-and-continue.

TWO RULES THAT MATTER
- Only the heartbeat's own history is reconciled (heartbeat.scoped). The
  reconcile closes every open task missing from the findings it is given;
  fed the whole history it would close every other task on the action plan.
- Nothing acts. The job records and emails; it never releases a hold,
  deletes or adopts anything.

WHEN IT EMAILS
- Something opened tonight, and the last email was NEW_DAYS or more ago.
- Nothing new, findings still open, and the last email was REMIND_DAYS ago.
Recorded in clients.heartbeat_notified_at. A finding someone already saw on
the action plan (the page opens it first) does not count as new tonight.
"""

import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

import heartbeat as HB
import tasks as T
from database import blocked_client_ids, get_document_versions, get_supabase_admin
from email_sender import send_heartbeat_digest
from obligations import DOCUMENT_TYPES

NEW_DAYS = 7
REMIND_DAYS = 30
ACTOR = "heartbeat"


def _since(value, now: datetime) -> timedelta | None:
    if not value:
        return None
    return now - datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def should_email(opened_now: int, open_total: int, last, now: datetime) -> bool:
    """The email rule, on its own so it can be tested."""
    gap = _since(last, now)
    if opened_now and (gap is None or gap >= timedelta(days=NEW_DAYS)):
        return True
    return bool(open_total) and (gap is None or gap >= timedelta(days=REMIND_DAYS))


FILED_FIGURES_EVERY = timedelta(days=30)


def refresh_filed_figures(sb, now: datetime, dry_run: bool = False) -> None:
    """S76: Belgian companies' filed size, read again at most monthly (accounts
    are filed once a year, 6–18 months after the year ends). Silent without
    the NBB key."""
    import nbb_accounts as NBB
    if not NBB.configured():
        return
    rows = sb.table("clients").select("id, country, enterprise_number, filed_figures") \
        .eq("country", "BE").execute().data or []
    due = [c for c in rows if NBB.cbe_number(c.get("enterprise_number"))
           and ((_since((c.get("filed_figures") or {}).get("checked_at"), now) or FILED_FIGURES_EVERY)
                >= FILED_FIGURES_EVERY)]
    done = 0
    for c in due:
        if dry_run or NBB.refresh_client(c):
            done += 1
    print(f"Filed figures (NBB): {len(due)} due, {done} {'would be ' if dry_run else ''}read.")


def run(now: datetime | None = None, dry_run: bool = False) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    sb = get_supabase_admin()
    clients = sb.table("clients").select("id, user_id, heartbeat_notified_at").execute().data or []
    print(f"RECOSA Heartbeat — {now:%Y-%m-%d %H:%M} UTC — {len(clients)} company(ies)"
          + (" — DRY RUN" if dry_run else ""))
    totals = {"opened": 0, "closed": 0, "sent": 0, "errors": 0}

    blocked = blocked_client_ids()   # D-217: no email to a blocked account's companies
    for c in clients:
        cid = c["id"]
        if cid in blocked:
            continue
        try:
            systems = sb.table("systems").select("id, name, created_at").eq("client_id", cid).execute().data or []
            links = sb.table("activity_systems").select("system_id").eq("client_id", cid).execute().data or []
            found = HB.findings(docs=get_document_versions(cid, sb), systems=systems,
                                links=links, doc_labels=DOCUMENT_TYPES, today=today)
            history = HB.scoped(sb.table("task_events").select("*").eq("client_id", cid)
                                .order("created_at").limit(2000).execute().data or [])
            to_open = T.openings(found, history)
            to_close = T.closures(found, history)
            open_total = len(T.apply_history(found, history))

            rows = ([{"producer": HB.PRODUCER, "finding_key": f["finding_key"], "event": "opened"}
                     for f in to_open]
                    + [{"producer": HB.PRODUCER, "finding_key": k, "event": "closed"}
                       for k in to_close])
            if rows and not dry_run:
                sb.table("task_events").insert(
                    [{**r, "user_id": c["user_id"], "client_id": cid, "actor": ACTOR} for r in rows]
                ).execute()
            totals["opened"] += len(to_open)
            totals["closed"] += len(to_close)

            line = f"  {cid}: {len(found)} finding(s), +{len(to_open)} −{len(to_close)}"
            if should_email(len(to_open), open_total, c.get("heartbeat_notified_at"), now):
                p = sb.table("profiles").select("email").eq("id", c.get("user_id")).execute().data or []
                to = (p[0].get("email") if p else None) or ""
                if not to:
                    line += ", no owner email"
                elif dry_run:
                    line += ", would email the owner"
                elif send_heartbeat_digest(to):
                    sb.table("clients").update({"heartbeat_notified_at": now.isoformat()}).eq("id", cid).execute()
                    totals["sent"] += 1
                    line += ", emailed"
                else:
                    totals["errors"] += 1
                    line += ", email failed"
            print(line)
            for f in found:
                # Keys only: the log is read on the server, and keys carry ids, not content.
                print(f"      {f['finding_key']}")
        except Exception as e:
            totals["errors"] += 1
            print(f"  {cid}: failed — {e}")

    print(f"Done: {totals['opened']} opened, {totals['closed']} closed, "
          f"{totals['sent']} email(s), {totals['errors']} error(s).")
    refresh_filed_figures(sb, now, dry_run)
    return totals


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
