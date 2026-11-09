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

import table_view as tv

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

# The task table is the shared table (table_view.py, BO review point 4,
# 9 Nov): a click opens the task below; its ⋮ menu offers "Fix it" (the
# page where it is done) and "Open". It replaced an st.dataframe with a
# ButtonColumn plus a "select a task" box under it.
_TASK_LINK_PAGES = OV.TASK_LINK_PAGES


if open_tasks:
    _icon = {T.BLOCKING: "🔴", T.DUE: "🟠", T.OPEN: "⚪"}
    _talk = W.comment_counts(client_id, "task") if team else {}

    def _who(f):
        a = (assignments.get(f["finding_key"]) or {}).get("assignee_id")
        return ("You" if a == user_id else W.name_of(client_id, a)) if a else ""

    _tasks_by_key = {f["finding_key"]: f for f in open_tasks}
    # S56: the inbox opens a task here (ap_open_task, set by app_pages/inbox.py).
    _from_inbox = st.session_state.pop("ap_open_task", None)
    if _from_inbox in _tasks_by_key:
        st.session_state["ap_task_dismiss_select"] = _from_inbox
    if st.session_state.get("ap_task_dismiss_select") not in _tasks_by_key:
        st.session_state.pop("ap_task_dismiss_select", None)

    _cols = [{"key": "task", "label": "Task"}, {"key": "detail", "label": "Detail"}]
    if team:
        _cols.append({"key": "who", "label": "Handled by"})
    _cols.append({"key": "due", "label": "Due", "kind": "date"})
    _hit = tv.table(
        [{"id": f["finding_key"], "cells": {
            "task": f"{_icon.get(f['severity'], '⚪')} {f['title']}"
                    + (f"  💬 {_talk[f['finding_key']]}" if _talk.get(f["finding_key"]) else ""),
            "detail": f.get("detail"),
            "who": _who(f) if team else None,
            "due": f.get("due"),
        }, "actions": [
            {"id": "open", "label": "Open" if team else "Open (dismiss, details)", "icon": "📂"},
            {"id": "fix", "label": "Fix it", "icon": "🛠️",
             "disabled": None if _TASK_LINK_PAGES.get(f.get("link") or "")
             else "Done outside RECOSA, or on this page"},
            {"id": "dismiss", "label": "Dismiss, with a reason", "icon": "🚫"},
        ]} for f in open_tasks],
        _cols, key="ap_tasks", current=st.session_state.get("ap_task_dismiss_select"),
        empty="Nothing outstanding.")
    if _hit and _hit["row"] in _tasks_by_key:
        if _hit["action"] == "fix":
            _page = _TASK_LINK_PAGES.get(_tasks_by_key[_hit["row"]].get("link") or "")
            if _page:
                st.switch_page(_page)
        st.session_state["ap_task_dismiss_select"] = _hit["row"]
    _selected_key = st.session_state.get("ap_task_dismiss_select")

    if _selected_key:
        tv.focus("ap_tasks")
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

