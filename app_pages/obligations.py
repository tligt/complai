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

from display import fmt_date

import obligation_register as OR
import obligation_store as STORE
from auth import get_user_id
from database import get_supabase
from active_client import get_active_client
from obligations import (
    REGULATION_LABELS, DOCUMENT_TYPES,
)

st.title("Obligations")
from guide import page_tip
page_tip("obligations")
st.caption(
    "Everything the regulations you are subject to require of you, and what "
    "you have recorded against each."
)

user_id = get_user_id()
if not user_id:
    st.error("Please log in.")
    st.stop()

client = get_active_client(user_id)

client_id = client["id"]
regulations = client.get("regulations") or ["GDPR"]
doc_languages = [l.lower() for l in (client.get("document_languages") or ["en"])]

# ── Load ──────────────────────────────────────────────────────────────────
# Audit batch 2: computed in obligation_view, shared with Action plan and Home.
import obligation_view as OV
_state = OV.load_state(user_id, client)
activities, systems, links = _state["activities"], _state["systems"], _state["links"]
readiness, responses, register = _state["readiness"], _state["responses"], _state["register"]
doc_status, applicable, verdicts = _state["doc_status"], _state["applicable"], _state["verdicts"]
open_tasks = _state["open_tasks"]

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
    @st.fragment
    def _nis2_scope_panel(client_id: str, initial_client: dict):
        """Isolated so Save reruns only this panel, not the whole page
        (inventory reload, obligation evaluation, task derivation).

        Re-reads the three NIS2 fields fresh on every fragment rerun rather
        than trusting the page-level `client` snapshot from above: a
        fragment-scoped rerun does not re-execute the code that fetched
        `client` at the top of the script, so that snapshot would otherwise
        go stale the moment Save is clicked.
        """
        try:
            _row = (get_supabase().table("clients")
                    .select("nis2_entity_class, nis2_sector, nis2_scope_note")
                    .eq("id", client_id).single().execute().data) or {}
        except Exception:
            _row = initial_client

        _cls = _row.get("nis2_entity_class")
        with st.expander(
            "NIS2 — are you in scope, and as what?"
            + ("" if _cls else "  ·  :orange[not answered]"),
            expanded=not _cls,
        ):
            st.markdown(
                "NIS2 applies to medium and large companies (50+ staff or "
                "€10 million turnover) in the sectors it lists, and to some "
                "smaller ones regardless of size, such as DNS and trust-service "
                "providers. If it applies, you are one of two kinds:\n\n"
                "- **Essential** — large companies (250+ staff, or €50 million "
                "turnover) in the most critical sectors (energy, transport, "
                "banking, health, digital infrastructure…), and a few named "
                "regardless of size. Checked by the authority without waiting "
                "for a problem.\n"
                "- **Important** — medium-sized companies in those sectors, and "
                "companies in the other listed sectors (postal, waste, food, "
                "manufacturing, digital providers…). Checked after an incident or "
                "a complaint.\n\n"
                "Both owe the same things: security measures and incident reporting."
            )
            st.caption("Legal reference: NIS2 Art. 2–3, Annexes I and II. Your country's "
                       "law can add entities. Not sure? Ask the Assistant, or Support.")
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
                    "Sector", value=_row.get("nis2_sector") or "",
                    placeholder="e.g. digital infrastructure, manufacturing",
                )
                note = st.text_area(
                    "Why", value=_row.get("nis2_scope_note") or "", height=80,
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
                        st.rerun(scope="fragment")
                    except Exception as e:
                        st.error(f"Could not save: {e}")

            if _cls == "out_of_scope" and not (_row.get("nis2_scope_note") or "").strip():
                st.warning(
                    "Recorded as out of scope with no reason given. That is the "
                    "first thing an authority asks about."
                )

    _nis2_scope_panel(client_id, client)

st.divider()

# ── Tasks ─────────────────────────────────────────────────────────────────
# Audit batch 2 (H3): the task list has its own page, Action plan. Here only
# the count and the way there, so the register is not pushed below the fold.
if open_tasks:
    _ac1, _ac2 = st.columns([3, 1])
    _ac1.info(f"**{len(open_tasks)} {'task' if len(open_tasks) == 1 else 'tasks'} outstanding** "
              "— listed by urgency on the Action plan.")
    if _ac2.button("Open the action plan", key="ob_to_plan", use_container_width=True):
        st.switch_page("app_pages/action_plan.py")
else:
    st.success("Nothing outstanding.")
st.divider()

# ── The register ──────────────────────────────────────────────────────────
# Same table-plus-detail-panel shape as the To-do list above: a compact
# summary per regulation (icon, title, article, status), and the full
# description/form for whichever one obligation is selected. Safe to do
# without touching how verdicts are computed — they are still built once,
# above, from the full applicable set; this only changes how an already-
# computed verdict is DISPLAYED, so there is no risk of a stale or wrong
# status badge the way there would be if a save were scoped to a fragment.
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

# The Show/Search filters change which obligations are selectable per
# regulation. If a filter changes on this rerun, the previously selected
# obligation in any group may no longer be in that group's options — cleared
# here, before any selectbox below renders, rather than left to raise on a
# stale value Streamlit no longer recognises.
_filter_sig = (tuple(sorted(only)), search)
if st.session_state.get("_ob_filter_sig") != _filter_sig:
    st.session_state["_ob_filter_sig"] = _filter_sig
    st.session_state.pop("ob_select", None)

# Usability audit batch 2→3 (M8): one list across all regulations, what
# needs attention first, the plain title before the legal reference. It used
# to be one table and one selector per regulation, read one at a time.
_ORDER = {OR.MISSING: 0, OR.UNKNOWN: 1, OR.PARTIAL: 2, OR.COMPLIANT: 3, OR.NOT_APPLICABLE: 4}
shown = sorted(
    (o for o in applicable
     if (not only or verdicts[o["id"]]["status"] in only)
     and (not search or search.lower() in
          f"{o['title']} {o.get('article','')} {o.get('description','')}".lower())),
    key=lambda o: (_ORDER.get(verdicts[o["id"]]["status"], 9),
                   regulations.index(o["regulation"]) if o["regulation"] in regulations else 9),
)
if not shown:
    st.info("Nothing matches these filters.")
else:
    st.dataframe(
        [
            {
                "Status": f"{_STATUS_ICON[verdicts[o['id']]['status']]} {_STATUS_LABEL[verdicts[o['id']]['status']]}",
                "Obligation": o["title"],
                "Regulation": REGULATION_LABELS.get(o["regulation"], o["regulation"]),
                "Legal reference": o.get("article", ""),
            }
            for o in shown
        ],
        hide_index=True, width="stretch",
        column_config={
            "Status": st.column_config.TextColumn(width=150),
            "Obligation": st.column_config.TextColumn(width=520),
            "Regulation": st.column_config.TextColumn(width=110),
            "Legal reference": st.column_config.TextColumn(width=110),
        },
    )

if shown:
    _shown_by_id = {o["id"]: o for o in shown}
    if st.session_state.get("ob_select") not in _shown_by_id:
        st.session_state.pop("ob_select", None)
    _sel_id = st.selectbox(
        "Open an obligation",
        options=list(_shown_by_id.keys()),
        format_func=lambda i: (f"{_STATUS_ICON[verdicts[i]['status']]} {_shown_by_id[i]['title']}"
                               f" · {REGULATION_LABELS.get(_shown_by_id[i]['regulation'], '')}"),
        key="ob_select",
    )
    ob = _shown_by_id[_sel_id]
    v = verdicts[ob["id"]]
    resp = responses.get(ob["id"]) or {}
    kind = OR.response_kind(ob)

    with st.container(border=True):
        st.markdown(f"**{_STATUS_ICON[v['status']]}  {ob['title']}**")
        st.markdown(ob.get("description") or "")
        if ob.get("article"):
            st.caption(f"Legal reference: {REGULATION_LABELS.get(ob['regulation'], ob['regulation'])} "
                       f"{ob['article']}")
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
                            f"Confirmed {fmt_date(str(resp['acknowledged_at']))}"
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
                            # The saved status can move the obligation out of
                            # an active Show filter (e.g. marking a
                            # previously-Missing item Compliant while
                            # filtered to Missing) — same stale-option risk
                            # as a changed filter, cleared the same way.
                            st.session_state.pop("ob_select", None)
                            st.rerun()
                        else:
                            st.error("Could not save.")

st.divider()
st.caption(
    "Statuses RECOSA works out for itself update as your inventory changes. "
    "Everything else is what you have recorded, and is shown as such."
)
