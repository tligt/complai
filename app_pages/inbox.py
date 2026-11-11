"""
app_pages/inbox.py — S56 (D-145): what was given to you, and the comments
and mentions on your work, across every company you can reach. Newest
first; Open goes to the task on the Action plan or to the incident, in the
right company.

D-05: this is the only place the details are shown. The email that points
here says only that something is new.
"""
from i18n import tr  # S64 interface translation (D-164)

import streamlit as st

import work_items as W
from auth import get_user_id
from cached_reads import load_accessible_clients
from display import fmt_date

st.title(tr("Inbox"))
st.caption(tr("Tasks and incidents given to you, and comments on your work, "
           "for every company you work on. Notification emails never include "
           "the details: they're only here."))

user_id = get_user_id()
items = W.inbox(user_id)
clients = {c["id"]: c for c in (load_accessible_clients(user_id) or [])}

_VERB = {"assigned": "gave you", "comment": "commented on", "mention": "asked for you on"}
_ICON = {"assigned": "👤", "comment": "💬", "mention": "📣"}

unread = [n for n in items if not n.get("read_at")]
c1, c2 = st.columns([3, 1])
c1.markdown(f"**{len(unread)} new**" if unread else "Nothing new.")
if unread and c2.button(tr("Mark all as read"), use_container_width=True):
    W.mark_read(user_id)
    st.rerun()

if not items:
    st.info(tr("When someone gives you a task or comments on your work, it appears here."))
    st.stop()


def _open(n: dict) -> None:
    W.mark_read(user_id, ids=[n["id"]])
    c = clients.get(n["client_id"])
    if c:
        st.session_state.selected_client = c
    if n["item_type"] == "task":
        st.session_state["ap_open_task"] = n["item_key"]
        st.switch_page("app_pages/action_plan.py")
    else:
        st.session_state["incident_sel"] = n["item_key"]
        st.session_state["incident_open_panel"] = True
        st.switch_page("app_pages/incidents.py")


for n in items:
    c = clients.get(n["client_id"])
    if not c:
        continue                      # access to that company has ended
    who = W.name_of(n["client_id"], n.get("actor_id")) if n.get("actor_id") else "A routing rule"
    what = "a task" if n["item_type"] == "task" else "an incident"
    verb = _VERB.get(n["kind"], "updated")
    line = f"{who} {verb} {what}"
    new = not n.get("read_at")
    with st.container(border=True):
        a, b = st.columns([5, 1])
        a.markdown(tr("{icon_get_n_kind} {if_new_else}{line}{if_new_else2} · {c_company_name} · :gray[{fmt_date_n_get_created_a}]  \n{n_get_item_title_or}").format(icon_get_n_kind=_ICON.get(n['kind'], '•'), if_new_else='**' if new else '', line=line, if_new_else2='**' if new else '', c_company_name=c['company_name'], fmt_date_n_get_created_a=fmt_date((n.get('created_at') or '')[:10]), n_get_item_title_or=n.get('item_title') or ''))
        if b.button(tr("Open"), key=f"inbox_open_{n['id']}", use_container_width=True,
                    type="primary" if new else "secondary"):
            _open(n)

st.caption(tr("A task that has since been done no longer appears on the Action plan; "
           "its notification stays here for the record."))
