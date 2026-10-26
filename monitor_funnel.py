"""
RECOSA Free Check Delivery — S49 part 2 (D-119)

Every 15 minutes. The public app's one form promises the full result by
email once the address is confirmed. A confirmed account that has not
logged in yet would otherwise never get it, so this job sends it:
funnel_delivery.deliver() for every confirmed account whose free check
(user metadata) has not been sent. The flag it sets on the account stops a
second email, whether the app or this job sent the first.

A website report whose email is not at the site's domain waits until the
site is proven in the app (deliver() returns 'not_proven').

Run via GitHub Actions (.github/workflows/funnel_delivery.yml) or manually.
Service-role client only, print() for logging, per-account
try/except-and-continue, like monitor_incidents.py.
"""

from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from database import get_supabase_admin
import funnel_delivery as FD


def run() -> dict:
    admin = get_supabase_admin()
    counts: dict[str, int] = {}
    page = 1
    while True:
        users = admin.auth.admin.list_users(page=page, per_page=200) or []
        for u in users:
            meta = u.user_metadata or {}
            if not meta.get("recosa_pending") or meta.get("recosa_report_sent"):
                continue
            try:
                res = FD.deliver(u)
            except Exception as e:
                res = "failed"
                print(f"  {u.id}: failed — {e}")
            counts[res] = counts.get(res, 0) + 1
            if res == "sent":
                print(f"  {u.id}: result sent")
        if len(users) < 200:
            break
        page += 1
    print(f"RECOSA Free Check Delivery — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC — {counts or 'nothing due'}")
    return counts


if __name__ == "__main__":
    run()
