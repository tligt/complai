"""
test_cra_reporting.py — S71 (D-189)

Run: python test_cra_reporting.py

The cases that would mislead silently: a CRA clock on a company that makes no
product (every incident of every SME would grow three deadlines), a final
report dated from the wrong event, a report drafted in French for a platform
that takes English only, and the NIS2 and GDPR clocks changing because a
third track was added next to them.
"""

import sys
from datetime import datetime, timedelta, timezone

import incident_rules as R

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


FOUND = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
NOW = FOUND + timedelta(hours=10)
MAKER = {"legal_name": "Acme Devices SRL", "cra_manufacturer": True, "regulations": ["GDPR"],
         "contact_email": "security@acme.example"}
NOT_MAKER = {"legal_name": "Shop SRL", "cra_manufacturer": False, "regulations": ["GDPR", "CRA"]}
UNANSWERED = {"legal_name": "X", "regulations": ["GDPR", "NIS2"]}


def inc(**kw):
    return {"id": "i1", "title": "t", "discovered_at": FOUND.isoformat(), "status": "open",
            "personal_data": False, **kw}


def dl(incident, client, events=(), now=NOW):
    return {d["kind"]: d for d in R.deadlines(incident, client, list(events), False, now)}


def note(kind, at):
    return {"event_type": "notification", "kind": kind, "occurred_at": at.isoformat()}


CRA = (R.CRA_EARLY, R.CRA_NOTIFICATION, R.CRA_INTERMEDIATE, R.CRA_FINAL, R.CRA_USERS)

# ── Who is a manufacturer ─────────────────────────────────────────────────
check("answered yes", R.cra_applies(MAKER))
check("answered no beats CRA in regulations", not R.cra_applies(NOT_MAKER))
check("unanswered without CRA: no", not R.cra_applies(UNANSWERED))
check("unanswered with CRA in regulations: yes", R.cra_applies({"regulations": ["CRA"]}))

# ── Not a manufacturer: no CRA clock at all ───────────────────────────────
d = dl(inc(cra_type="vulnerability"), NOT_MAKER)
check("non-manufacturer: every CRA kind not required",
      all(d[k]["state"] == R.NOT_REQUIRED for k in CRA))
d = dl(inc(), UNANSWERED)
check("unanswered company: CRA not required, not 'to decide'",
      all(d[k]["state"] == R.NOT_REQUIRED for k in CRA))

# ── Manufacturer, not assessed yet: to decide, clock running from discovery
d = dl(inc(), MAKER)
check("unassessed: early warning to decide", d[R.CRA_EARLY]["state"] == R.TO_DECIDE)
check("unassessed: early warning due 24 h after discovery", d[R.CRA_EARLY]["due"] == FOUND + timedelta(hours=24))
check("unassessed: notification due 72 h", d[R.CRA_NOTIFICATION]["due"] == FOUND + timedelta(hours=72))
check("deciding late does not move the deadline",
      dl(inc(), MAKER, now=FOUND + timedelta(hours=30))[R.CRA_EARLY]["state"] == R.OVERDUE)

# ── Assessed as neither ───────────────────────────────────────────────────
d = dl(inc(cra_type="none"), MAKER)
check("'none': nothing required", all(d[k]["state"] == R.NOT_REQUIRED for k in CRA))

# ── Vulnerability ─────────────────────────────────────────────────────────
d = dl(inc(cra_type="vulnerability"), MAKER)
check("vulnerability: early warning running", d[R.CRA_EARLY]["state"] == R.RUNNING)
check("vulnerability: final undated before a fix", d[R.CRA_FINAL]["due"] is None)
check("vulnerability: final described as 14 days after a fix",
      R.describe_left(d[R.CRA_FINAL]) == "14 days after a fix is available")
check("users: in a timely manner", R.describe_left(d[R.CRA_USERS]) == "in a timely manner")
check("no intermediate until the CSIRT asks", d[R.CRA_INTERMEDIATE]["state"] == R.NOT_REQUIRED)
fix = FOUND + timedelta(days=3)
d = dl(inc(cra_type="vulnerability", cra_fix_available_at=fix.isoformat()), MAKER)
check("vulnerability: final 14 days after the fix", d[R.CRA_FINAL]["due"] == fix + timedelta(days=14))

# ── Severe incident ───────────────────────────────────────────────────────
d = dl(inc(cra_type="severe_incident"), MAKER)
check("incident: final undated before the notification", d[R.CRA_FINAL]["due"] is None)
check("incident: final described as one month after the notification",
      R.describe_left(d[R.CRA_FINAL]) == "one month after the notification")
sent_at = FOUND + timedelta(hours=60)
d = dl(inc(cra_type="severe_incident"), MAKER, [note(R.CRA_NOTIFICATION, sent_at)])
check("incident: final one month after the notification was SENT",
      d[R.CRA_FINAL]["due"] == sent_at.replace(month=12))
check("sent notification is done", d[R.CRA_NOTIFICATION]["state"] == R.DONE)

# Intermediate when the CSIRT asks.
ask = FOUND + timedelta(days=5)
d = dl(inc(cra_type="severe_incident", cra_intermediate_due=ask.isoformat()), MAKER)
check("intermediate requested: due on the date asked",
      d[R.CRA_INTERMEDIATE]["state"] == R.RUNNING and d[R.CRA_INTERMEDIATE]["due"] == ask)

# ── NIS2 and GDPR untouched ───────────────────────────────────────────────
nis2_client = {**MAKER, "nis2_in_scope": True}
a = dl(inc(significant=True, cra_type="vulnerability"), nis2_client)
b = dl(inc(significant=True), {**nis2_client, "cra_manufacturer": False})
check("NIS2 clock identical with or without the CRA track",
      all(a[k]["due"] == b[k]["due"] and a[k]["state"] == b[k]["state"]
          for k in (R.NIS2_EARLY, R.NIS2_NOTIFICATION, R.NIS2_FINAL, R.GDPR_AUTHORITY)))
check("both clocks can run on one incident",
      a[R.NIS2_EARLY]["state"] == R.RUNNING and a[R.CRA_EARLY]["state"] == R.RUNNING)

# ── Team alerts and contact clocks ────────────────────────────────────────
contact = {"id": "c1", "email": "x@y.z", "alert_on": "significant", "active": True}
check("'significant' contact alerted for a CRA-reportable incident",
      R.alert_targets([contact], inc(cra_type="vulnerability"), [], is_nis2=False) == [contact])
check("…and not for a CRA 'none'",
      R.alert_targets([contact], inc(cra_type="none"), [], is_nis2=False) == [])
timed = {**contact, "deadline_hours": 48}
d = {x["kind"]: x for x in R.deadlines(inc(cra_type="vulnerability"), MAKER, [], False, NOW, [timed])}
check("contract clock for 'significant' runs on a CRA incident", d["contact:c1"]["state"] == R.RUNNING)

# ── Authority: the SRP, NIS2 CSIRT as unverified fallback ─────────────────
jur = {"csirt_en": "Centre for Cybersecurity Belgium", "csirt_short": "CCB"}
a = R.authorities(jur, "fr")["cra"]
check("CRA submits on the SRP", a["submit"] == R.SRP_URL)
check("falls back to the NIS2 CSIRT, unverified", a["name"] == "Centre for Cybersecurity Belgium" and not a["verified"])
a = R.authorities({**jur, "cra_csirt_en": "Coordinator X", "cra_csirt_verified_on": "2026-11-18"}, "en")["cra"]
check("a checked coordinator wins and is verified", a["name"] == "Coordinator X" and a["verified"])

# ── Drafts ────────────────────────────────────────────────────────────────
v = inc(cra_type="vulnerability", cra_product="Router X1 firmware 2.3", description="RCE in admin UI")
t = R.draft(R.CRA_EARLY, v, MAKER, [], "fr")
check("CRA report in English even when French is picked", t.startswith("Early warning") and "[to complete]" in t)
check("early warning names Member States", "Member States" in t)
check("vulnerability early warning has no 'unlawful' question", "unlawful" not in t)
t = R.draft(R.CRA_EARLY, inc(cra_type="severe_incident"), MAKER, [], "en")
check("incident early warning asks about unlawful or malicious acts", "unlawful or malicious" in t)
t = R.draft(R.CRA_NOTIFICATION, v, MAKER, [], "en")
check("vulnerability notification lists the Art. 14(2)(b) items",
      all(x in t.lower() for x in ("general nature of the exploit", "users can take", "how sensitive")))
t = R.draft(R.CRA_FINAL, {**v, "cra_fix_available_at": fix.isoformat()}, MAKER, [], "en")
check("vulnerability final report: (i) (ii) (iii) and the fix date",
      all(x in t for x in ("(i)", "(ii)", "malicious actor", "(iii)", "security update")))
t = R.draft(R.CRA_USERS, v, MAKER, [], "fr")
check("users notice in the picked language", t.startswith("Objet") and "Router X1" in t)
t = R.draft(R.CRA_NOTIFICATION, v, MAKER, [], "fr",
            events=[note(R.CRA_NOTIFICATION, FOUND + timedelta(hours=30))], followup=True)
check("CRA follow-up headed in English", t.startswith("Supplementary information"))
check("GDPR draft still French", R.draft(R.GDPR_AUTHORITY, inc(), MAKER, [], "fr").startswith("Notification de violation"))

# ── Action plan ───────────────────────────────────────────────────────────
fs = R.findings([v], MAKER, {}, {}, NOW)
check("open CRA deadlines become tasks",
      {f["finding_key"] for f in fs} >= {"incident:i1:cra_early_warning", "incident:i1:cra_notification"})

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All CRA reporting tests passed.")
