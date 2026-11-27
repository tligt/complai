"""test_lifecycle_view.py — D-216: stages and next planned email for the
back office's Lifecycle page. No database.

    python test_lifecycle_view.py
"""

from datetime import datetime, timedelta, timezone

import lifecycle_view as LV

failures = []


def check(name, ok):
    if not ok:
        failures.append(name)
        print(f"FAIL  {name}")


NOW = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
iso = lambda d: d.isoformat()

check("no account: registered", LV.stage_of(None, NOW) == ("registered", None))
check("registered", LV.stage_of({"status": "registered"}, NOW) == ("registered", None))
check("trial day 0", LV.stage_of({"status": "trial", "trial_ends_at": iso(NOW + timedelta(days=14))}, NOW) == ("trial", 0))
check("trial day 10", LV.stage_of({"status": "trial", "trial_ends_at": iso(NOW + timedelta(days=4))}, NOW) == ("trial", 10))
check("trial past its end: drop-out (job not run yet)",
      LV.stage_of({"status": "trial", "trial_ends_at": iso(NOW - timedelta(days=2))}, NOW) == ("dropout", 2))
check("expired day 7", LV.stage_of({"status": "expired", "trial_ends_at": iso(NOW - timedelta(days=7))}, NOW) == ("dropout", 7))
check("customer since", LV.stage_of({"status": "active"}, NOW, NOW - timedelta(days=40)) == ("customer", 40))
check("blocked since", LV.stage_of({"status": "blocked"}, NOW, NOW - timedelta(days=3)) == ("blocked", 3))
check("churned since", LV.stage_of({"status": "cancelled"}, NOW, NOW - timedelta(days=5)) == ("churned", 5))

check("next on trial day 3", LV.next_planned("trial", 3, {"welcome", "personal", "step_a"}) == (4, "step_b"))
check("next on trial day 9: trial ending", LV.next_planned("trial", 9, {"welcome", "personal", "step_a", "step_b", "step_c", "wrapup"}) == (10, "four_days"))
check("next drop-out day 22: the access notice (D-222)",
      LV.next_planned("dropout", 22, {"ended", "missing", "why"}) == (38, "access_closing"))
check("next drop-out day 1", LV.next_planned("dropout", 1, {"ended"}) == (7, "missing"))
check("drop-out day 2, nothing sent: ended is due now", LV.next_planned("dropout", 2, set()) == (0, "ended"))
check("trial day 7, late start: the welcome first, as the job does",
      LV.next_planned("trial", 7, set()) == (0, "welcome"))
check("trial day 7, welcome sent: the latest due (step_c)",
      LV.next_planned("trial", 7, {"welcome"}) == (6, "step_c"))
check("churned: nothing built", LV.next_planned("churned", 10, set()) is None)
check("unknown day", LV.next_planned("trial", None, set()) is None)

check("trial lane holds both flows", {f for _, _, f, _ in LV.LANES["trial"][1]} == {"onboarding", "trial_ending"})
check("notices and the deletion shown as live (D-222)",
      [live for _, k, _, live in LV.LANES["dropout"][1]
       if k in ("access_closing", "access_closed", "deleted")] == [True] * 3)
check("no day-55 reminder", "last_warning" not in [k for _, k, _, _ in LV.LANES["dropout"][1]])

print("All lifecycle view tests passed." if not failures else f"{len(failures)} failure(s).")
raise SystemExit(1 if failures else 0)
