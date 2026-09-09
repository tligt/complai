"""
tasks.py — S29. What is outstanding, derived from the things that know.

NO STREAMLIT. NO SUPABASE. NO I/O. (D-61)

Each producer takes data and returns findings. The register composes them; it
does not know what any individual producer looks at.

DERIVED STATE, STORED HISTORY
-----------------------------
The open list is computed on every read. Nothing stores "this task is open".

Stored rows drift: a task whose underlying gap was fixed elsewhere — the
translation confirmed, the document adopted, the retention structured — sits
there claiming to be open until something reconciles it, and reconciliation is
where these systems rot.

So a task is open because a producer still reports it. When the producer stops,
the task is gone and its closure is recorded in task_events, which survives the
task itself. That is the only reason to have a register rather than a query:
*a gap was found on one date and closed on another.*

FINDING KEYS
------------
Every finding carries a stable key — producer plus subject, e.g.
`translation:activity:<uuid>:purpose:fr`.

Without it, a finding that disappears and comes back cannot be told from a new
one, and the history becomes a list of unrelated events. The key must not
contain anything that changes while the finding is the same thing: not the
activity's name, not a date, not a count.

PRODUCERS THAT DO NOT EXIST YET
-------------------------------
S55 (consistency) and S57 (heartbeat) are not built. A producer that is not
registered contributes nothing, and adding one later is registering a function.
Nothing here depends on them.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Mapping


# ── Severity ──────────────────────────────────────────────────────────────
# Ordered worst first, and deliberately NOT the same vocabulary as obligation
# status. A task is a piece of work; an obligation is a legal position. A
# translation awaiting review is real work and no kind of legal failure.

BLOCKING = "blocking"   # something cannot be produced until this is done
DUE      = "due"        # a date has passed
OPEN     = "open"       # outstanding, no deadline

_SEVERITY_ORDER = {BLOCKING: 0, DUE: 1, OPEN: 2}


def _finding(
    producer: str, key: str, title: str, severity: str = OPEN,
    detail: str = "", due: date | None = None, link: str | None = None,
) -> dict[str, Any]:
    return {
        "producer": producer,
        "finding_key": f"{producer}:{key}",
        "title": title,
        "severity": severity,
        "detail": detail,
        "due": due,
        "link": link,
    }


# ── Producers ─────────────────────────────────────────────────────────────

def obligations_due(
    verdicts: Mapping[str, Mapping[str, Any]],
    responses: Mapping[str, Mapping[str, Any]],
    catalogue: Mapping[str, Mapping[str, Any]],
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Obligations whose review has come round, or which nothing addresses.

    An obligation the client marked not_applicable produces nothing: they
    answered it, and re-raising an answered question is how a register teaches
    people to ignore it.
    """
    today = today or date.today()
    out = []
    for ob_id, v in verdicts.items():
        if v["status"] == "not_applicable":
            continue
        ob = catalogue.get(ob_id) or {}
        title = ob.get("title") or ob_id

        due = (responses.get(ob_id) or {}).get("review_due")
        if isinstance(due, str) and due:
            try:
                due = datetime.fromisoformat(due[:10]).date()
            except ValueError:
                due = None
        if due and due <= today:
            out.append(_finding(
                "obligation", f"{ob_id}:review", f"Review due: {title}",
                DUE, f"Last reviewed {(responses.get(ob_id) or {}).get('reviewed_at') or 'never'}.",
                due, link="obligations",
            ))
            continue

        # Only 'missing' and 'unknown'. 'partial' is progress and the client
        # knows; raising it as a task alongside things they have not started
        # flattens a distinction they need.
        if v["status"] in ("missing", "unknown"):
            out.append(_finding(
                "obligation", ob_id, title, OPEN,
                v.get("detail") or "", link="obligations",
            ))
    return out


def translations_outstanding(
    activities: Iterable[Mapping[str, Any]],
    doc_languages: Iterable[str],
) -> list[dict[str, Any]]:
    """Text that is missing, or drafted and unconfirmed, in a document language.

    TWO findings, not one, and the first version only reported the second.

    An activity with NO French text produces nothing from a check that reads
    translation_status, because it has no status to read — it is an absence,
    not a draft. So a task list built on status alone said "nothing
    outstanding" to a client whose French policy was rendering English.

    **The missing one is the worse of the two.** An unconfirmed draft still
    renders in the right language; a missing translation falls back to another
    language, so the document silently carries text the reader cannot read.
    That is the defect S26C exists to fix.

    Only for languages this client's documents are produced in. An unreviewed
    German draft on a client who produces nothing in German is not work — it is
    a row in a table.
    """
    langs = [l for l in doc_languages if l]
    out = []
    for a in activities:
        status = a.get("translation_status") or {}
        status = status if isinstance(status, Mapping) else {}
        name = (a.get("name_i18n") or {}).get("en") or a.get("name") or a["id"]

        for field in ("name", "purpose"):
            blob = a.get(f"{field}_i18n") or {}
            blob = blob if isinstance(blob, Mapping) else {}
            for lang in langs:
                text = (blob.get(lang) or "").strip()

                if not text:
                    out.append(_finding(
                        "translation", f"activity:{a['id']}:{field}:{lang}:missing",
                        f"Add the {lang.upper()} {field} for “{name}”",
                        # DUE, not OPEN. Documents produced in that language
                        # are already wrong, whereas an unconfirmed draft is
                        # merely unverified.
                        DUE,
                        f"Documents produced in {lang.upper()} fall back to "
                        "another language for this. Open the activity and save "
                        "it — the translation is drafted automatically.",
                        link="inventory",
                    ))
                elif (status.get(field) or {}).get(lang) == "machine_unreviewed":
                    out.append(_finding(
                        "translation", f"activity:{a['id']}:{field}:{lang}",
                        f"Confirm the {lang.upper()} {field} for “{name}”",
                        OPEN,
                        "Drafted automatically. It appears in documents "
                        "produced in that language until you confirm it.",
                        link="inventory",
                    ))
    return out


# Kept: the register imports by name and renaming a producer silently drops
# whatever still calls the old one.
translations_awaiting_review = translations_outstanding


def documents_outstanding(
    register_rows: Iterable[Mapping[str, Any]],
    doc_labels: Mapping[str, str],
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Drafts never adopted, and superseded versions nearing deletion."""
    today = today or date.today()
    out = []
    for r in register_rows:
        label = doc_labels.get(r.get("document_type"), r.get("document_type"))
        lang = (r.get("language") or "").upper()

        if r.get("status") == "draft":
            out.append(_finding(
                "document", f"draft:{r['id']}",
                f"{label} ({lang}) was generated but never put in force",
                OPEN,
                "Until it is adopted, it is not what your organisation "
                "operates under.",
                link="documents",
            ))

        keep = r.get("retain_until")
        if isinstance(keep, str) and keep and not r.get("legal_hold"):
            try:
                keep_d = datetime.fromisoformat(keep[:10]).date()
            except ValueError:
                continue
            if 0 <= (keep_d - today).days <= 30:
                out.append(_finding(
                    "document", f"retention:{r['id']}",
                    f"{label} v{r.get('version')} ({lang}) reaches the end of "
                    "its retention period",
                    DUE,
                    "Download a copy if you need one, or place it on hold if "
                    "it is relevant to a live matter.",
                    keep_d, link="compliance_record",
                ))
    return out


def inventory_gaps(readiness: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Gaps that BLOCK a register from being produced.

    readiness() already computes these; this reports them where the client
    looks for outstanding work rather than only where they were found.
    """
    if not readiness:
        return []
    out = []
    for msg in readiness.get("blocking") or []:
        out.append(_finding(
            "readiness", f"blocking:{_slug(msg)}", msg, BLOCKING,
            "A record cannot be produced until this is resolved.",
            link="inventory",
        ))
    return out


def _slug(text: str) -> str:
    """A stable key from a message. Lowercased, alphanumerics and colons only.

    The message IS the identity here, because readiness() returns prose rather
    than ids. Fragile — a reworded message reads as a new finding and closes
    the old one — so it is the first thing to replace if readiness() ever
    returns structured findings.
    """
    return "".join(c if c.isalnum() else "-" for c in text.lower())[:80]


# ── Composition ───────────────────────────────────────────────────────────

PRODUCERS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "obligation":  obligations_due,
    "translation": translations_outstanding,
    "document":    documents_outstanding,
    "readiness":   inventory_gaps,
}


def collect(*finding_lists: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge producer output, worst first, then by due date.

    Deduplicated on finding_key: two producers reporting the same thing is a
    bug, but it should show up as one task rather than as two.
    """
    seen: dict[str, dict] = {}
    for lst in finding_lists:
        for f in lst or []:
            seen.setdefault(f["finding_key"], dict(f))
    return sorted(
        seen.values(),
        key=lambda f: (
            _SEVERITY_ORDER.get(f["severity"], 9),
            f["due"] or date.max,
            f["title"],
        ),
    )


def apply_history(
    findings: list[dict[str, Any]],
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the latest event per finding, and drop dismissed ones.

    A dismissal holds only while the finding is CONTINUOUSLY reported. If it
    disappears and returns, the dismissal does not carry over — the situation
    changed, and a decision made about the old one should not silently apply to
    the new. That is what finding_key is for.
    """
    latest: dict[str, dict] = {}
    for e in events:
        k = e.get("finding_key")
        if not k:
            continue
        cur = latest.get(k)
        if cur is None or (e.get("created_at") or "") > (cur.get("created_at") or ""):
            latest[k] = dict(e)

    out = []
    for f in findings:
        e = latest.get(f["finding_key"])
        if e and e.get("event") == "dismissed":
            continue
        if e:
            f = {**f, "last_event": e.get("event"), "actor": e.get("actor"),
                 "note": e.get("note")}
        out.append(f)
    return out


def closures(
    findings: list[dict[str, Any]],
    events: Iterable[Mapping[str, Any]],
) -> list[str]:
    """finding_keys that were open and are no longer reported.

    The caller writes a 'closed' event for each. This is what makes the
    history true without anything having to reconcile state: the producer
    stopping is the closure, and recording it is the only durable trace that
    the work happened at all.
    """
    open_now = {f["finding_key"] for f in findings}
    state: dict[str, str] = {}
    for e in sorted(events, key=lambda x: x.get("created_at") or ""):
        if e.get("finding_key"):
            state[e["finding_key"]] = e.get("event") or ""
    return [k for k, ev in state.items()
            if ev in ("opened", "assigned", "noted") and k not in open_now]


def openings(
    findings: list[dict[str, Any]],
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Findings reported now with no open event recorded. Caller writes them.

    Without this the history starts at whenever someone happened to look, and
    "found on one date, closed on another" loses its first date.
    """
    state: dict[str, str] = {}
    for e in sorted(events, key=lambda x: x.get("created_at") or ""):
        if e.get("finding_key"):
            state[e["finding_key"]] = e.get("event") or ""
    return [f for f in findings
            if state.get(f["finding_key"]) in (None, "", "closed")]
