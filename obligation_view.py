"""
obligation_view.py — the obligations register and the open tasks for one
client, computed once for the three pages that show them (usability audit
batch 2, H2/H3): Obligations (the register), Action plan (the tasks) and Home
(the next three).

Moved out of app_pages/obligations.py unchanged. Same rule as there: verdicts
come from obligation_register, findings from tasks, I/O from obligation_store;
this decides nothing, it only gathers.
"""
from i18n import tr  # S64 interface translation (D-164)

import streamlit as st

import incident_store as INC
import obligation_register as OR
import obligation_store as STORE
import tasks as T
from template_nis2 import INSERTS
from cached_reads import get_register_status, get_in_force_template_versions
from obligations import OBLIGATIONS, OBLIGATION_BY_ID, DOCUMENT_TYPES
from gap_assessment import load_latest_gap_results

# The page that fixes each kind of finding (tasks.py's `link`). "obligations"
# is missing on purpose: those are fixed on the register itself.
TASK_LINK_PAGES = {
    "obligations":        "app_pages/obligations.py",
    "inventory":          "app_pages/inventory.py",
    "documents":          "app_pages/documents.py",
    "wording":            "app_pages/wording.py",
    "compliance_record":  "app_pages/compliance_record.py",
    "incidents":          "app_pages/incidents.py",
    "training":           "app_pages/training.py",
    "ai_inventory":       "app_pages/ai_inventory.py",
}


def load_state(user_id: str, client: dict) -> dict:
    client_id = client["id"]
    regulations = client.get("regulations") or ["GDPR"]
    doc_languages = [l.lower() for l in (client.get("document_languages") or ["en"])]

    try:
        import inventory_store as INVS
        activities = INVS.load_activities(user_id, client_id)
        systems = INVS.load_systems(user_id, client_id)
        links = INVS.load_links(user_id, client_id)
        readiness = INVS.readiness(
            activities, systems, links,
            INVS.load_counterparty_links(user_id, client_id), client_id,
        )
    except Exception as e:
        st.warning(tr("Could not read the inventory: {e}").format(e=e))
        activities, systems, links, readiness = [], [], [], None

    responses = STORE.load_responses(client_id, user_id)
    register = get_register_status(client_id, user_id)

    # get_register_status is per language; the obligation only needs to know
    # whether a document is in force at all.
    doc_status = {
        dt: ("in_force" if any(r.get("status") == "in_force" for r in per_lang.values())
             else "draft")
        for dt, per_lang in register.items()
    }

    applicable = [o for o in OBLIGATIONS if o.get("regulation") in regulations]

    # S45. evaluate()'s gap_results parameter has existed since the register was
    # written but was never actually passed here — a gap assessment's findings
    # never reached the action plan until now. See gap_assessment.py's docstring.
    gap_results = load_latest_gap_results(user_id, client_id)

    # S60. The training register: the verdict for gdpr_13, nis2_09 and ai_01,
    # and the action-plan tasks. Read once for both.
    import training_store as TS
    try:
        training = TS.load_all(client_id)
    except Exception as e:
        print(f"Training register not loaded: {e}")
        training = None

    # S61. The AI inventory: verdicts for the AI Act obligations it records,
    # and its tasks.
    import ai_store as AIS
    try:
        ai_data = AIS.load_all(client_id)
    except Exception as e:
        print(f"AI inventory not loaded: {e}")
        ai_data = None

    verdicts = OR.evaluate(
        applicable,
        {"client": client, "activities": activities, "systems": systems,
         "links": links, "training": training, "ai": ai_data},
        document_status=doc_status,
        gap_results=gap_results,
        responses=responses,
    )

    # Derived on every read; nothing stores that a task is open. See tasks.py.
    _reg_rows = [r for per_lang in register.values() for r in per_lang.values()]
    findings = T.collect(
        T.obligations_due(verdicts, responses, OBLIGATION_BY_ID),
        T.translations_outstanding(activities, doc_languages),
        T.documents_outstanding(_reg_rows, DOCUMENT_TYPES),
        # S36. Compares against the shared template catalogue, not per-client data.
        T.template_updates_available(
            _reg_rows, get_in_force_template_versions(), DOCUMENT_TYPES,
        ),
        T.inventory_gaps(readiness),
        # S30. Insert sections that are missing, unconfirmed, or two words long.
        T.wording_missing(client, INSERTS, doc_languages),
        T.wording_too_short(client, INSERTS, doc_languages),
        # S53. Every open notification deadline of an incident not yet closed.
        INC.open_findings(user_id, client),
        # S60. Who needs training and does not have a current session.
        TS.open_findings(client, training) if training else [],
        # S61. AI systems with no use described, uses not assessed, prohibited
        # uses, high-risk uses with no overseer.
        AIS.open_findings(client, ai_data) if ai_data else [],
    )
    events = STORE.load_events(client_id, user_id)
    STORE.reconcile(user_id, client_id, findings, events)
    open_tasks = T.apply_history(findings, events)

    # S56: who handles each task; never-assigned tasks follow the company's
    # routing rule for their area. Never allowed to break the register.
    try:
        import work_items as W
        assignments = W.current(client_id, "task")
        if W.route_unassigned(client_id, open_tasks, assignments):
            assignments = W.current(client_id, "task")
    except Exception as e:
        print(f"Assignments not loaded: {e}")
        assignments = {}

    return {
        "client_id": client_id, "regulations": regulations,
        "doc_languages": doc_languages, "activities": activities,
        "systems": systems, "links": links, "readiness": readiness,
        "responses": responses, "register": register, "doc_status": doc_status,
        "applicable": applicable, "verdicts": verdicts, "open_tasks": open_tasks,
        "assignments": assignments,
        "counts": OR.counts(verdicts),
    }


# ── The headline figure (usability audit C6, D-123) ───────────────────────
# One answer to "how compliant am I?", the same on Home, Obligations and the
# Compliance record. Documents in force and the gap assessment's score are
# shown as details under it, named for what they measure.

HEADLINE_EXPLAINER = (
    "**% in place** counts every obligation that applies to you and is already "
    "in force; partly in place counts as half. It combines what RECOSA works out "
    "from your systems, the documents you adopted, your last gap assessment and "
    "what you recorded yourself — and rises as you complete the action plan."
)


def headline(state: dict) -> dict:
    """{regulation: OR.score(...)} for the client's regulations, in force only."""
    from obligations import split_by_force
    live, _ = split_by_force(state["applicable"])
    return {
        reg: OR.score(state["verdicts"], [o for o in live if o.get("regulation") == reg])
        for reg in state["regulations"]
    }


def band(pct) -> str:
    if pct is None:
        return "⚪"
    return "🟢" if pct >= 80 else "🟡" if pct >= 40 else "🔴"


def render_headline(state: dict, explain: bool = True) -> None:
    from display import regulation_label, plural
    scores = headline(state)
    cols = st.columns(max(len(scores), 1))
    for col, (reg, sc) in zip(cols, scores.items()):
        with col:
            st.markdown(f"**{regulation_label(reg)}**")
            if sc["percent"] is None:
                st.markdown("### ⚪ —")
                st.caption(tr("No obligation in force applies yet."))
                continue
            st.markdown(tr("### {band_sc_percent} {sc_percent}% in place").format(band_sc_percent=band(sc['percent']), sc_percent=sc['percent']))
            st.progress(sc["percent"] / 100)
            bits = [f"{sc['in_place']} of {sc['applicable']} obligations in place"]
            if sc["partly"]:
                bits.append(f"{sc['partly']} partly")
            if sc["declared"]:
                bits.append(f"{sc['declared']} self-declared")
            st.caption(" · ".join(bits))
    if explain:
        st.caption(HEADLINE_EXPLAINER)
