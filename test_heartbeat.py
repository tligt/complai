"""
test_heartbeat.py — S67 (D-188)

Run: python test_heartbeat.py

The cases that would fail silently: a hold set before hold_set_on existed never
asked about, a held or in-force version warned about deletion, a new system
flagged the day it is added, a key that changes from one night to the next
(the client would be emailed about the same thing as if it were new), and —
the one that would do real damage — the nightly job closing every other task
on the action plan because it reconciled one producer against all history.
"""

import sys
from datetime import date

import heartbeat as H
import tasks as T

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


TODAY = date(2026, 11, 18)
LABELS = {"privacy_policy": "Privacy Policy"}


def doc(id_, **kw):
    return {"id": id_, "document_type": "privacy_policy", "language": "fr", "version": 2, **kw}


def keys(fs):
    return [f["finding_key"] for f in fs]


# ── Holds ─────────────────────────────────────────────────────────────────
fs = H.stale_holds([
    doc("old", legal_hold=True, hold_set_on="2026-09-01T10:00:00+00:00"),
    doc("new", legal_hold=True, hold_set_on="2026-11-10T10:00:00+00:00"),
    doc("unknown", legal_hold=True, hold_set_on=None),
    doc("none", legal_hold=False, hold_set_on="2025-01-01"),
], LABELS, TODAY)
check("old and undated holds asked about", keys(fs) == ["heartbeat:hold:old", "heartbeat:hold:unknown"])
check("hold title is a question", fs and fs[0]["title"].endswith("?"))
check("hold names the document", fs and "Privacy Policy v2 (FR)" in fs[0]["title"])
check("hold date in detail", fs and "2026-09-01" in fs[0]["detail"])
check("hold exactly 30 days old is asked",
      keys(H.stale_holds([doc("x", legal_hold=True, hold_set_on="2026-10-19")], LABELS, TODAY))
      == ["heartbeat:hold:x"])

# ── Retention ending ──────────────────────────────────────────────────────
fs = H.retention_ending([
    doc("soon", status="superseded", retain_until="2026-12-01"),
    doc("today", status="superseded", retain_until="2026-11-18"),
    doc("far", status="superseded", retain_until="2027-06-01"),
    doc("past", status="superseded", retain_until="2026-11-01"),
    doc("held", status="superseded", retain_until="2026-12-01", legal_hold=True),
    doc("live", status="in_force", retain_until="2026-12-01"),
], LABELS, TODAY)
check("only near, unheld, superseded versions", keys(fs) == ["heartbeat:retention:soon", "heartbeat:retention:today"])
check("retention is due, with its date", fs and fs[0]["severity"] == T.DUE and fs[0]["due"] == date(2026, 12, 1))

# ── Not reviewed in a year ────────────────────────────────────────────────
fs = H.not_reviewed([
    doc("stale", status="in_force", adopted_at="2025-10-01T09:00:00+00:00"),
    doc("fresh", status="in_force", adopted_at="2026-03-01T09:00:00+00:00"),
    doc("eff", status="in_force", adopted_at=None, effective_from="2025-01-01"),
    doc("draft", status="draft", adopted_at=None, uploaded_at="2024-01-01"),
    doc("undated", status="in_force"),
], LABELS, TODAY)
check("in force over a year, by adoption or effective date", keys(fs) == ["heartbeat:review:stale", "heartbeat:review:eff"])

# ── Systems with no activity ──────────────────────────────────────────────
fs = H.unused_systems([
    {"id": "s1", "name": "Old CRM", "created_at": "2026-09-01T00:00:00+00:00"},
    {"id": "s2", "name": "New tool", "created_at": "2026-11-15T00:00:00+00:00"},
    {"id": "s3", "name": "Used", "created_at": "2026-01-01T00:00:00+00:00"},
], [{"system_id": "s3", "activity_id": "a1"}], TODAY)
check("unused system after the grace period only", keys(fs) == ["heartbeat:system:s1"])

# ── Keys are stable: renaming changes nothing ─────────────────────────────
a = H.findings(systems=[{"id": "s1", "name": "A", "created_at": "2026-01-01"}], today=TODAY)
b = H.findings(systems=[{"id": "s1", "name": "B", "created_at": "2026-01-01"}], today=TODAY)
check("key stable across rename", keys(a) == keys(b))
check("producer is heartbeat", all(f["producer"] == "heartbeat" for f in a))

# Nothing at all on an empty company.
check("empty company, no findings", H.findings(today=TODAY) == [])

# ── The guard: reconciling one producer must not close the others ─────────
history = [
    {"producer": "obligation", "finding_key": "obligation:gdpr_01", "event": "opened", "created_at": "1"},
    {"producer": "training", "finding_key": "training:gdpr_awareness", "event": "opened", "created_at": "2"},
    {"producer": "heartbeat", "finding_key": "heartbeat:hold:gone", "event": "opened", "created_at": "3"},
]
now = H.findings(systems=[{"id": "s1", "name": "A", "created_at": "2026-01-01"}], today=TODAY)
check("unscoped history would close other producers' tasks (the danger is real)",
      "obligation:gdpr_01" in T.closures(now, history))
closed = T.closures(now, H.scoped(history))
check("scoped: only the heartbeat task that went away closes", closed == ["heartbeat:hold:gone"])
check("scoped: the new heartbeat finding opens",
      keys(T.openings(now, H.scoped(history))) == ["heartbeat:system:s1"])

# ── Dead branch removed: documents_outstanding no longer warns on retention ─
check("documents producer leaves retention to the heartbeat",
      T.documents_outstanding([doc("r", status="superseded", retain_until="2026-12-01")],
                              LABELS, TODAY) == [])

# ── When the nightly job emails ───────────────────────────────────────────
from datetime import datetime, timezone  # noqa: E402

from monitor_heartbeat import should_email  # noqa: E402

NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)
check("new finding, never emailed", should_email(1, 1, None, NOW))
check("new finding, emailed 3 days ago: wait", not should_email(1, 2, "2026-11-15T03:00:00+00:00", NOW))
check("new finding, emailed 8 days ago", should_email(1, 2, "2026-11-10T03:00:00+00:00", NOW))
check("nothing new, open, emailed 10 days ago: quiet", not should_email(0, 2, "2026-11-08T03:00:00+00:00", NOW))
check("nothing new, open, emailed 31 days ago: remind", should_email(0, 2, "2026-10-18T03:00:00+00:00", NOW))
check("nothing open, nothing sent", not should_email(0, 0, None, NOW))

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All heartbeat tests passed.")
