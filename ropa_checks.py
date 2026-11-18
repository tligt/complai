"""
ropa_checks.py — S65 (D-186). Consistency checks over the processing register.

NO STREAMLIT. NO SUPABASE. NO I/O. Like tasks.py (D-61): the caller loads the
rows and the vocabulary metadata; this only reads them.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
Deterministic rules over one processing activity at a time, each returning a
finding with a severity, a message and the fields it is about. Advisory: a
finding never blocks a save, never blocks generation, and never touches a
score (scope lock in 3b: mixing register hygiene into document scoring
re-creates the DOC_OBLIGATIONS / DOC_SCORING_OBLIGATIONS conflation).

What already BLOCKS generation stays in inventory_store.readiness() and is not
repeated here: no legal basis, no retention, special categories with no Art. 9(2)
condition, legitimate interests with no balancing test, a processor activity
with no controller, a transfer with no safeguard. Those make a record wrong;
these make it doubtful. Reporting both would put the same fact on the page
twice under two severities.

No LLM, on purpose: the point of a rule is that it says the same thing every
time and can be read.

FINDING KEYS
------------
`<rule>` is stable per activity, so tasks.py can tell a finding that comes back
from a new one (see FINDING KEYS there). Never put a name or a date in it.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from i18n import tr  # S64 interface translation (D-164); the catalogue is keyed by the English

ERROR = "error"      # the record states something that cannot be right
WARNING = "warning"  # likely wrong, or likely to be challenged
INFO = "info"        # unfinished work, not a mistake

SEVERITY_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}

# Data subjects for whom consent is rarely freely given (Art. 7(4), recital 43;
# EDPB Guidelines 05/2020 on consent, §21–23: the imbalance of power in
# employment). Not unlawful as such — hence a warning, not an error.
IMBALANCED_SUBJECTS = ("employees", "job_applicants")

# A link role for which the vendor processes on the client's behalf, so Art. 28(3)
# requires a contract. The others (internal, independent recipient, joint
# controller) need a different instrument or none.
PROCESSOR_ROLES = ("processor", "sub_processor")

# dpa_status codes flagged is_gap in reference_values. Read from the vocabulary
# by the caller when it can; this is the fallback and matches the seed.
DPA_GAP_CODES = ("none", "requested", "unknown")


def _finding(rule: str, severity: str, message: str, *fields: str, **values: Any) -> dict[str, Any]:
    """`message` is the English template; translated, then filled in."""
    return {"rule": rule, "severity": severity,
            "message": tr(message).format(**values) if values else tr(message),
            "fields": list(fields)}


def has_structured_retention(a: Mapping[str, Any]) -> bool:
    """Whether the active phase is recorded as a period, not as a sentence.

    'indefinite' carries no number by design, so the unit alone counts.
    """
    unit = a.get("retention_unit")
    return bool(unit == "indefinite" or (unit and a.get("retention_value")))


def check_activity(
    a: Mapping[str, Any],
    *,
    links: Iterable[Mapping[str, Any]] = (),
    systems_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    client_country: str | None = None,
    retention_basis_meta: Mapping[str, Mapping[str, Any]] | None = None,
    dpa_gap_codes: Iterable[str] = DPA_GAP_CODES,
) -> list[dict[str, Any]]:
    """Findings for one activity, worst first.

    links: this activity's activity_systems rows (system_id, role).
    retention_basis_meta: code -> metadata for value_type 'retention_basis'
    (uses `statutory` and `jurisdiction`).
    """
    systems_by_id = systems_by_id or {}
    retention_basis_meta = retention_basis_meta or {}
    gap_codes = set(dpa_gap_codes)
    out: list[dict[str, Any]] = []

    specials = a.get("special_categories") or []
    subjects = a.get("data_subject_categories") or []

    # 1. The mirror image of readiness()'s Art. 9 rule. A condition with nothing
    # to justify either means a special category was left unticked — the record
    # then understates what is processed — or a leftover from an earlier edit.
    if a.get("art9_condition") and not specials:
        out.append(_finding(
            "art9_without_special_category", WARNING,
            "An Art. 9(2) condition is recorded, but no special category of data. "
            "Either tick the special categories processed, or clear the condition.",
            "art9_condition", "special_categories"))

    # 2. Consent where the person can hardly refuse.
    hit = [s for s in IMBALANCED_SUBJECTS if s in subjects]
    if a.get("legal_basis") == "consent" and hit:
        who = tr(" and ").join(tr("employees") if s == "employees" else tr("job applicants")
                               for s in hit)
        out.append(_finding(
            "consent_imbalance", WARNING,
            "Consent is the legal basis, and the people concerned include {who}. "
            "Consent from someone who depends on you is rarely freely given "
            "(Art. 7(4), EDPB guidelines on consent). Contract, legal obligation or "
            "legitimate interests usually fit better.",
            "legal_basis", "data_subject_categories", who=who))

    # 3–5. Retention, active phase. readiness() blocks when there is none at all.
    structured = has_structured_retention(a)
    if not structured and (a.get("retention_period") or "").strip():
        # D-48: never backfilled on purpose. This is how a client finds them.
        out.append(_finding(
            "retention_free_text", INFO,
            "Retention is still recorded as free text. Set it as a period and a "
            "reason, so it is shown correctly in every language.",
            "retention_period"))
    if a.get("retention_unit") == "indefinite":
        out.append(_finding(
            "retention_indefinite", WARNING,
            "Data is kept indefinitely. Personal data may be kept only as long as "
            "the purpose needs it (Art. 5(1)(e)); give a period, or a review date "
            "with the reason \"business need, reviewed periodically\".",
            "retention_unit"))
    if structured and not a.get("retention_basis_code"):
        out.append(_finding(
            "retention_without_reason", WARNING,
            "A retention period is set without saying why that period. Choose the "
            "reason — a legal requirement, the contract, a limitation period.",
            "retention_basis_code"))

    # 6. Archive phase. The database CHECK requires a basis on new writes; this
    # catches rows written before it or by another path.
    archive = bool(a.get("retention_archive_unit") or a.get("retention_archive_value"))
    if archive and not a.get("retention_archive_basis_code"):
        out.append(_finding(
            "archive_without_reason", ERROR,
            "An archive period is recorded with no reason. Keeping data after its "
            "active use needs its own justification, usually a legal requirement.",
            "retention_archive_basis_code"))

    # 7. A statutory reason that belongs to another country's law.
    country = (client_country or "").upper()
    for code_field, label in (("retention_basis_code", tr("active use")),
                              ("retention_archive_basis_code", tr("archive"))):
        code = a.get(code_field)
        meta = retention_basis_meta.get(code) or {}
        where = meta.get("jurisdiction")
        if country and meta.get("statutory") and where and country not in where:
            out.append(_finding(
                f"statutory_other_country:{code_field}", WARNING,
                "The reason given for the {label} period is a legal requirement of "
                "{where}, not of {country}. Check the period against "
                "your own country's law.",
                code_field, label=label, where=", ".join(where), country=country))

    # 8. A vendor that processes for this activity with no DPA in place.
    # readiness() lists vendors without a DPA once, for the whole inventory;
    # this names them where the processing happens.
    for link in links:
        if link.get("role") not in PROCESSOR_ROLES:
            continue
        sysrow = systems_by_id.get(link.get("system_id")) or {}
        if (sysrow.get("dpa_status") or "unknown") in gap_codes:
            out.append(_finding(
                f"processor_without_dpa:{link.get('system_id')}", WARNING,
                "{system} processes data for this activity "
                "as a processor, and no signed data processing agreement is recorded "
                "for it (Art. 28(3)).",
                "systems", system=sysrow.get("name") or tr("A system")))

    return sorted(out, key=lambda f: SEVERITY_ORDER[f["severity"]])


def check_all(
    activities: Iterable[Mapping[str, Any]],
    links: Iterable[Mapping[str, Any]],
    systems: Iterable[Mapping[str, Any]],
    **kw: Any,
) -> dict[str, list[dict[str, Any]]]:
    """activity id -> its findings, for the activities that have any."""
    systems_by_id = {s["id"]: s for s in systems}
    by_activity: dict[str, list[Mapping[str, Any]]] = {}
    for l in links:
        by_activity.setdefault(l["activity_id"], []).append(l)
    result = {}
    for a in activities:
        f = check_activity(a, links=by_activity.get(a["id"], []),
                           systems_by_id=systems_by_id, **kw)
        if f:
            result[a["id"]] = f
    return result


def counts(findings: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, int]:
    """How many findings of each severity, across all activities."""
    c = {ERROR: 0, WARNING: 0, INFO: 0}
    for lst in findings.values():
        for f in lst:
            c[f["severity"]] += 1
    return c
