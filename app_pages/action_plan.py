"""
app_pages/action_plan.py — usability audit batch 2 (H3). The open tasks,
worst first and then by due date, on a page of their own. They used to sit on
Obligations below the metrics and the NIS2 scope form, where the most useful
list in the app was the easiest to miss.

The list itself is unchanged from Obligations (S29): derived on every read in
obligation_view, never stored as open; dismissing needs a reason.

S56: with a team, each task shows who handles it, "Only mine" filters to
yours, and Open shows a task with its person, its comments and Dismiss.
"""

import streamlit as st

import obligation_store as STORE
import obligation_view as OV
import tasks as T
import work_items as W
from work_items_view import render_panel
from active_client import get_active_client
from auth import get_user_id
from display import fmt_date, plural

st.title("Action plan")
from guide import page_tip
page_tip("action_plan")
st.caption(
    "What is outstanding, most urgent first. 🔴 blocks a document, 🟠 is "
    "past its date, ⚪ is open with no deadline. **Fix it** takes you to the "
    "page where it is done."
)

user_id = get_user_id()
client = get_active_client(user_id)
client_id = client["id"]
_state = OV.load_state(user_id, client)
open_tasks = _state["open_tasks"]
assignments = _state.get("assignments") or {}
team = W.has_team(client_id)

if open_tasks:
    _mine = [f for f in open_tasks
             if (assignments.get(f["finding_key"]) or {}).get("assignee_id") == user_id]
    h1, h2 = st.columns([3, 1])
    h1.markdown(f"**{plural(len(open_tasks), 'task')}** for {client['company_name']}"
                + (f" · **{len(_mine)}** handled by you" if team else ""))
    if team and h2.toggle("Only mine", key="ap_only_mine",
                          value=st.session_state.get("ap_only_mine", False)):
        open_tasks = _mine

# ── Tasks ─────────────────────────────────────────────────────────────────
# Summary table with two real per-row actions — Go fix it and Dismiss — via
# st.column_config.ButtonColumn, which renders actual clickable buttons
# inside a cell and fires a Python callback with the clicked row's index.
# Every finding already carries `link`, the page that actually fixes the
# underlying thing, so every row gets a fix-it button (on Obligations, where
# this list used to live, "obligations" rows had none: that was the page).
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
_TASK_LINK_PAGES = OV.TASK_LINK_PAGES
_FIX_LABEL = "Fix it"
_OPEN_LABEL = "Open"


def _task_actions(f: dict) -> list[str]:
    acts = []
    if _TASK_LINK_PAGES.get(f.get("link") or ""):
        acts.append(_FIX_LABEL)
    acts.append(_OPEN_LABEL)
    return acts


def _handle_task_action():
    """ButtonColumn callback. Runs before the rerun it triggers, so it only
    sets state for the main script body to act on — switch_page itself
    stays out of the callback, since callbacks execute in their own partial
    run and are not the documented place to call it.
    """
    click = st.session_state.get("ap_task_action_click")
    if not click:
        return
    idx = click.get("row")
    if idx is None or idx >= len(open_tasks):
        return
    f = open_tasks[idx]
    label = click.get("label") or ""
    if _OPEN_LABEL in label:
        st.session_state["ap_task_dismiss_select"] = f["finding_key"]
    elif _FIX_LABEL in label:
        page = _TASK_LINK_PAGES.get(f.get("link") or "")
        if page:
            st.session_state["_ap_pending_navigate"] = page


if open_tasks:
    _icon = {T.BLOCKING: "🔴", T.DUE: "🟠", T.OPEN: "⚪"}
    _talk = W.comment_counts(client_id, "task") if team else {}

    def _who(f):
        a = (assignments.get(f["finding_key"]) or {}).get("assignee_id")
        return ("You" if a == user_id else W.name_of(client_id, a)) if a else ""

    st.dataframe(
        [
            {
                "Task": f"{_icon.get(f['severity'], '⚪')} {f['title']}"
                        + (f"  💬 {_talk[f['finding_key']]}" if _talk.get(f["finding_key"]) else ""),
                "Detail": f.get("detail") or "",
                **({"Handled by": _who(f)} if team else {}),
                "Due": fmt_date(f["due"]) if f.get("due") else "",
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
            "Detail": st.column_config.TextColumn(width=520 if team else 620),
            "Handled by": st.column_config.TextColumn(width=140),
            "Due": st.column_config.TextColumn(width=90),
            # A single Dismiss renders directly at this width; two actions
            # collapse into a "..." menu rather than both showing inline —
            # kept deliberately, not a compromise: familiar pattern, and it
            # means Actions does not need to fight Task/Detail for width.
            "Actions": st.column_config.ButtonColumn(
                width=100,
                on_click=_handle_task_action,
                key="ap_task_action_click",
            ),
        },
    )

    # Set by the Go fix it button's callback, above. Done here rather than
    # inside the callback itself — st.switch_page's own docs describe it as
    # stopping the CURRENT page's execution, which is the main script body,
    # not the separate partial run a column-button callback executes in.
    _pending_nav = st.session_state.pop("_ap_pending_navigate", None)
    if _pending_nav:
        st.switch_page(_pending_nav)

    # Still a real selector, not just a Dismiss-button landing spot — either
    # path sets the same key, so clicking Dismiss in the table and picking a
    # task here do the same thing.
    _tasks_by_key = {f["finding_key"]: f for f in open_tasks}
    # S56: the inbox opens a task here (ap_open_task, set by app_pages/inbox.py).
    _from_inbox = st.session_state.pop("ap_open_task", None)
    if _from_inbox in _tasks_by_key:
        st.session_state["ap_task_dismiss_select"] = _from_inbox
    if st.session_state.get("ap_task_dismiss_select") not in _tasks_by_key:
        st.session_state.pop("ap_task_dismiss_select", None)
    _select_options = [None] + list(_tasks_by_key.keys())
    _selected_key = st.selectbox(
        "Open a task" if team else "Dismiss a task",
        options=_select_options,
        format_func=lambda k: (
            ("— Select a task —" if team else "— Select a task to dismiss —")
            if k is None else _tasks_by_key[k]["title"]
        ),
        key="ap_task_dismiss_select",
    )

    if _selected_key:
        f = _tasks_by_key[_selected_key]
        if team:
            with st.container(border=True):
                st.markdown(f"**{f['title']}**")
                if f.get("detail"):
                    st.caption(f["detail"])
                render_panel(client, "task", f["finding_key"], f["title"], user_id,
                             assignments.get(f["finding_key"]))
        with st.container(border=True):
            # A reason is required — the CHECK constraint enforces it, and
            # this is what an auditor asks about.
            why = st.text_input(
                "Why is this not something you need to do?",
                key=f"ap_dis_why_{f['finding_key']}",
                placeholder="e.g. accepted risk, reviewed and not applicable",
            )
            d1, d2 = st.columns(2)
            if d1.button("Dismiss it", key=f"ap_dis_go_{f['finding_key']}",
                         type="primary", disabled=not (why or "").strip()):
                STORE.dismiss(user_id, client_id, f["producer"],
                              f["finding_key"], why)
                # The dismissed task drops out of open_tasks on the next
                # load, so its key would no longer be a valid option —
                # cleared here rather than left to raise on rerun.
                st.session_state.pop("ap_task_dismiss_select", None)
                st.rerun()
            if d2.button("Cancel", key=f"ap_dis_no_{f['finding_key']}"):
                st.session_state.pop("ap_task_dismiss_select", None)
                st.rerun()
            st.caption(
                "It comes back if the situation changes — a dismissal "
                "applies to this finding, not to any future one that looks "
                "like it."
            )
else:
    st.success("Nothing outstanding.")

