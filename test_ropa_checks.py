"""
test_ropa_checks.py — S65 (D-186)

Run: python test_ropa_checks.py

The cases that would mislead silently: a rule firing on a clean activity (the
client learns to ignore the panel), a rule repeating what readiness() already
blocks on, a finding key that changes while the finding is the same, and the
readiness() retention check missing an activity that records its retention the
structured way.
"""

import sys

import ropa_checks as RC

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


RET_META = {
    "statutory_social_documents": {"statutory": True, "jurisdiction": ["BE"]},
    "statutory_accounting": {"statutory": True, "jurisdiction": ["BE", "FR"]},
    "statutory_other": {"statutory": True},
    "contract_duration": {},
}

CLEAN = {
    "id": "a1", "name": "Payroll", "legal_basis": "legal_obligation",
    "data_subject_categories": ["employees"], "special_categories": [],
    "art9_condition": None,
    "retention_value": 5, "retention_unit": "years",
    "retention_basis_code": "statutory_social_documents",
    "retention_period": None,
}


def rules(a, **kw):
    kw.setdefault("client_country", "BE")
    kw.setdefault("retention_basis_meta", RET_META)
    return [f["rule"] for f in RC.check_activity(a, **kw)]


# A clean activity has nothing to say.
check("clean activity has no findings", rules(CLEAN) == [])

# 1. Art. 9(2) condition with no special category.
check("art9 without special category",
      "art9_without_special_category" in rules({**CLEAN, "art9_condition": "employment_social_security"}))
check("art9 with special category is fine",
      "art9_without_special_category" not in rules(
          {**CLEAN, "art9_condition": "employment_social_security", "special_categories": ["health"]}))
# Special categories with NO condition is readiness()'s rule: not repeated here.
check("special without condition left to readiness",
      rules({**CLEAN, "special_categories": ["health"]}) == [])

# 2. Consent with employees or job applicants.
check("consent for employees", "consent_imbalance" in rules({**CLEAN, "legal_basis": "consent"}))
check("consent for job applicants", "consent_imbalance" in rules(
    {**CLEAN, "legal_basis": "consent", "data_subject_categories": ["job_applicants"]}))
check("consent for customers is fine", "consent_imbalance" not in rules(
    {**CLEAN, "legal_basis": "consent", "data_subject_categories": ["customers"]}))

# 3. Free-text retention is info; structured beats a leftover sentence.
legacy = {**CLEAN, "retention_value": None, "retention_unit": None,
          "retention_basis_code": None, "retention_period": "10 years"}
f = RC.check_activity(legacy, client_country="BE", retention_basis_meta=RET_META)
check("free text reported", [x["rule"] for x in f] == ["retention_free_text"])
check("free text is info", f and f[0]["severity"] == RC.INFO)
check("structured with old sentence is not free text",
      "retention_free_text" not in rules({**CLEAN, "retention_period": "10 years"}))
# No retention at all is readiness()'s blocking rule.
check("no retention left to readiness",
      rules({**legacy, "retention_period": ""}) == [])

# 4. Indefinite.
check("indefinite", "retention_indefinite" in rules(
    {**CLEAN, "retention_value": None, "retention_unit": "indefinite"}))

# 5. Period without reason.
check("period without reason",
      "retention_without_reason" in rules({**CLEAN, "retention_basis_code": None}))

# 6. Archive with no reason is an error; with a reason it is fine.
arc = {**CLEAN, "retention_archive_value": 3, "retention_archive_unit": "years"}
f = RC.check_activity(arc, client_country="BE", retention_basis_meta=RET_META)
check("archive without reason", [x["rule"] for x in f] == ["archive_without_reason"])
check("archive without reason is error", f and f[0]["severity"] == RC.ERROR)
check("archive with reason fine", rules(
    {**arc, "retention_archive_basis_code": "statutory_accounting"}) == [])

# 7. Statutory reason from another country.
check("BE-only reason for a FR company",
      "statutory_other_country:retention_basis_code" in rules(CLEAN, client_country="FR"))
check("BE+FR reason for a FR company is fine", rules(
    {**CLEAN, "retention_basis_code": "statutory_accounting"}, client_country="FR") == [])
check("statutory reason with no jurisdiction is fine", rules(
    {**CLEAN, "retention_basis_code": "statutory_other"}, client_country="NL") == [])
check("no country, no finding", rules(CLEAN, client_country=None) == [])

# 8. Processor without a DPA, named per system; other roles do not need one here.
systems = {"s1": {"id": "s1", "name": "Payroll Co", "dpa_status": "none"},
           "s2": {"id": "s2", "name": "Bank", "dpa_status": "none"},
           "s3": {"id": "s3", "name": "Signed Co", "dpa_status": "signed"}}
links = [{"activity_id": "a1", "system_id": "s1", "role": "processor"},
         {"activity_id": "a1", "system_id": "s2", "role": "recipient_controller"},
         {"activity_id": "a1", "system_id": "s3", "role": "processor"}]
r = rules(CLEAN, links=links, systems_by_id=systems)
check("processor without DPA", r == ["processor_without_dpa:s1"])

# Keys never carry a name: renaming the system keeps the same finding.
systems2 = {**systems, "s1": {**systems["s1"], "name": "Renamed"}}
check("key stable across rename",
      rules(CLEAN, links=links, systems_by_id=systems2) == r)

# Worst first.
f = RC.check_activity({**arc, "legal_basis": "consent", "retention_basis_code": None},
                      client_country="BE", retention_basis_meta=RET_META)
check("sorted worst first", [x["severity"] for x in f] == sorted(
    [x["severity"] for x in f], key=RC.SEVERITY_ORDER.get))

# check_all and counts.
all_f = RC.check_all([CLEAN, {**arc, "id": "a2"}], links, systems.values(),
                     client_country="BE", retention_basis_meta=RET_META)
check("check_all keys", set(all_f) == {"a1", "a2"})
check("counts", RC.counts(all_f) == {"error": 1, "warning": 1, "info": 0})

# has_structured_retention: what readiness() now accepts.
check("structured: value+unit", RC.has_structured_retention({"retention_value": 2, "retention_unit": "years"}))
check("structured: indefinite", RC.has_structured_retention({"retention_unit": "indefinite"}))
check("not structured: unit only", not RC.has_structured_retention({"retention_unit": "years"}))

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All ropa_checks tests passed.")
