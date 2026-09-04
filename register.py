"""
register.py — S27. What the document register MEANS, as pure functions.

NO STREAMLIT. NO SUPABASE. NO I/O.

Everything here takes plain data and returns plain data. The caller fetches the
rows and decides how to paint the answer; this module decides what the answer
is.

WHY
---
Two reasons, and the second is the one that matters day to day.

Portability: the logic that decides whether a client is covered should not be
entangled with the framework that draws the screen. Moving off Streamlit later
should be a rendering job, not a re-derivation of compliance rules.

Testability: `document_status()` can be exercised against a dozen awkward cases
in a second. The same logic written as branches inside a page can only be
tested by clicking, which in practice means it is not tested at all — and it
decides what a client is told about their own compliance.

THE DISTINCTION THIS MODULE EXISTS TO DRAW
------------------------------------------
"No Dutch privacy policy" is two different findings:

  NOT_GENERATED  the template exists; the client has not produced it.
                 Their action, and it counts against them.

  NOT_AVAILABLE  RECOSA has no template in that language yet.
                 Our action. The client cannot fix it, so it must not
                 count against them and must not be shown as their failure.

They look identical on a dashboard and are opposites. Scoring a client down
because a template was never written is a bill for our own backlog.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


# ── States, worst first ───────────────────────────────────────────────────
# Ordered deliberately: reduce() over a document's languages takes the worst,
# and "worst" has to mean something stable.

IN_FORCE      = "in_force"       # every required language is adopted
PARTIAL       = "partial"        # adopted in some languages, not all
DRAFT         = "draft"          # produced, never adopted
NOT_GENERATED = "not_generated"  # template exists, client has not produced it
NOT_AVAILABLE = "not_available"  # no template in that language — RECOSA's gap
ARCHIVED      = "archived"       # retired, nothing replaced it

STATE_LABELS = {
    IN_FORCE:      "In force",
    PARTIAL:       "In force in some languages",
    DRAFT:         "Draft — not adopted",
    NOT_GENERATED: "Not generated",
    NOT_AVAILABLE: "Not available yet",
    ARCHIVED:      "Archived",
}

# Whether a state is the CLIENT's to fix. NOT_AVAILABLE is not: no action of
# theirs changes it. Anything that consumes these states for scoring should
# read this rather than re-deciding, because the decision is easy to get
# backwards and expensive when it is.
CLIENT_ACTIONABLE = {
    IN_FORCE:      False,
    PARTIAL:       True,
    DRAFT:         True,
    NOT_GENERATED: True,
    NOT_AVAILABLE: False,
    ARCHIVED:      True,
}


def document_status(
    doc_type: str,
    languages: Iterable[str],
    register_rows: Mapping[str, Mapping[str, Any]] | None,
    template_languages: Iterable[str] | None,
) -> dict[str, Any]:
    """Where one document stands across every language it is needed in.

    Args:
        doc_type: the document's code, echoed back for convenience.
        languages: the languages this client's documents are produced in.
        register_rows: {language: register row} for this doc_type, or None.
            Rows are whatever the store returns; only `status`, `version`,
            `effective_from` and `superseded_on` are read.
        template_languages: languages RECOSA has an in-force template for, or
            None when unknown. **None is not the same as empty.** Empty means
            "we have no template", None means "we did not check" — and
            reporting our own gap on the strength of a failed lookup would
            tell a client we cannot help them when in fact we do not know.

    Returns a dict with `state`, the per-language breakdown, and
    `client_actionable`.
    """
    langs = [str(l).lower() for l in (languages or []) if l]
    rows = {str(k).lower(): v for k, v in (register_rows or {}).items()}
    tmpl = (
        None if template_languages is None
        else {str(l).lower() for l in template_languages}
    )

    in_force, drafts, not_generated, not_available, archived = [], [], [], [], []

    for lang in langs:
        row = rows.get(lang) or {}
        status = row.get("status")
        if status == "in_force":
            in_force.append(lang)
        elif status == "draft":
            drafts.append(lang)
        elif status == "archived":
            archived.append(lang)
        elif tmpl is not None and lang not in tmpl:
            # No template. Ours, and only assertable because tmpl is not None.
            not_available.append(lang)
        else:
            not_generated.append(lang)

    # A language RECOSA cannot produce is NOT held against the client, and the
    # exclusion is PER LANGUAGE, not per document.
    #
    # The first version excluded only documents whose every language was
    # unavailable. A client with NL and FR documents, a French DPA in force and
    # no Dutch template scored `partial` — and `coverage()` counted partial as
    # not covered, so a fully compliant client read 0/7. They had done
    # everything available to them and the product told them they had done
    # nothing.
    #
    # So the question is not "is every required language in force" but "is
    # every language we can actually serve in force". The unavailable ones stay
    # in the breakdown and in the note, because the gap is real and should be
    # visible — it is just not theirs.
    _blocking = drafts or not_generated
    if in_force and not _blocking:
        state = IN_FORCE
    elif in_force:
        state = PARTIAL
    elif drafts:
        # Produced and not adopted is NOT the same as nothing, and is
        # deliberately not treated as covered: the client is not operating
        # under it, and calling it done restores the false assurance the
        # adoption step was introduced to remove.
        state = DRAFT
    elif not_generated:
        # Something the client can act on outranks something they cannot. A
        # dashboard that leads with our gap buries their next action.
        state = NOT_GENERATED
    elif not_available:
        state = NOT_AVAILABLE
    elif archived:
        state = ARCHIVED
    else:
        state = NOT_GENERATED

    return {
        "doc_type": doc_type,
        "state": state,
        "label": STATE_LABELS[state],
        "client_actionable": CLIENT_ACTIONABLE[state],
        "in_force": in_force,
        "drafts": drafts,
        "not_generated": not_generated,
        "not_available": not_available,
        "archived": archived,
        "versions": {
            l: (rows.get(l) or {}).get("version")
            for l in in_force
        },
    }


def status_note(status: dict[str, Any], multilingual: bool = True) -> str:
    """One line naming the gaps and whose they are. '' when there are none.

    Single-language clients get nothing: naming the language when there is
    only one is noise, and the state label already says everything.
    """
    if not multilingual:
        return ""
    parts = []
    if status["in_force"] and (status["drafts"] or status["not_generated"]
                               or status["not_available"]):
        parts.append("in force in " + _langs(status["in_force"]))
    if status["drafts"]:
        parts.append("generated but not in force in " + _langs(status["drafts"]))
    if status["not_generated"]:
        parts.append("not generated in " + _langs(status["not_generated"]))
    if status["not_available"]:
        # Said plainly, and owned. A client reading "not available in NL" with
        # no explanation reasonably assumes it is something they failed to do.
        parts.append(
            "not available in " + _langs(status["not_available"])
            + " — no template yet, on us"
        )
    return " · ".join(parts)


def _langs(codes: list[str]) -> str:
    return ", ".join(c.upper() for c in codes)


def coverage(
    statuses: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Counts across a set of documents, EXCLUDING what the client cannot fix.

    `required` omits documents whose ONLY problem is a missing RECOSA template.
    A client's compliance percentage must not fall because we have not written
    a Dutch version — that is billing them for our backlog, and it is the kind
    of thing a competitor would put in a comparison table.

    `blocked_on_us` counts documents held up entirely by us; `partly_blocked`
    counts those in force in every language we can serve but still missing one
    we cannot. The second is the case that produced a 0% score for a client who
    had done everything available to them.
    """
    required = covered = blocked = partly = 0
    for st_ in statuses:
        if st_["state"] == NOT_AVAILABLE:
            blocked += 1
            continue
        required += 1
        if st_["state"] == IN_FORCE:
            covered += 1
            if st_["not_available"]:
                partly += 1
    return {
        "required": required,
        "covered": covered,
        "blocked_on_us": blocked,
        "partly_blocked": partly,
        "percent": round(100 * covered / required) if required else 0,
    }


def supersession_chain(rows: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Register rows for one (doc_type, language), newest first, chained.

    Each entry gains `supersedes` and `superseded_by_version`, resolved by
    following the id links rather than assuming version n was replaced by
    version n+1. Once a client can backdate an effective date, and once a
    version can be archived rather than superseded, that assumption breaks —
    and the chain is the thing an auditor reads to establish what applied when.
    """
    by_id = {r["id"]: r for r in rows if r.get("id")}
    out = []
    for r in sorted(
        by_id.values(),
        key=lambda x: (x.get("version") or 0, x.get("uploaded_at") or ""),
        reverse=True,
    ):
        successor = by_id.get(r.get("superseded_by") or "")
        predecessor = next(
            (p for p in by_id.values() if p.get("superseded_by") == r["id"]),
            None,
        )
        out.append({
            **r,
            "superseded_by_version": (successor or {}).get("version"),
            "supersedes": (predecessor or {}).get("version"),
        })
    return out
