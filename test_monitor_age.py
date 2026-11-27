"""
test_monitor_age.py — D-225. The regulatory monitor skips items older than
MAX_ITEM_AGE_DAYS before summarising them (CERT-FR's alerts feed lists
alerts from 2015). Run: python test_monitor_age.py
"""

from datetime import datetime, timezone

import monitor

failures = []


def check(name, ok):
    if not ok:
        failures.append(name)
        print(f"FAIL  {name}")


NOW = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
check("30 days is the limit", monitor.MAX_ITEM_AGE_DAYS == 30)
check("2015: too old", monitor.too_old("Fri, 24 Jul 2015 00:00:00 +0000", NOW))
check("last week: kept", not monitor.too_old("Fri, 20 Nov 2026 10:00:00 +0100", NOW))
check("a future date (an event): kept", not monitor.too_old("Tue, 15 Dec 2026 08:33:00 +0100", NOW))
check("GMT form: kept", not monitor.too_old("Thu, 19 Nov 2026 12:37:09 GMT", NOW))
check("ISO date, 38 days: too old", monitor.too_old("2026-10-20", NOW))
check("ISO date, 28 days: kept", not monitor.too_old("2026-10-30", NOW))
check("no date: kept", not monitor.too_old("", NOW))
check("unreadable date: kept", not monitor.too_old("sometime last year", NOW))

print("All monitor age tests passed." if not failures else f"{len(failures)} failure(s).")
raise SystemExit(1 if failures else 0)
