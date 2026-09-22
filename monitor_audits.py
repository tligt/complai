"""
RECOSA Audit Monitor — S44

Re-runs the free website compliance scanner (crawler.py / checklist.py /
report.py) for every domain subscribed to recurring audits
(audit_subscriptions, S44), whose owner already proved they control it by
matching their email domain at subscribe time (S43's domains_match(),
enforced once, up front — not re-checked here; a subscription that
already exists is already verified).

Run via GitHub Actions cron (.github/workflows/audit_monitoring.yml) or
manually. Same skeleton as monitor.py / monitor_marketing.py: only
database.py functions backed by get_supabase_admin() (never
get_supabase(), which needs a live Streamlit session), plain print() for
all logging, monitor_runs for structured run-tracking, per-subscription
try/except-and-continue so one bad site doesn't abort the run.
"""

import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# No-op in GitHub Actions (no .env file there, and real env vars are
# already set via secrets) — only fills in values for local runs.
load_dotenv()

from database import (
    get_supabase_admin,
    save_audit,
    upload_file,
    update_audit_path,
    start_monitor_run,
    complete_monitor_run,
)
from crawler import crawl
from checklist import run_checklist
from report import generate_pdf
from email_sender import send_audit_report


def _is_due(sub: dict) -> bool:
    """Never run, or last run at least frequency_days ago."""
    last_run_at = sub.get("last_run_at")
    if not last_run_at:
        return True
    last_run = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
    due_at = last_run + timedelta(days=sub["frequency_days"])
    return datetime.now(timezone.utc) >= due_at


def run_audit_monitoring(triggered_by: str = "cron") -> dict:
    print(f"\nRECOSA Audit Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    run_id = start_monitor_run("audit", triggered_by=triggered_by)

    subs = (
        get_supabase_admin().table("audit_subscriptions")
        .select("*").eq("active", True).execute().data or []
    )
    print(f"{len(subs)} active subscription(s).")

    total_fetched = len(subs)
    total_saved = 0
    total_skipped = 0
    total_errors = 0
    source_stats = []

    for sub in subs:
        domain = sub["site_domain"]
        if not _is_due(sub):
            total_skipped += 1
            continue

        try:
            crawl_result = crawl(sub["website_url"])
            if crawl_result.error:
                print(f"  {domain}: crawl error — {crawl_result.error}")
                total_errors += 1
                source_stats.append({"domain": domain, "error": crawl_result.error})
                continue

            audit_result = run_checklist(crawl_result)
            pdf_bytes = generate_pdf(audit_result)

            audit_id = save_audit(
                email=sub["email"],
                email_domain=sub["email"].split("@")[-1],
                website_url=sub["website_url"],
                audit_result=audit_result,
                user_id=sub["user_id"],
                client_id=sub.get("client_id"),
                site_domain=domain,
            )

            if audit_id:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_domain = domain.replace(".", "_")
                pdf_path = f"{sub['user_id']}/{safe_domain}/{ts}_scheduled_audit.pdf"
                stored_path = upload_file(
                    "audit-reports", pdf_path, pdf_bytes, "application/pdf"
                )
                if stored_path:
                    # S42's gap, closed for this path: the two existing
                    # Streamlit flows upload but never link the path back.
                    update_audit_path(audit_id, stored_path)

            send_audit_report(
                to_email=sub["email"],
                website_url=sub["website_url"],
                pdf_bytes=pdf_bytes,
                score=audit_result.score,
                risk_level=audit_result.risk_level,
                ok_count=audit_result.ok_count,
                warn_count=audit_result.warn_count,
                fail_count=audit_result.fail_count,
            )

            get_supabase_admin().table("audit_subscriptions").update(
                {"last_run_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", sub["id"]).execute()

            print(f"  {domain}: {audit_result.risk_level} risk, score {audit_result.score}/100 — sent to {sub['email']}")
            total_saved += 1
            source_stats.append({"domain": domain, "score": audit_result.score,
                                  "risk_level": audit_result.risk_level})
        except Exception as e:
            print(f"  {domain}: error — {e}")
            total_errors += 1
            source_stats.append({"domain": domain, "error": str(e)})

    print(f"\nDone. Checked: {total_fetched} | Run: {total_saved} | "
          f"Skipped (not due): {total_skipped} | Errors: {total_errors}")

    if run_id:
        complete_monitor_run(
            run_id, total_fetched, total_saved, total_skipped, total_errors,
            source_stats, {}, status="completed",
        )

    return {
        "checked": total_fetched, "run": total_saved,
        "skipped": total_skipped, "errors": total_errors,
    }


if __name__ == "__main__":
    result = run_audit_monitoring(triggered_by="cron")
    print(json.dumps(result, indent=2))
