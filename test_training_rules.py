"""
test_training_rules.py — S60 (D-159)

Run: python test_training_rules.py

The cases that would fail silently: a session counted for the wrong
requirement, a planned session counted as attended, someone who left still
dragging the matrix down, NIS2 training asked of a company out of scope, and
a register verdict claiming compliance from an empty register.
"""

import sys
from datetime import date

import training_rules as TR

TODAY = date(2026, 11, 10)


def _req(code, reg, audience, ob=None, applies_from=None, sort=10):
    return TR.requirement({"code": code, "label_en": code, "sort_order": sort, "metadata": {
        "regulation": reg, "audience": audience, "refresh_months": 12,
        "obligation_id": ob, "anchor": "x", "applies_from": applies_from}})


REQS = [
    _req("gdpr_awareness", "GDPR", "personal_data", "gdpr_13", sort=10),
    _req("nis2_awareness", "NIS2", "all", "nis2_09", sort=20),
    _req("nis2_management", "NIS2", "management", sort=30),
    _req("ai_literacy", "EU_AI_ACT", "ai_users", "ai_01", sort=40),
    _req("ai_oversight", "EU_AI_ACT", "ai_overseers", applies_from="2027-12-02", sort=50),
]
CLIENT = {"regulations": ["GDPR", "NIS2", "EU_AI_ACT"], "nis2_in_scope": None}

ANNA = {"id": "a", "name": "Anna", "handles_personal_data": True, "uses_ai": True}
BEN = {"id": "b", "name": "Ben", "handles_personal_data": False, "management_body": True}
CARL = {"id": "c", "name": "Carl", "handles_personal_data": True, "left_on": "2026-06-30"}
DORA = {"id": "d", "name": "Dora", "handles_personal_data": True, "ai_overseer": True}

failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# add_months clamps to month end
check("add_months clamp", TR.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
check("add_months year", TR.add_months(date(2026, 11, 10), 12), date(2027, 11, 10))

# applicable: regulations and NIS2 scope
check("applicable all", [r["code"] for r in TR.applicable(REQS, CLIENT)],
      ["gdpr_awareness", "nis2_awareness", "nis2_management", "ai_literacy", "ai_oversight"])
check("NIS2 out of scope", [r["code"] for r in TR.applicable(REQS, {**CLIENT, "nis2_in_scope": False})],
      ["gdpr_awareness", "ai_literacy", "ai_oversight"])
check("GDPR only", [r["code"] for r in TR.applicable(REQS, {"regulations": ["GDPR"]})], ["gdpr_awareness"])

# needs: an overseer counts as an AI user
check("overseer is AI user", TR.needs(DORA, REQS[3]), True)
check("ben no gdpr", TR.needs(BEN, REQS[0]), False)

SESSIONS = [
    {"id": "s1", "held_on": "2026-03-01", "requirement_codes": ["gdpr_awareness", "nis2_awareness"]},
    {"id": "s2", "held_on": "2025-09-01", "requirement_codes": ["nis2_management"]},          # lapsed
    {"id": "s3", "held_on": "2026-12-01", "requirement_codes": ["ai_literacy"]},             # planned
    {"id": "s4", "held_on": "2025-12-20", "requirement_codes": ["ai_literacy"]},             # lapses soon
    {"id": "s5", "held_on": "2026-10-01", "requirement_codes": ["gdpr_awareness"], "valid_until": "2026-11-01"},
]
ATT = [
    {"session_id": "s1", "employee_id": "a"}, {"session_id": "s3", "employee_id": "a"},
    {"session_id": "s2", "employee_id": "b"}, {"session_id": "s1", "employee_id": "b"},
    {"session_id": "s4", "employee_id": "d"}, {"session_id": "s5", "employee_id": "d"},
    {"session_id": "s1", "employee_id": "c"},
]
reqs = TR.applicable(REQS, CLIENT)
mx = TR.matrix([ANNA, BEN, CARL, DORA], reqs, SESSIONS, ATT, TODAY)

check("left people excluded", sorted(mx), ["a", "b", "d"])
check("anna gdpr current", mx["a"]["gdpr_awareness"]["state"], TR.CURRENT)
check("anna gdpr until", mx["a"]["gdpr_awareness"]["valid_until"], date(2027, 3, 1))
check("planned session not counted", mx["a"]["ai_literacy"]["state"], TR.ABSENT)
check("ben gdpr not required", mx["b"]["gdpr_awareness"]["state"], TR.NOT_REQUIRED)
check("ben management lapsed", mx["b"]["nis2_management"]["state"], TR.EXPIRED)
check("dora ai expiring", mx["d"]["ai_literacy"]["state"], TR.EXPIRING)
check("own valid_until wins (lapsed)", mx["d"]["gdpr_awareness"]["state"], TR.EXPIRED)
check("dora nis2 absent", mx["d"]["nis2_awareness"]["state"], TR.ABSENT)

cov = TR.coverage(mx, reqs)
check("gdpr coverage", (cov["gdpr_awareness"]["required"], cov["gdpr_awareness"][TR.CURRENT],
                        cov["gdpr_awareness"][TR.EXPIRED]), (2, 1, 1))
check("needs attention", TR.needs_attention(cov), True)

# findings: ai_oversight not in force yet, so no task for it
fs = TR.findings(CLIENT, REQS, [ANNA, BEN, CARL, DORA], SESSIONS, ATT, TODAY)
keys = sorted(f["finding_key"] for f in fs)
check("finding keys", keys, ["training:ai_literacy", "training:gdpr_awareness",
                             "training:nis2_awareness", "training:nis2_management"])
sev = {f["finding_key"]: f["severity"] for f in fs}
check("lapsed is due", sev["training:nis2_management"], "due")
check("never trained is open", sev["training:nis2_awareness"], "open")
check("no people finding", [f["finding_key"] for f in TR.findings(CLIENT, REQS, [], [], [], TODAY)],
      ["training:no_people"])

# verdicts
ctx = {"client": CLIENT, "training": {"requirements": REQS, "employees": [ANNA, BEN, CARL, DORA],
                                      "sessions": SESSIONS, "attendance": ATT, "today": TODAY}}
v = TR.verdict("gdpr_13", ctx)
check("gdpr_13 partial", (v["status"], v["evidence"]), ("partial", ["Dora"]))
check("nis2_09 partial", TR.verdict("nis2_09", ctx)["status"], "partial")
check("ai_01 partial", TR.verdict("ai_01", ctx)["status"], "partial")
check("no data, no verdict", TR.verdict("gdpr_13", {"client": CLIENT}), None)
check("no people, no verdict", TR.verdict("gdpr_13", {"client": CLIENT, "training": {
    "requirements": REQS, "employees": [], "sessions": [], "attendance": [], "today": TODAY}}), None)
check("out of scope, no verdict", TR.verdict("nis2_09", {**ctx, "client": {**CLIENT, "nis2_in_scope": False}}), None)

# the register uses them, and tracks them on the Training page
import obligation_register as OR
from obligations import OBLIGATIONS
check("register ids known", OR.check_ids([o["id"] for o in OBLIGATIONS]), [])
check("gdpr_13 tracked", OR.response_kind({"id": "gdpr_13"}), OR.KIND_TRACKED)
verdicts = OR.evaluate([o for o in OBLIGATIONS if o["id"] in ("gdpr_13", "ai_01")],
                       {**ctx, "activities": [], "systems": [], "links": []})
check("register derives", verdicts["gdpr_13"]["source"], "derived")

# routing area
import importlib
try:
    W = importlib.import_module("work_items")
    check("routing nis2", W.area_of_task({"producer": "training", "finding_key": "training:nis2_management"}), "nis2")
    check("routing ai", W.area_of_task({"producer": "training", "finding_key": "training:ai_literacy"}), "ai_act")
except Exception as e:  # streamlit not importable outside the app is fine
    print(f"(routing not checked: {e})")

# the PDFs build, in both languages
import training_docs as D
for lg in ("en", "fr"):
    pdf = D.build_plan_pdf({"company_name": "Test"}, REQS, [ANNA, BEN, CARL, DORA], SESSIONS, ATT, TODAY, lg)
    check(f"plan pdf {lg}", pdf[:4], b"%PDF")
    pdf = D.build_attestation_pdf({"company_name": "Test"}, {**SESSIONS[0], "title": "Spring session",
                                  "duration_minutes": 90, "format": "online"}, [ANNA, BEN], REQS, lg)
    check(f"attestation pdf {lg}", pdf[:4], b"%PDF")

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("All training rules tests passed.")
