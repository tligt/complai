"""
heartbeat.py — S67 (D-188). Checks that become true by time passing.

NO STREAMLIT. NO SUPABASE. NO I/O. Like tasks.py (D-61): rows in, findings out.

Everything else RECOSA checks is checked when somebody opens a page. These are
the things nobody triggers: a legal hold that outlives its matter, a superseded
version reaching its deletion date, a policy nobody has re-read in a year, a
tool added and never tied to any processing. monitor_heartbeat.py runs them
every night for every company; obligation_view runs the same function when the
action plan is opened, so the two can never disagree about what is open.

NOTHING HERE ACTS. A finding asks; it never releases a hold, deletes, or adopts
(scope lock in 3b). The hold finding is a question on purpose: RECOSA cannot
know whether the proceeding is over, and telling someone to release a hold on
evidence in a live matter would be worse than saying nothing.

Not here, because a producer already reports them: drafts never adopted
(tasks.documents_outstanding), training due (training_store), consistency
findings (S65), unreviewed translations. Keys are `heartbeat:<rule>:<id>` —
stable, no names, no dates (see FINDING KEYS in tasks.py).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping

from i18n import tr
from tasks import DUE, OPEN, _finding

PRODUCER = "heartbeat"

HOLD_DAYS = 30             # a hold older than this is asked about
RETENTION_WARN_DAYS = 30   # a superseded version this close to deletion is flagged
REVIEW_DAYS = 365          # an in-force version older than this asks for a re-read
SYSTEM_GRACE_DAYS = 14     # a new system gets this long before it must be tied to an activity


def _day(v: Any) -> date | None:
    """A date from a date, a datetime or an ISO string; None if it is none of them."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v[:10]).date()
        except ValueError:
            return None
    return None


def _label(r: Mapping[str, Any], doc_labels: Mapping[str, str]) -> str:
    kind = doc_labels.get(r.get("document_type"), r.get("document_type") or "—")
    v = f" v{r['version']}" if r.get("version") else ""
    return f"{kind}{v} ({(r.get('language') or '').upper()})"


def stale_holds(docs: Iterable[Mapping[str, Any]], doc_labels: Mapping[str, str],
                today: date) -> list[dict[str, Any]]:
    """Legal holds set more than HOLD_DAYS ago, or of unknown age.

    A hold with no hold_set_on was set before S27's column existed; its age
    cannot be known, which is the reason to ask, not a reason to stay silent.
    """
    out = []
    for r in docs:
        if not r.get("legal_hold"):
            continue
        since = _day(r.get("hold_set_on"))
        if since is not None and (today - since).days < HOLD_DAYS:
            continue
        out.append(_finding(
            PRODUCER, f"hold:{r['id']}",
            tr("{doc} is on legal hold — is it still necessary?").format(doc=_label(r, doc_labels)),
            OPEN,
            (tr("The hold was set on {date}.").format(date=since.isoformat()) if since
             else tr("When the hold was set is not recorded."))
            + " " + tr("A hold keeps data past its retention period. Release it once "
                       "the matter it was set for is over; keep it while it is live."),
            link="compliance_record",
        ))
    return out


def retention_ending(docs: Iterable[Mapping[str, Any]], doc_labels: Mapping[str, str],
                     today: date) -> list[dict[str, Any]]:
    """Superseded versions whose retain_until falls within RETENTION_WARN_DAYS.

    Not on hold (a held version is not deleted), and not already past: the
    deletion date passing is the end of the finding, not an escalation.
    """
    out = []
    for r in docs:
        if r.get("legal_hold") or r.get("status") == "in_force":
            continue
        keep = _day(r.get("retain_until"))
        if keep is None or not (0 <= (keep - today).days <= RETENTION_WARN_DAYS):
            continue
        out.append(_finding(
            PRODUCER, f"retention:{r['id']}",
            tr("{doc} reaches the end of its retention period").format(doc=_label(r, doc_labels)),
            DUE,
            tr("Download a copy if you need one, or place it on hold if it is "
               "relevant to a live matter."),
            keep, link="compliance_record",
        ))
    return out


def not_reviewed(docs: Iterable[Mapping[str, Any]], doc_labels: Mapping[str, str],
                 today: date) -> list[dict[str, Any]]:
    """In-force versions adopted more than REVIEW_DAYS ago.

    "Reviewed" means re-adopted: there is no separate review date, and a
    re-read that changes nothing is recorded by putting the same text in force
    again. Not a breach — a document nobody has revisited in a year has
    usually drifted from the business it describes.
    """
    out = []
    for r in docs:
        if r.get("status") != "in_force":
            continue
        since = _day(r.get("adopted_at")) or _day(r.get("effective_from"))
        if since is None or (today - since).days <= REVIEW_DAYS:
            continue
        out.append(_finding(
            PRODUCER, f"review:{r['id']}",
            tr("{doc} has not been reviewed for over a year").format(doc=_label(r, doc_labels)),
            OPEN,
            tr("Re-read it against how you work today. If nothing changed, put it in "
               "force again; if something did, generate a new version."),
            link="documents",
        ))
    return out


def unused_systems(systems: Iterable[Mapping[str, Any]], links: Iterable[Mapping[str, Any]],
                   today: date) -> list[dict[str, Any]]:
    """Systems added more than SYSTEM_GRACE_DAYS ago and tied to no activity.

    readiness() reports the other direction (an activity with no system). A
    tool nobody has tied to a purpose is either processing that the register
    does not describe, or a tool that is no longer used.
    """
    linked = {l.get("system_id") for l in links}
    out = []
    for s in systems:
        if s["id"] in linked:
            continue
        added = _day(s.get("created_at"))
        if added is None or (today - added).days < SYSTEM_GRACE_DAYS:
            continue
        out.append(_finding(
            PRODUCER, f"system:{s['id']}",
            tr("{system} is not used by any processing activity").format(
                system=s.get("name") or "—"),
            OPEN,
            tr("Add it to the activities it serves, or remove it if you no longer use it."),
            link="inventory",
        ))
    return out


def findings(
    *,
    docs: Iterable[Mapping[str, Any]] = (),
    systems: Iterable[Mapping[str, Any]] = (),
    links: Iterable[Mapping[str, Any]] = (),
    doc_labels: Mapping[str, str] | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Every heartbeat finding for one company.

    docs: ALL client_documents rows of the company (drafts, in force and
    superseded) — the hold and retention rules are about superseded versions,
    which the register status view leaves out.
    """
    today = today or date.today()
    docs = list(docs)
    labels = doc_labels or {}
    return (stale_holds(docs, labels, today)
            + retention_ending(docs, labels, today)
            + not_reviewed(docs, labels, today)
            + unused_systems(list(systems), list(links), today))


def scoped(events: Iterable[Mapping[str, Any]], producers: Iterable[str] = (PRODUCER,)) -> list:
    """Only the task events of these producers.

    obligation_store.reconcile closes every open key missing from the findings
    it is given. A job that computes ONE producer and passes the whole history
    would close every other task on the action plan. This is the guard.
    """
    keep = set(producers)
    return [e for e in events if e.get("producer") in keep]
