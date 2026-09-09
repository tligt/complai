"""
obligation_register.py — S29. What each obligation's status IS.

NO STREAMLIT. NO SUPABASE. NO I/O. (D-61)

Takes the inventory, the client record and whatever the gap assessment
produced; returns a verdict per obligation. The caller fetches and renders.

WHY THIS IS NOT A FOURTH EVALUATOR
----------------------------------
There were already two ways an obligation got a status:

  profile question   21 obligations. Ask the client, map their answer through
                     PROFILE_QUESTIONS.compliant_answers.
  document analysis  16 obligations. Send the document text to Mistral and ask
                     whether it satisfies the requirement.

That leaves most of the catalogue with no evaluation at all, and one obligation
— gdpr_04, "DPO appointed if required" — where RECOSA asks the client a
question it can answer from the client record it already holds.

So this module does not add a parallel verdict. It adds the missing one, and
imposes an order on all of them.

PRECEDENCE
----------
    1. derived     RECOSA knows, from the S24/S26 inventory
    2. document    the document register says a document is in force
    3. analysed    the gap assessment read the document and judged it
    4. declared    the client answered a question, or wrote a statement
    5. unknown     nothing has been recorded

Higher beats lower, and the reason is that each level is harder to be wrong
about than the one below. A DPA recorded against every processor system is a
fact; a client answering "yes, we have DPAs" is a claim. Where a derivation
exists, the question should be retired rather than both being kept — two
answers to one question is the divergence pattern, and the whole point of
having a source of truth is that there is one.

WHAT DERIVATION IS NOT
----------------------
A derivation says what the inventory RECORDS, never what is TRUE. "Every
processor system has a DPA recorded" is a statement about the register, and it
is exactly the statement an auditor wants — they can check the register against
reality themselves. Every derived verdict therefore carries the evidence it was
computed from, so the client can see what would change it.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping


# ── Statuses ──────────────────────────────────────────────────────────────
# Deliberately the SAME vocabulary gap_assessment already emits. A register
# that graded obligations differently from the gap assessment would be two
# scores for one thing, which is the problem it exists to solve.

COMPLIANT      = "compliant"
PARTIAL        = "partial"
MISSING        = "missing"
NOT_APPLICABLE = "not_applicable"
UNKNOWN        = "unknown"

# How the verdict was reached. Shown to the client, because "we worked this out
# from your systems inventory" and "you told us so" deserve different levels of
# trust, and only one of them is evidence.
SOURCE_DERIVED  = "derived"
SOURCE_DOCUMENT = "document"
SOURCE_ANALYSED = "analysed"
SOURCE_DECLARED = "declared"
SOURCE_NONE     = "none"

_PRECEDENCE = {
    SOURCE_DERIVED: 5,
    SOURCE_DOCUMENT: 4,
    SOURCE_ANALYSED: 3,
    SOURCE_DECLARED: 2,
    SOURCE_NONE: 1,
}


def _verdict(status: str, source: str, detail: str = "",
             evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "source": source,
        "detail": detail,
        "evidence": evidence or [],
    }


# ── Derivations ───────────────────────────────────────────────────────────
# One function per obligation RECOSA can answer from its own data. Each takes
# the same context and returns a verdict or None.
#
# None means "this derivation does not apply", NOT "not compliant". A client
# with no processor systems is not failing gdpr_05 — there is nothing to
# derive, and the register falls through to the next source. Conflating the two
# is the D-60 shape: absence of a check is not a negative result.

_PROCESSOR_ROLES = {"processor", "sub_processor"}

# The EEA, by country code, plus the aggregate values the inventory also uses.
#
# NOT `country != "EU"`. That treated "BE" as a third country and told a
# Belgian client their Belgian payroll provider was an international transfer —
# a Chapter V finding against processing that never leaves the country. The
# inventory stores real country codes, so the test has to know which ones are
# inside.
#
# The UK is deliberately absent: it is a third country with an adequacy
# decision, which is a Chapter V transfer requiring a safeguard, not a
# non-transfer. Adequacy makes the safeguard easy, not unnecessary.
_EEA = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",           # EU 27
    "IS", "LI", "NO",           # EEA EFTA
    "EU", "EEA", "",            # aggregates the inventory also accepts
}


def _outside_eea(system: Mapping[str, Any]) -> bool:
    """True where processing leaves the EEA. Unknown counts as inside.

    An unrecorded country is a gap in the inventory, not evidence of a
    transfer, and readiness() already reports it as a gap. Reporting it here as
    a Chapter V failure would be the same absence-is-a-negative-result error as
    D-60.
    """
    return (system.get("processing_country") or "EU").strip().upper() not in _EEA


def _derive_dpo(ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """gdpr_04 — DPO appointed if required.

    Replaces a profile question that asks the client something the client
    record holds. Note it cannot decide whether one is REQUIRED (Art. 37
    turns on core activities and scale, neither of which is modelled), so an
    absent DPO is reported as unknown rather than as a failure.
    """
    client = ctx["client"]
    name = (client.get("dpo_name") or "").strip()
    email = (client.get("dpo_email") or "").strip()
    if name and email:
        return _verdict(COMPLIANT, SOURCE_DERIVED,
                        "A DPO is recorded with contact details.",
                        [f"DPO: {name}"])
    if name or email:
        return _verdict(PARTIAL, SOURCE_DERIVED,
                        "A DPO is recorded but the contact details are "
                        "incomplete. Art. 37(7) requires them to be published "
                        "and given to the supervisory authority.")
    return None


def _derive_processor_dpas(ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """gdpr_05 — DPAs with all processors.

    Derived from systems.dpa_status across systems attached to activities with
    a processor-role link. A vendor that never touches personal data on the
    client's behalf is not in scope and is not counted against them.
    """
    systems = {s["id"]: s for s in ctx["systems"]}
    processor_ids = {
        l["system_id"] for l in ctx["links"]
        if (l.get("role") or "") in _PROCESSOR_ROLES
    }
    if not processor_ids:
        return None

    signed, missing = [], []
    for sid in processor_ids:
        s = systems.get(sid)
        if not s:
            continue
        name = s.get("vendor_legal_name") or s.get("name") or sid
        (signed if s.get("dpa_status") == "signed" else missing).append(name)

    if not signed and not missing:
        return None
    if not missing:
        return _verdict(COMPLIANT, SOURCE_DERIVED,
                        f"A DPA is recorded for all {len(signed)} processors.",
                        sorted(signed))
    return _verdict(
        PARTIAL if signed else MISSING, SOURCE_DERIVED,
        f"{len(missing)} of {len(signed) + len(missing)} processors have no "
        "DPA recorded.",
        sorted(missing),
    )


def _derive_transfers(ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """gdpr_11 — international transfer safeguards.

    Nothing to derive where nothing leaves the EEA, which is a common and
    correct state — hence None rather than COMPLIANT. Reporting "compliant" for
    an obligation that never engaged inflates a score with an achievement
    nobody earned.
    """
    outside = [s for s in ctx["systems"] if _outside_eea(s)]
    if not outside:
        return None

    unsafeguarded = [
        s.get("vendor_legal_name") or s.get("name") or s["id"]
        for s in outside if not s.get("transfer_mechanism")
    ]
    if not unsafeguarded:
        return _verdict(
            COMPLIANT, SOURCE_DERIVED,
            f"All {len(outside)} transfers outside the EEA have a safeguard "
            "recorded.",
            [f"{s.get('vendor_legal_name') or s.get('name')} "
             f"({s.get('processing_country')})" for s in outside],
        )
    return _verdict(
        MISSING, SOURCE_DERIVED,
        f"{len(unsafeguarded)} transfer(s) outside the EEA have no Chapter V "
        "safeguard recorded.",
        sorted(unsafeguarded),
    )


def _derive_art9(ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """gdpr_16 — special category safeguards.

    An Art. 9 category with no Art. 9(2) condition is not a gap, it is a
    contradiction: the processing is prohibited unless a condition applies, so
    recording the data without one asserts something unlawful. Reported as
    MISSING and never as PARTIAL.
    """
    with_special = [a for a in ctx["activities"] if a.get("special_categories")]
    if not with_special:
        return None

    unconditioned = [
        a.get("name") or a["id"] for a in with_special
        if not a.get("art9_condition")
    ]
    if not unconditioned:
        return _verdict(
            COMPLIANT, SOURCE_DERIVED,
            f"All {len(with_special)} activities processing special category "
            "data name an Art. 9(2) condition.",
            [a.get("name") or a["id"] for a in with_special],
        )
    return _verdict(
        MISSING, SOURCE_DERIVED,
        "Special category data is recorded without an Art. 9(2) condition. "
        "The processing is prohibited unless one applies.",
        sorted(unconditioned),
    )


def _derive_joint_controllers(ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """gdpr_17 — joint controller arrangement documented.

    The role is on the JOIN (S24), so this counts vendors acting as joint
    controllers for at least one activity. RECOSA cannot see whether an Art. 26
    arrangement exists — it holds no such document type — so the verdict is
    PARTIAL with the vendors named, never COMPLIANT. Saying otherwise would
    assert a document nobody has seen.
    """
    systems = {s["id"]: s for s in ctx["systems"]}
    joint = {
        l["system_id"] for l in ctx["links"]
        if (l.get("role") or "") == "joint_controller"
    }
    if not joint:
        return None
    names = sorted(
        (systems[sid].get("vendor_legal_name") or systems[sid].get("name") or sid)
        for sid in joint if sid in systems
    )
    return _verdict(
        PARTIAL, SOURCE_DERIVED,
        "Joint controllers are recorded. Art. 26 requires an arrangement "
        "setting out respective responsibilities; RECOSA cannot see whether "
        "one exists.",
        names,
    )


def _derive_lia(ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """gdpr_18 — legitimate interest assessment documented."""
    li = [a for a in ctx["activities"]
          if a.get("legal_basis") == "legitimate_interests"]
    if not li:
        return None
    without = [
        a.get("name") or a["id"] for a in li
        if not (a.get("legitimate_interest_note") or "").strip()
    ]
    if not without:
        return _verdict(
            COMPLIANT, SOURCE_DERIVED,
            f"All {len(li)} activities relying on legitimate interests record "
            "a balancing test.",
            [a.get("name") or a["id"] for a in li],
        )
    return _verdict(
        PARTIAL if len(without) < len(li) else MISSING, SOURCE_DERIVED,
        f"{len(without)} of {len(li)} legitimate interest activities have no "
        "balancing test recorded.",
        sorted(without),
    )


def _derive_security_measures(ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """gdpr_20 — technical and organisational measures documented.

    Art. 32 is about measures being APPROPRIATE, which no derivation can judge.
    This reports coverage — whether measures are recorded at all — and says so,
    rather than implying RECOSA has assessed their adequacy.
    """
    acts = ctx["activities"]
    if not acts:
        return None
    without = [a.get("name") or a["id"] for a in acts
               if not (a.get("security_measures") or [])]
    if not without:
        return _verdict(
            COMPLIANT, SOURCE_DERIVED,
            f"Security measures are recorded against all {len(acts)} "
            "activities. Whether they are appropriate under Art. 32 is a "
            "judgement RECOSA does not make.",
        )
    return _verdict(
        PARTIAL if len(without) < len(acts) else MISSING, SOURCE_DERIVED,
        f"{len(without)} of {len(acts)} activities have no security measures "
        "recorded.",
        sorted(without),
    )


DERIVATIONS: dict[str, Callable[[Mapping[str, Any]], dict | None]] = {
    "gdpr_04": _derive_dpo,
    "gdpr_05": _derive_processor_dpas,
    "gdpr_11": _derive_transfers,
    "gdpr_16": _derive_art9,
    "gdpr_17": _derive_joint_controllers,
    "gdpr_18": _derive_lia,
    "gdpr_20": _derive_security_measures,
}


# ── How an obligation is answered ─────────────────────────────────────────
# Which control the client is offered. A classification, not a rendering
# decision, so it lives here where it can be tested rather than in the page.
#
# Forcing one shape on all 54 is what makes compliance tools feel like
# paperwork: an obligation RECOSA can answer, one that needs a document, and
# one that needs a person to confirm they did something are three different
# questions, and asking them the same way makes two of them wrong.

KIND_DERIVED     = "derived"       # RECOSA answers it from the inventory
KIND_DOCUMENT    = "document"      # a document satisfies it
KIND_ACKNOWLEDGE = "acknowledge"   # an act: who did it, and when
KIND_TRACKED     = "tracked"       # lives elsewhere in the product
KIND_STATEMENT   = "statement"     # the client describes what they do

# Acts rather than artefacts. There is no document to produce and no data to
# derive — someone did a thing on a date, and the register records who says so.
_ACKNOWLEDGE = {
    "nis2_11",   # registered with the national NIS2 authority
    "nis2_12",   # management body approved the cybersecurity policy
    "ai_01",     # AI literacy measures in place for staff using AI
}

# Tracked elsewhere in the product. The register shows the status and links; it
# does not hold a second copy, because two places recording the same fact is
# the divergence pattern.
#
# S50 (skills matrix and training register) is not built. Until it is, these
# fall back to a statement — a link to a page that does not exist is worse than
# a text box.
_TRACKED: dict[str, str] = {
    # "gdpr_13": "training",   # employee data protection training  — S50
    # "nis2_09": "training",   # security awareness training        — S50
}


def check_ids(catalogue_ids: Iterable[str]) -> list[str]:
    """Ids named in this module that are not in the catalogue.

    Every set and dict here is keyed by obligation id, and a wrong id fails
    SILENTLY: the obligation classifies as a statement and nobody notices. This
    happened during S29 — `ai_04` was written where `ai_01` was meant, and the
    only symptom was an obligation getting the wrong control.

    Call it from a startup check or a test. An empty list is the pass.
    """
    known = set(catalogue_ids)
    named = set(DERIVATIONS) | _ACKNOWLEDGE | set(_TRACKED)
    return sorted(named - known)


def response_kind(obligation: Mapping[str, Any]) -> str:
    """Which control this obligation is answered with."""
    ob_id = obligation.get("id", "")
    if ob_id in DERIVATIONS:
        return KIND_DERIVED
    if ob_id in _TRACKED:
        return KIND_TRACKED
    if obligation.get("doc_type"):
        return KIND_DOCUMENT
    if ob_id in _ACKNOWLEDGE:
        return KIND_ACKNOWLEDGE
    return KIND_STATEMENT


# ── Composition ───────────────────────────────────────────────────────────

def evaluate(
    obligations: Iterable[Mapping[str, Any]],
    ctx: Mapping[str, Any],
    document_status: Mapping[str, str] | None = None,
    gap_results: Mapping[str, Mapping[str, Any]] | None = None,
    responses: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """A verdict per obligation, highest-precedence source winning.

    Args:
        obligations: the applicable subset of the catalogue.
        ctx: {"client", "activities", "systems", "links"} — the inventory.
        document_status: {doc_type: register status} from S27.
        gap_results: {obligation_id: {"status", "explanation"}} from the last
            gap assessment.
        responses: {obligation_id: obligation_responses row} — what the client
            recorded in this register.
    """
    document_status = document_status or {}
    gap_results = gap_results or {}
    responses = responses or {}
    out: dict[str, dict[str, Any]] = {}

    for ob in obligations:
        ob_id = ob["id"]
        candidates: list[dict[str, Any]] = []

        # A client marking something not applicable ends the question. They
        # know their business; the register records the reason and moves on.
        resp = responses.get(ob_id) or {}
        if resp.get("status") == NOT_APPLICABLE:
            out[ob_id] = _verdict(
                NOT_APPLICABLE, SOURCE_DECLARED,
                resp.get("not_applicable_reason") or "Marked not applicable.",
            )
            continue

        fn = DERIVATIONS.get(ob_id)
        if fn:
            v = fn(ctx)
            if v:
                candidates.append(v)

        doc = ob.get("doc_type")
        if doc and document_status.get(doc) == "in_force":
            candidates.append(_verdict(
                COMPLIANT, SOURCE_DOCUMENT,
                "A document satisfying this obligation is in force.",
            ))

        gap = gap_results.get(ob_id)
        if gap and gap.get("status"):
            candidates.append(_verdict(
                gap["status"], SOURCE_ANALYSED,
                gap.get("explanation") or "",
            ))

        if resp.get("status") in (COMPLIANT, PARTIAL, MISSING):
            candidates.append(_verdict(
                resp["status"], SOURCE_DECLARED,
                (resp.get("statement_i18n") or {}).get("en")
                or "Recorded by the client.",
            ))

        if not candidates:
            out[ob_id] = _verdict(
                UNKNOWN, SOURCE_NONE,
                "Nothing recorded yet.",
            )
            continue

        candidates.sort(key=lambda v: _PRECEDENCE[v["source"]], reverse=True)
        out[ob_id] = candidates[0]

    return out


def counts(verdicts: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """Counts by status. Deliberately NOT a percentage.

    The dashboard publishes a coverage figure computed a different way. Two
    numbers claiming to measure the same thing, differing, in one product is
    worse than one honest low number — so this reports states and the two are
    reconciled in a single later sprint, with the explanation shipped alongside.
    """
    out = {k: 0 for k in
           (COMPLIANT, PARTIAL, MISSING, NOT_APPLICABLE, UNKNOWN)}
    for v in verdicts.values():
        out[v["status"]] = out.get(v["status"], 0) + 1
    return out
