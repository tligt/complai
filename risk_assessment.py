"""
risk_assessment.py — S30. When a DPIA is needed, and whether the risk is
acceptable.

NO STREAMLIT. NO SUPABASE. NO I/O. (D-61)

Two questions, both compliance verdicts, both testable without a database:

    who_needs_a_dpia()   which activities trigger Art. 35(1)
    consultation_needed()  whether Art. 36 prior consultation applies

ONE ENGINE, TWO CATALOGUES, TWO ACCEPTANCE RULES (D-85)
--------------------------------------------------------
The register and the workflow are shared. What a risk IS, and what makes it
acceptable, are not:

    DPIA   risk to the RIGHTS AND FREEDOMS OF NATURAL PERSONS (Art. 35(1))
           unacceptable residual risk -> Art. 36 prior consultation, before
           processing begins

    NIS2   risk to NETWORK AND INFORMATION SYSTEMS (Art. 21(2)(a))
           unacceptable residual risk -> a management decision, and nothing
           else

The failure to guard against is a generic "risk" that serves both by being
vague about which harm it measures. That is how a DPIA ends up reading like an
IT risk register, which is the commonest way DPIAs are done badly.

WHY THE TRIGGER IS THE VALUABLE HALF
------------------------------------
Art. 35(1) requires a DPIA where processing is likely to result in a high risk.
Art. 35(3) lists three cases; supervisory authorities publish their own lists
under Art. 35(4).

Most SMEs never ask the question. Telling a client WHICH of their activities
needs a DPIA is worth more than producing one, because it is the part they get
wrong — usually by not realising it applies to them at all.

Same shape as rights_in_play() in S28: an executable rule over the inventory,
not prose in a template. And the same conservatism — where RECOSA cannot tell,
it says so rather than concluding "not required".
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


# ── Scales ────────────────────────────────────────────────────────────────
# Four levels, deliberately. Three collapses everything to "medium"; five
# invites false precision about the difference between 2 and 3.
#
# NOT multiplied together. Likelihood x severity produces a number that looks
# objective and is not — a 1x4 and a 4x1 are the same product and completely
# different situations. The register keeps both dimensions and a person
# decides (D-85).

NEGLIGIBLE = 1
LIMITED    = 2
SIGNIFICANT = 3
MAXIMUM    = 4

LEVELS = {
    NEGLIGIBLE:  {"en": "Negligible", "fr": "Négligeable", "nl": "Verwaarloosbaar"},
    LIMITED:     {"en": "Limited",    "fr": "Limitée",     "nl": "Beperkt"},
    SIGNIFICANT: {"en": "Significant","fr": "Importante",  "nl": "Aanzienlijk"},
    MAXIMUM:     {"en": "Maximum",    "fr": "Maximale",    "nl": "Maximaal"},
}


def level_label(level: int | None, language: str = "en") -> str:
    if level not in LEVELS:
        return "—"
    return LEVELS[level].get(language) or LEVELS[level]["en"]


# ── Art. 35 triggers ──────────────────────────────────────────────────────
#
# Each returns a reason string when it fires, or None. Reasons are what the
# client reads — "this activity needs a DPIA" is useless without "because".

TRIGGER_ART35_3A = "art35_3a"   # systematic and extensive automated evaluation
TRIGGER_ART35_3B = "art35_3b"   # large scale special category or criminal data
TRIGGER_ART35_3C = "art35_3c"   # systematic monitoring of a public area
TRIGGER_SCALE    = "large_scale"
TRIGGER_VULNERABLE = "vulnerable_subjects"
TRIGGER_UNKNOWN  = "cannot_tell"

# Data subject categories the EDPB treats as vulnerable — an imbalance of
# power makes objection harder, which RAISES the risk rather than lowering it.
_VULNERABLE = {"employees", "children", "patients", "job_applicants",
               "students", "vulnerable_adults"}

# What "large scale" means is a judgement (Recital 91), and the inventory holds
# no headcount. So this NEVER concludes "large scale" on its own — it reports
# that it cannot tell, which is a different answer from "no".
_LARGE_SCALE_HINTS = {"customers", "website_visitors", "patients", "public"}


def _has(activity: Mapping[str, Any], field: str) -> bool:
    return bool(activity.get(field))


def dpia_triggers(activity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Why this activity might need a DPIA. Empty means no trigger fired.

    Empty is NOT "no DPIA needed": Art. 35(1) is a general test and Art. 35(4)
    lets each authority add to the list. It means nothing RECOSA can see fires,
    which is what the caller reports.
    """
    out: list[dict[str, Any]] = []
    subjects = set(activity.get("data_subject_categories") or [])

    if _has(activity, "special_categories") or _has(activity, "criminal_data"):
        # Art. 35(3)(b) says "on a large scale", and scale is a judgement
        # RECOSA cannot make. Reported as a trigger with that caveat rather
        # than withheld: a client processing health data should be asked the
        # question even if the answer turns out to be no.
        out.append({
            "code": TRIGGER_ART35_3B,
            "article": "Art. 35(3)(b)",
            "reason": "Special category or criminal offence data is processed. "
                      "A DPIA is required where this is done on a large scale — "
                      "whether it is, is your judgement.",
            "certain": False,
        })

    if subjects & _VULNERABLE:
        named = sorted(subjects & _VULNERABLE)
        out.append({
            "code": TRIGGER_VULNERABLE,
            "article": "EDPB WP248 criterion 7",
            "reason": "Data about people in a weaker position — "
                      + ", ".join(named).replace("_", " ")
                      + ". An imbalance of power makes objection harder, which "
                        "raises the risk rather than lowering it.",
            "certain": False,
        })

    if subjects & _LARGE_SCALE_HINTS:
        out.append({
            "code": TRIGGER_SCALE,
            "article": "Recital 91",
            "reason": "Data about a broad population. Scale is one of the "
                      "criteria, and RECOSA holds no numbers — only you know "
                      "how many people this covers.",
            "certain": False,
        })

    return out


def needs_dpia(activity: Mapping[str, Any]) -> dict[str, Any]:
    """A verdict per activity: required, likely, or nothing visible.

    Never returns "not required". Art. 35(1) is a general standard and Art.
    35(4) lets authorities extend it, so the absence of a visible trigger is
    the absence of a check, not a negative result — the D-60 shape, and the
    third time in this codebase that distinction has had to be made explicit.
    """
    triggers = dpia_triggers(activity)
    if not triggers:
        return {
            "verdict": "no_trigger_seen",
            "triggers": [],
            "detail": "Nothing RECOSA can see triggers a DPIA for this "
                      "activity. That is not the same as none being needed — "
                      "your supervisory authority publishes its own list.",
        }
    return {
        "verdict": "likely_required",
        "triggers": triggers,
        "detail": f"{len(triggers)} criterion/criteria apply. Two or more "
                  "usually means a DPIA is expected.",
    }


def activities_needing_dpia(
    activities: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Every activity with at least one trigger, worst first."""
    out = []
    for a in activities:
        v = needs_dpia(a)
        if v["verdict"] == "likely_required":
            out.append({**v, "activity_id": a.get("id"),
                        "activity_name": a.get("name")})
    return sorted(out, key=lambda x: -len(x["triggers"]))


# ── Acceptance ────────────────────────────────────────────────────────────

def consultation_needed(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Whether Art. 36 prior consultation applies to a DPIA.

    Art. 36(1): where a DPIA indicates the processing would result in a high
    risk IN THE ABSENCE OF MEASURES to mitigate it, the controller consults the
    supervisory authority BEFORE processing.

    So the test is on RESIDUAL risk — after mitigation — and the threshold is
    high. Implemented as: residual severity is Maximum, or residual severity is
    Significant with residual likelihood Significant or above.

    **This is the point of a DPIA.** Most templates bury it. A client who
    mitigates to medium and files the document has done the work; one who
    leaves a high residual risk and starts processing has broken Art. 36 and
    does not know it.

    An item with no residual assessment recorded counts as UNRESOLVED, not as
    acceptable. A risk nobody has finished assessing is not a risk that was
    found acceptable.
    """
    items = list(items)
    if not items:
        # An empty assessment is not a passed one.
        #
        # "No residual risk reaches the threshold" is true of zero risks and
        # reads as a green light. Absence rendering as a positive result — the
        # same shape as a task list saying "nothing outstanding" because it was
        # looking at the wrong field.
        return {
            "required": None,
            "high_items": [],
            "unresolved": [],
            "detail": "No risks have been recorded yet, so whether prior "
                      "consultation is needed cannot be answered.",
        }

    high, unresolved = [], []
    for it in items:
        sev = it.get("residual_severity")
        lik = it.get("residual_likelihood")
        if sev is None or lik is None:
            unresolved.append(it)
            continue
        if sev == MAXIMUM or (sev == SIGNIFICANT and lik >= SIGNIFICANT):
            high.append(it)

    return {
        "required": bool(high),
        "high_items": high,
        "unresolved": unresolved,
        "detail": (
            "Residual risk remains high after mitigation. Under Art. 36(1) the "
            "supervisory authority must be consulted BEFORE this processing "
            "begins."
            if high else
            "No residual risk reaches the Art. 36 threshold."
            if not unresolved else
            "No residual risk reaches the Art. 36 threshold, but some risks "
            "have not been assessed after mitigation — until they are, this "
            "cannot be concluded."
        ),
    }


def nis2_unaccepted(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The NIS2 equivalent, and deliberately NOT the same rule.

    There is no Art. 36 here. A high residual risk on a network and information
    system is a management decision — Art. 20(1) makes the management body
    approve the measures and supervise their implementation, so what it needs
    is a named person accepting it, not an authority consulted.

    Sharing the DPIA's threshold would have been easy and would have implied a
    consequence that does not exist.
    """
    items = list(items)
    if not items:
        return {
            "high_items": [],
            "unaccepted": [],
            "detail": "No risks have been recorded yet.",
        }

    high, unaccepted = [], []
    for it in items:
        sev = it.get("residual_severity")
        lik = it.get("residual_likelihood")
        if sev is not None and lik is not None and (
            sev == MAXIMUM or (sev == SIGNIFICANT and lik >= SIGNIFICANT)
        ):
            high.append(it)
            if not (it.get("accepted_by") or "").strip():
                unaccepted.append(it)

    return {
        "high_items": high,
        "unaccepted": unaccepted,
        "detail": (
            f"{len(unaccepted)} high residual risk(s) have not been formally "
            "accepted. Art. 20(1) puts approval of the measures on the "
            "management body — an unaccepted risk is a decision nobody has "
            "made."
            if unaccepted else
            "Every high residual risk has been accepted by a named person."
        ),
    }


def summarise(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Counts by residual severity. Deliberately not a score.

    A single figure invites comparison between assessments that measure
    different things, and hides the one risk that matters behind nineteen that
    do not.
    """
    out = {"total": 0, "assessed": 0, "unassessed": 0,
           **{lvl: 0 for lvl in LEVELS}}
    for it in items:
        out["total"] += 1
        sev = it.get("residual_severity")
        if sev in LEVELS:
            out["assessed"] += 1
            out[sev] += 1
        else:
            out["unassessed"] += 1
    return out
