"""
pages/obligations.py — S29. Every obligation, and what is outstanding.

38 of 54 obligations had no home in the product. A client saw a checkbox on a
dashboard and had nowhere to record what they actually do about it — no
evidence, no date, no reviewer, no history. So they kept a spreadsheet, and
that spreadsheet is where the parts of their compliance RECOSA could not hold
ended up living.

RENDERING ONLY (D-61). Every verdict comes from obligation_register, every
finding from tasks, and all I/O from obligation_store. This file decides what
to show, never what is true.

54 IS A LOT
-----------
The design problem is navigability, not completeness. A flat list of 54 rows is
a spreadsheet with worse ergonomics, which is the thing being replaced.

So: outstanding work first and separately, then obligations grouped by
regulation, collapsed, filtered, with the ones needing attention open. A client
should be able to answer "what do I need to do" without reading anything they
have already dealt with.
"""

from datetime import date

import streamlit as st

import obligation_register as OR
import obligation_store as STORE
import tasks as T
from auth import get_user_id
from database import get_supabase, get_register_status
from obligations import (
    OBLIGATIONS, OBLIGATION_BY_ID, REGULATION_LABELS, DOCUMENT_TYPES,
)

st.title("Obligations")
st.caption(
    "Everything the regulations you are subject to require of you, and what "
    "you have recorded against each."
)

user_id = get_user_id()
if not user_id:
    st.error("Please log in.")
    st.stop()

try:
    client = (get_supabase().table("clients").select("*")
              .eq("user_id", user_id).single().execute().data) or {}
except Exception:
    client = {}

if not client:
    st.warning("Please complete your company profile first.")
    st.stop()

client_id = client["id"]
regulations = client.get("regulations") or ["GDPR"]
doc_languages = [l.lower() for l in (client.get("document_languages") or ["en"])]

# ── Load ──────────────────────────────────────────────────────────────────
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
    st.warning(f"Could not read the inventory: {e}")
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

verdicts = OR.evaluate(
    applicable,
    {"client": client, "activities": activities, "systems": systems,
     "links": links},
    document_status=doc_status,
    responses=responses,
)

# ── Outstanding work ──────────────────────────────────────────────────────
# Derived on every read; nothing stores that a task is open. See tasks.py.
_reg_rows = [r for per_lang in register.values() for r in per_lang.values()]
findings = T.collect(
    T.obligations_due(verdicts, responses, OBLIGATION_BY_ID),
    T.translations_outstanding(activities, doc_languages),
    T.documents_outstanding(_reg_rows, DOCUMENT_TYPES),
    T.inventory_gaps(readiness),
)
events = STORE.load_events(client_id, user_id)
STORE.reconcile(user_id, client_id, findings, events)
open_tasks = T.apply_history(findings, events)

counts = OR.counts(verdicts)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Recorded as in place", counts["compliant"])
c2.metric("Partly addressed", counts["partial"])
c3.metric("Not addressed", counts["missing"] + counts["unknown"])
c4.metric("Outstanding tasks", len(open_tasks))

# No percentage, deliberately. The dashboard publishes a coverage figure
# computed a different way; two numbers claiming to measure the same thing and
# disagreeing, in one product, is worse than one honest low number. They are
# reconciled in a single later sprint with the explanation shipped alongside.

# ── NIS2 scope ────────────────────────────────────────────────────────────
# Here rather than in the inventory: "am I in scope, and as what" is an
# obligation response, not a systems fact. It also keeps pages/inventory.py
# from growing again — that page has produced five defects in two days,
# largely because it keeps acquiring responsibilities.
#
# Shown only where NIS2 applies to the client at all.
if "NIS2" in regulations:
    _cls = client.get("nis2_entity_class")
    with st.expander(
        "NIS2 — are you in scope, and as what?"
        + ("" if _cls else "  ·  :orange[not answered]"),
        expanded=not _cls,
    ):
        st.caption(
            "Annex I sectors are **essential** entities, Annex II **important** "
            "ones. The difference is how you are supervised, not what you owe: "
            "both are subject to Art. 21 measures and Art. 23 reporting. "
            "Essential entities are supervised proactively; important ones "
            "after the fact."
        )
        with st.form("nis2_scope"):
            _opts = [None, "essential", "important", "out_of_scope"]
            new_cls = st.selectbox(
                "Classification",
                options=_opts,
                index=_opts.index(_cls) if _cls in _opts else 0,
                format_func=lambda c: {
                    None: "Not yet determined",
                    "essential": "Essential entity (Annex I)",
                    "important": "Important entity (Annex II)",
                    "out_of_scope": "Not in scope",
                }[c],
            )
            sector = st.text_input(
                "Sector", value=client.get("nis2_sector") or "",
                placeholder="e.g. digital infrastructure, manufacturing",
            )
            note = st.text_area(
                "Why", value=client.get("nis2_scope_note") or "", height=80,
                help=(
                    "An entity that concluded it is out of scope will be asked "
                    "to justify that, and will not remember. Size thresholds, "
                    "sector, and any exception you relied on."
                ),
            )
            if st.form_submit_button("Save", type="primary"):
                try:
                    get_supabase().table("clients").update({
                        "nis2_entity_class": new_cls,
                        # Kept coherent in code as well as by the CHECK: the
                        # documents read one of these and the register the
                        # other, and they must not disagree.
                        "nis2_in_scope": (
                            None if new_cls is None
                            else new_cls in ("essential", "important")
                        ),
                        "nis2_sector": sector or None,
                        "nis2_scope_note": note or None,
                    }).eq("id", client_id).execute()
                    st.success("Saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not save: {e}")

        if _cls == "out_of_scope" and not (client.get("nis2_scope_note") or "").strip():
            st.warning(
                "Recorded as out of scope with no reason given. That is the "
                "first thing an authority asks about."
            )

st.divider()

# ── Tasks ─────────────────────────────────────────────────────────────────
if open_tasks:
    st.subheader(f"To do ({len(open_tasks)})")
    _icon = {T.BLOCKING: "🔴", T.DUE: "🟠", T.OPEN: "⚪"}
    for f in open_tasks:
        col_a, col_b = st.columns([6, 1])
        col_a.markdown(f"{_icon.get(f['severity'], '⚪')} **{f['title']}**")
        if f.get("detail"):
            col_a.caption(f["detail"])
        if f.get("due"):
            col_a.caption(f"Due {f['due']}")

        if col_b.button("Dismiss", key=f"dis_{f['finding_key']}",
                        use_container_width=True):
            st.session_state[f"dis_open_{f['finding_key']}"] = True
            st.rerun()

        if st.session_state.get(f"dis_open_{f['finding_key']}"):
            with st.container(border=True):
                # A reason is required — the CHECK constraint enforces it, and
                # this is what an auditor asks about.
                why = st.text_input(
                    "Why is this not something you need to do?",
                    key=f"dis_why_{f['finding_key']}",
                    placeholder="e.g. accepted risk, reviewed and not applicable",
                )
                d1, d2 = st.columns(2)
                if d1.button("Dismiss it", key=f"dis_go_{f['finding_key']}",
                             type="primary", disabled=not (why or "").strip()):
                    STORE.dismiss(user_id, client_id, f["producer"],
                                  f["finding_key"], why)
                    st.session_state.pop(f"dis_open_{f['finding_key']}", None)
                    st.rerun()
                if d2.button("Keep it", key=f"dis_no_{f['finding_key']}"):
                    st.session_state.pop(f"dis_open_{f['finding_key']}", None)
                    st.rerun()
                st.caption(
                    "It comes back if the situation changes — a dismissal "
                    "applies to this finding, not to any future one that looks "
                    "like it."
                )
    st.divider()
else:
    st.success("Nothing outstanding.")
    st.divider()

# ── The register ──────────────────────────────────────────────────────────
_STATUS_ICON = {
    OR.COMPLIANT: "🟢", OR.PARTIAL: "🟡", OR.MISSING: "🔴",
    OR.NOT_APPLICABLE: "⚪", OR.UNKNOWN: "⚫",
}
_STATUS_LABEL = {
    OR.COMPLIANT: "In place", OR.PARTIAL: "Partly", OR.MISSING: "Not in place",
    OR.NOT_APPLICABLE: "Not applicable", OR.UNKNOWN: "Nothing recorded",
}
_SOURCE_NOTE = {
    OR.SOURCE_DERIVED: "Worked out from your systems and activities",
    OR.SOURCE_DOCUMENT: "A document in force covers this",
    OR.SOURCE_ANALYSED: "From your last gap assessment",
    OR.SOURCE_DECLARED: "You recorded this",
    OR.SOURCE_NONE: "",
}

f1, f2 = st.columns([2, 3])
only = f1.multiselect(
    "Show", [OR.MISSING, OR.UNKNOWN, OR.PARTIAL, OR.COMPLIANT, OR.NOT_APPLICABLE],
    default=[], format_func=lambda s: _STATUS_LABEL[s],
    placeholder="Everything",
)
search = f2.text_input("Search", placeholder="Article, keyword…")

for reg in regulations:
    rows = [o for o in applicable if o["regulation"] == reg]
    if not rows:
        continue
    shown = [
        o for o in rows
        if (not only or verdicts[o["id"]]["status"] in only)
        and (not search or search.lower() in
             f"{o['title']} {o.get('article','')} {o.get('description','')}".lower())
    ]
    if not shown:
        continue

    st.subheader(f"{REGULATION_LABELS.get(reg, reg)} ({len(shown)})")

    for ob in shown:
        v = verdicts[ob["id"]]
        resp = responses.get(ob["id"]) or {}
        kind = OR.response_kind(ob)

        with st.expander(
            f"{_STATUS_ICON[v['status']]}  {ob['title']}  ·  {ob.get('article','')}",
            # Open where the client has something to do. Anything already
            # settled stays shut — a page of 54 open panels is unreadable.
            expanded=v["status"] in (OR.MISSING, OR.UNKNOWN) and bool(only),
        ):
            st.caption(ob.get("description") or "")
            note = _SOURCE_NOTE.get(v["source"], "")
            st.markdown(
                f"**{_STATUS_LABEL[v['status']]}**"
                + (f" — {note}" if note else "")
            )
            if v.get("detail"):
                st.caption(v["detail"])
            for ev in (v.get("evidence") or [])[:8]:
                st.caption(f"· {ev}")

            st.divider()

            if kind == OR.KIND_DERIVED:
                st.caption(
                    "RECOSA works this out from your systems and activities. "
                    "Change it there and this follows — there is nothing to "
                    "fill in here."
                )
            elif kind == OR.KIND_DOCUMENT:
                dt = ob.get("doc_type")
                st.caption(
                    f"Satisfied by a **{DOCUMENT_TYPES.get(dt, dt)}**. "
                    "Generate or upload it under Documents; its status here "
                    "follows the register."
                )
            elif kind == OR.KIND_TRACKED:
                st.caption("Tracked elsewhere in RECOSA.")
            else:
                with st.form(f"ob_{ob['id']}"):
                    if kind == OR.KIND_ACKNOWLEDGE:
                        who = st.text_input(
                            "Who confirmed this, and in what capacity",
                            value=resp.get("acknowledged_by") or "",
                            help=(
                                "A name and a date. An unattributed tick is "
                                "not evidence of anything."
                            ),
                        )
                        if resp.get("acknowledged_at"):
                            st.caption(
                                f"Confirmed {str(resp['acknowledged_at'])[:10]}"
                            )
                    else:
                        who = None

                    statement = st.text_area(
                        "What you do about this",
                        value=(resp.get("statement_i18n") or {}).get("en", ""),
                        height=90,
                        help=(
                            "In your own words. This is what you would show "
                            "someone who asked."
                        ),
                    )

                    s1, s2 = st.columns(2)
                    new_status = s1.selectbox(
                        "Status",
                        options=["not_started", "in_progress", "compliant",
                                 "partial", "not_applicable"],
                        index=["not_started", "in_progress", "compliant",
                               "partial", "not_applicable"].index(
                            resp.get("status") or "not_started"),
                        format_func=lambda s: {
                            "not_started": "Not started",
                            "in_progress": "In progress",
                            "compliant": "In place",
                            "partial": "Partly",
                            "not_applicable": "Not applicable",
                        }[s],
                    )
                    review = s2.date_input(
                        "Review again on",
                        value=(date.fromisoformat(resp["review_due"])
                               if resp.get("review_due") else None),
                        help="Leave blank if it does not need revisiting.",
                    )

                    reason = st.text_input(
                        "If not applicable, why not",
                        value=resp.get("not_applicable_reason") or "",
                        help=(
                            "Required, and the first thing an auditor asks "
                            "about. It is also what you will not remember."
                        ),
                    )

                    if st.form_submit_button("Save", type="primary"):
                        if new_status == "not_applicable" and not reason.strip():
                            st.error(
                                "A reason is required to mark something not "
                                "applicable."
                            )
                        else:
                            ok = STORE.save_response(
                                user_id, client_id, ob["id"],
                                status=new_status,
                                statement_en=statement,
                                acknowledged_by=who,
                                review_due=review or None,
                                not_applicable_reason=reason,
                            )
                            if ok:
                                st.success("Saved.")
                                st.rerun()
                            else:
                                st.error("Could not save.")

st.divider()
st.caption(
    "Statuses RECOSA works out for itself update as your inventory changes. "
    "Everything else is what you have recorded, and is shown as such."
)
