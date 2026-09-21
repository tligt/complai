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
from template_nis2 import INSERTS
from auth import get_user_id
from database import get_supabase
from active_client import get_active_client
from cached_reads import get_register_status, get_in_force_template_versions
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

client = get_active_client(user_id)

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
    # S36. Compares against the shared template catalogue, not per-client data.
    T.template_updates_available(
        _reg_rows, get_in_force_template_versions(), DOCUMENT_TYPES,
    ),
    T.inventory_gaps(readiness),
    # S30. Insert sections that are missing, unconfirmed, or two words long.
    # Surfaced here rather than only on the wording page: a warning on a form
    # is seen once, by someone who has decided to type "By looking" and move
    # on.
    T.wording_missing(client, INSERTS, doc_languages),
    T.wording_too_short(client, INSERTS, doc_languages),
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
# Summary table with two real per-row actions — Go fix it and Dismiss — via
# st.column_config.ButtonColumn, which renders actual clickable buttons
# inside a cell and fires a Python callback with the clicked row's index.
# Every finding already carries `link`, the page that actually fixes the
# underlying thing; "obligations" is this page, so those rows get no
# fix-it button — everything else does.
#
# A single narrow icon column measured right in testing and then rendered
# far too wide in a real browser window: st.dataframe distributes any
# leftover row width EVENLY across every column once the sum of configured
# widths is less than the table's own width, including a column pinned at
# 36px — confirmed in the installed column_config source, not assumed. The
# icon is folded into the Task text instead, so there is no narrow column
# for that redistribution to inflate. Due is narrowed the same way, though
# a normal text column being stretched somewhat is far less visually broken
# than a one-character column was.
_TASK_LINK_PAGES = {
    "inventory":          "pages/inventory.py",
    "documents":          "pages/documents.py",
    "wording":            "pages/wording.py",
    "compliance_record":  "pages/compliance_record.py",
}
_FIX_LABEL = "Fix it"
_DISMISS_LABEL = "Dismiss"


def _task_actions(f: dict) -> list[str]:
    acts = []
    if _TASK_LINK_PAGES.get(f.get("link") or ""):
        acts.append(_FIX_LABEL)
    acts.append(_DISMISS_LABEL)
    return acts


def _handle_task_action():
    """ButtonColumn callback. Runs before the rerun it triggers, so it only
    sets state for the main script body to act on — switch_page itself
    stays out of the callback, since callbacks execute in their own partial
    run and are not the documented place to call it.
    """
    click = st.session_state.get("ob_task_action_click")
    if not click:
        return
    idx = click.get("row")
    if idx is None or idx >= len(open_tasks):
        return
    f = open_tasks[idx]
    label = click.get("label") or ""
    if _DISMISS_LABEL in label:
        st.session_state["ob_task_dismiss_select"] = f["finding_key"]
    elif _FIX_LABEL in label:
        page = _TASK_LINK_PAGES.get(f.get("link") or "")
        if page:
            st.session_state["_ob_pending_navigate"] = page


if open_tasks:
    st.subheader(f"To do ({len(open_tasks)})")
    _icon = {T.BLOCKING: "🔴", T.DUE: "🟠", T.OPEN: "⚪"}

    st.dataframe(
        [
            {
                "Task": f"{_icon.get(f['severity'], '⚪')} {f['title']}",
                "Detail": f.get("detail") or "",
                "Due": f.get("due") or "",
                "Actions": _task_actions(f),
            }
            for f in open_tasks
        ],
        hide_index=True,
        # stretch (matches every other table on this page) fills the parent
        # container and spreads whatever is left over EVENLY across every
        # column. Task and Detail are given a bigger starting width than Due
        # and Actions specifically so that, after that even split, they are
        # still the two columns actually getting the space.
        width="stretch",
        column_config={
            "Task": st.column_config.TextColumn(width=430),
            "Detail": st.column_config.TextColumn(width=620),
            "Due": st.column_config.TextColumn(width=90),
            # A single Dismiss renders directly at this width; two actions
            # collapse into a "..." menu rather than both showing inline —
            # kept deliberately, not a compromise: familiar pattern, and it
            # means Actions does not need to fight Task/Detail for width.
            "Actions": st.column_config.ButtonColumn(
                width=100,
                on_click=_handle_task_action,
                key="ob_task_action_click",
            ),
        },
    )

    # Set by the Go fix it button's callback, above. Done here rather than
    # inside the callback itself — st.switch_page's own docs describe it as
    # stopping the CURRENT page's execution, which is the main script body,
    # not the separate partial run a column-button callback executes in.
    _pending_nav = st.session_state.pop("_ob_pending_navigate", None)
    if _pending_nav:
        st.switch_page(_pending_nav)

    # Still a real selector, not just a Dismiss-button landing spot — either
    # path sets the same key, so clicking Dismiss in the table and picking a
    # task here do the same thing.
    _tasks_by_key = {f["finding_key"]: f for f in open_tasks}
    _select_options = [None] + list(_tasks_by_key.keys())
    _selected_key = st.selectbox(
        "Dismiss a task",
        options=_select_options,
        format_func=lambda k: (
            "— Select a task to dismiss —" if k is None else _tasks_by_key[k]["title"]
        ),
        key="ob_task_dismiss_select",
    )

    if _selected_key:
        f = _tasks_by_key[_selected_key]
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
                # The dismissed task drops out of open_tasks on the next
                # load, so its key would no longer be a valid option —
                # cleared here rather than left to raise on rerun.
                st.session_state.pop("ob_task_dismiss_select", None)
                st.rerun()
            if d2.button("Cancel", key=f"dis_no_{f['finding_key']}"):
                st.session_state.pop("ob_task_dismiss_select", None)
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
    for _reg in regulations:
        st.session_state.pop(f"ob_reg_select_{_reg}", None)

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

    st.dataframe(
        [
            {
                # Icon folded into the text rather than its own column — a
                # narrow pinned-width column gets inflated by st.dataframe's
                # even redistribution of unused row width, the same issue
                # fixed in the To-do table above.
                "Obligation": (
                    f"{_STATUS_ICON[verdicts[o['id']]['status']]}  {o['title']}"
                ),
                "Article": o.get("article", ""),
                "Status": _STATUS_LABEL[verdicts[o["id"]]["status"]],
            }
            for o in shown
        ],
        hide_index=True,
        # stretch, same as the To-do table — Obligation given a large
        # starting width so it is still the column that ends up dominant
        # after stretch's even split of leftover space.
        width="stretch",
        column_config={
            "Obligation": st.column_config.TextColumn(width=560),
            "Article": st.column_config.TextColumn(width=90),
            "Status": st.column_config.TextColumn(width=110),
        },
    )

    _shown_by_id = {o["id"]: o for o in shown}
    _sel_id = st.selectbox(
        f"Select a {REGULATION_LABELS.get(reg, reg)} obligation",
        options=list(_shown_by_id.keys()),
        format_func=lambda i: _shown_by_id[i]["title"],
        key=f"ob_reg_select_{reg}",
        label_visibility="collapsed",
    )
    ob = _shown_by_id[_sel_id]
    v = verdicts[ob["id"]]
    resp = responses.get(ob["id"]) or {}
    kind = OR.response_kind(ob)

    with st.container(border=True):
        st.markdown(
            f"**{_STATUS_ICON[v['status']]}  {ob['title']}**"
            + (f"  ·  {ob['article']}" if ob.get("article") else "")
        )
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
                            # The saved status can move the obligation out of
                            # an active Show filter (e.g. marking a
                            # previously-Missing item Compliant while
                            # filtered to Missing) — same stale-option risk
                            # as a changed filter, cleared the same way.
                            st.session_state.pop(f"ob_reg_select_{reg}", None)
                            st.rerun()
                        else:
                            st.error("Could not save.")

st.divider()
st.caption(
    "Statuses RECOSA works out for itself update as your inventory changes. "
    "Everything else is what you have recorded, and is shown as such."
)
