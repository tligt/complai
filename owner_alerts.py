"""
owner_alerts.py — D-201, 23 Nov 2026. Tells the owner, by email, the moment
something happens in the funnel:

  - someone reached the end of the free check (its results page);
  - a new account was opened (a trial, or a beta invitation);
  - a client started paying (an account period that is active on a paid plan,
    not opened by a beta invitation).

Run every 10 minutes by cron (deploy/crontab). Reads the last two days only,
and owner_alerts remembers what was already announced, so each event is
emailed once, and a missed run is caught up by the next. One email per run,
listing everything new. Test accounts (signup_source "test") are left out.

    python owner_alerts.py            # send
    python owner_alerts.py --dry-run  # print what would be sent, send nothing

The recipient is OWNER_ALERT_EMAIL; without it the run prints and stops.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

WINDOW = timedelta(days=2)
PAID_PLANS = ("starter", "professional", "enterprise", "advisory")
CHECK_NAMES = {"website": "Website check", "nis2": "NIS2", "ai": "AI Act", "gdpr": "GDPR"}
INVITE_NOTE_PREFIX = "Beta invitation"


# ── Pure parts (test_owner_alerts.py) ──────────────────────────────────────

def checks_label(tool: str | None) -> str:
    codes = [c for c in (tool or "").split(",") if c]
    return ", ".join(CHECK_NAMES.get(c, c) for c in codes) or "—"


def origin_label(source: str | None, utm: dict | None) -> str:
    utm = utm or {}
    parts = [f"{k[4:]}={utm[k]}" for k in ("utm_source", "utm_medium", "utm_campaign") if utm.get(k)]
    if source:
        parts.insert(0, f"src={source}")
    return ", ".join(parts) or "direct"


def finished_checks(events: list[dict]) -> list[dict]:
    """One item per visit that reached the results page. An event without a
    visit id (before D-201) is its own visit. The visit's sign-up, if any, is
    noted."""
    signed = {e["visit"] for e in events if e["event"] == "signup" and e.get("visit")}
    seen, out = set(), []
    for e in sorted(events, key=lambda e: e["created_at"]):
        if e["event"] != "results_viewed":
            continue
        visit = e.get("visit") or f"event-{e['id']}"
        if visit in seen:
            continue
        seen.add(visit)
        out.append({"key": f"check:{visit}", "at": e["created_at"],
                    "checks": checks_label(e.get("tool")),
                    "origin": origin_label(e.get("source"), e.get("utm")),
                    "signed_up": visit in signed})
    return out


def is_paying(period: dict) -> bool:
    return (period.get("status") == "active" and period.get("plan") in PAID_PLANS
            and not (period.get("note") or "").startswith(INVITE_NOTE_PREFIX))


def subject_for(checks: list, accounts: list, paying: list) -> str:
    bits = []
    if paying:
        bits.append(f"{len(paying)} paying client{'s' if len(paying) > 1 else ''}")
    if accounts:
        bits.append(f"{len(accounts)} new account{'s' if len(accounts) > 1 else ''}")
    if checks:
        bits.append(f"{len(checks)} free check{'s' if len(checks) > 1 else ''} finished")
    return "RECOSA: " + ", ".join(bits)


def body_lines(checks: list, accounts: list, paying: list) -> list[str]:
    lines = []
    if paying:
        lines.append("PAYING CLIENTS")
        lines += [f"- {p['who']} — {p['plan']} (from {p['at'][:16].replace('T', ' ')} UTC)" for p in paying]
        lines.append("")
    if accounts:
        lines.append("NEW ACCOUNTS")
        lines += [f"- {a['who']} — {a['what']}, via {a['origin']} ({a['at'][:16].replace('T', ' ')} UTC)"
                  for a in accounts]
        lines.append("")
    if checks:
        lines.append("FREE CHECKS FINISHED (results page reached)")
        lines += [f"- {c['checks']} — {c['origin']}"
                  f"{' — signed up' if c['signed_up'] else ''} ({c['at'][:16].replace('T', ' ')} UTC)"
                  for c in checks]
        lines.append("")
    return lines


# ── Reading and sending ────────────────────────────────────────────────────

def _collect(admin, since: str):
    from database import SUBSCRIPTION_TIERS
    events = admin.table("funnel_events").select("id, event, tool, source, utm, visit, created_at") \
        .gte("created_at", since).in_("event", ["results_viewed", "signup"]).execute().data or []
    checks = finished_checks(events)

    accs = admin.table("accounts").select("id, name, plan, status, owner_user_id, created_at") \
        .gte("created_at", since).execute().data or []
    periods = admin.table("account_periods").select("id, account_id, plan, status, note, created_at") \
        .gte("created_at", since).execute().data or []
    ids = {a["owner_user_id"] for a in accs if a.get("owner_user_id")}
    pay_acc_ids = {p["account_id"] for p in periods if is_paying(p)}
    pay_accs = {a["id"]: a for a in (admin.table("accounts").select("id, name, owner_user_id")
                                     .in_("id", list(pay_acc_ids)).execute().data or [])} if pay_acc_ids else {}
    ids |= {a["owner_user_id"] for a in pay_accs.values() if a.get("owner_user_id")}
    profs = {p["id"]: p for p in (admin.table("profiles").select("id, email, signup_source")
                                  .in_("id", list(ids)).execute().data or [])} if ids else {}

    def test(user_id):
        return (profs.get(user_id) or {}).get("signup_source") == "test"

    accounts = []
    for a in accs:
        if test(a.get("owner_user_id")):
            continue
        prof = profs.get(a.get("owner_user_id")) or {}
        invited = any(p["account_id"] == a["id"] and (p.get("note") or "").startswith(INVITE_NOTE_PREFIX)
                      for p in periods)
        what = ("beta invitation, " if invited else f"{a.get('status') or '?'}, ") \
            + SUBSCRIPTION_TIERS.get(a.get("plan"), a.get("plan") or "?")
        accounts.append({"key": f"account:{a['id']}", "at": a["created_at"],
                         "who": prof.get("email") or a.get("name") or a["id"], "what": what,
                         "origin": prof.get("signup_source") or "direct"})
    paying = []
    for p in periods:
        acc = pay_accs.get(p["account_id"]) or {}
        if not is_paying(p) or test(acc.get("owner_user_id")):
            continue
        prof = profs.get(acc.get("owner_user_id")) or {}
        paying.append({"key": f"paid:{p['id']}", "at": p["created_at"],
                       "who": f"{acc.get('name') or '?'} ({prof.get('email') or 'no owner'})",
                       "plan": SUBSCRIPTION_TIERS.get(p["plan"], p["plan"])})
    return checks, accounts, paying


def main(dry_run: bool = False) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    import database as D
    import email_sender as E

    admin = D.get_supabase_admin()
    since = (datetime.now(timezone.utc) - WINDOW).isoformat()
    checks, accounts, paying = _collect(admin, since)
    sent = {r["key"] for r in (admin.table("owner_alerts").select("key")
                               .in_("key", [x["key"] for x in checks + accounts + paying] or ["-"])
                               .execute().data or [])}
    checks = [x for x in checks if x["key"] not in sent]
    accounts = [x for x in accounts if x["key"] not in sent]
    paying = [x for x in paying if x["key"] not in sent]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not (checks or accounts or paying):
        print(f"Owner alerts — {stamp}: nothing new.")
        return 0

    subject = subject_for(checks, accounts, paying)
    lines = body_lines(checks, accounts, paying)
    print(f"Owner alerts — {stamp}: {subject}")
    print("\n".join(lines))
    if dry_run:
        return 0
    to = (os.environ.get("OWNER_ALERT_EMAIL") or "").strip()
    cfg = E._notify_config()
    if not (to and cfg):
        print("Not sent: OWNER_ALERT_EMAIL or the email settings are missing.")
        return 1
    import html as _h
    link = f"{cfg[3].replace('://app.', '://admin.')}/acquisition"
    html_body = E._short_html(
        [_h.escape(l).replace("  ", "&nbsp; ") for l in lines if l], "Open Acquisition", link)
    if not E._post_short(cfg, to, subject, "\n".join(lines) + f"\n\n{link}\n", html_body, "Owner alert"):
        print("Not sent: Brevo refused or failed; will retry next run.")
        return 1
    admin.table("owner_alerts").insert([{"key": x["key"]} for x in checks + accounts + paying]).execute()
    print(f"Sent to the owner: {len(checks) + len(accounts) + len(paying)} item(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
