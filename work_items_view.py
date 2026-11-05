"""
work_items_view.py — S56 (D-145): the "who handles it" and comments panel
for one task or incident, shared by the Action plan and Incidents pages,
and the routing rules section of the Team page.
"""

from __future__ import annotations

import streamlit as st

import work_items as W
from database import can_edit, can_manage_people
from display import fmt_date


def _when(ts: str | None) -> str:
    return fmt_date((ts or "")[:10]) if ts else ""


def render_panel(client: dict, item_type: str, item_key: str, title: str,
                 user_id: str, current_row: dict | None = None) -> None:
    """Assignment and comments for one item. Marks the person's
    notifications about it as read."""
    cid = client["id"]
    W.mark_read(user_id, item=(item_type, item_key))
    editable = can_edit(client.get("role"))
    assignee = (current_row or {}).get("assignee_id")
    import hashlib
    k = f"wi_{item_type}_{hashlib.md5(item_key.encode()).hexdigest()[:10]}"

    # ── Who handles it ────────────────────────────────────────────────────
    people = W.assignable(cid)
    ids = [None] + [p["id"] for p in people]
    if assignee and assignee not in ids:
        ids.append(assignee)              # a former member: shown, not offered
    label = lambda i: "Nobody yet" if i is None else (
        W.name_of(cid, i) + (" (you)" if i == user_id else ""))
    if editable and W.has_team(cid):
        pick = st.selectbox("Handled by", ids, index=ids.index(assignee) if assignee in ids else 0,
                            format_func=label, key=f"{k}_who")
        if pick != assignee:
            if W.assign(cid, item_type, item_key, title, pick, user_id):
                st.toast(f"Given to {label(pick)}." if pick else "Nobody handles it now.")
                st.rerun()
            st.error("Couldn't save that. Try again.")
    else:
        st.markdown(f"**Handled by:** {label(assignee)}")
    if current_row:
        how = "routing rule" if current_row.get("source") == "rule" else W.name_of(cid, current_row.get("assigned_by"))
        st.caption(f"Since {_when(current_row.get('created_at'))}, by {how}.")

    # ── Comments ──────────────────────────────────────────────────────────
    thread = W.comments(cid, item_type, item_key)
    st.markdown(f"**Comments** · {len(thread)}" if thread else "**Comments**")
    for c in thread:
        st.markdown(f"**{W.name_of(cid, c.get('author_id'))}** · "
                    f":gray[{_when(c.get('created_at'))}]  \n{c['body']}")
    if not W.has_team(cid) and not thread:
        st.caption("Comments are for the people working on this company together. "
                   "Invite someone on the Team page to discuss it here.")
        return
    with st.form(f"{k}_form", clear_on_submit=True):
        body = st.text_area("Add a comment", key=f"{k}_body", height=80,
                            placeholder="A question, an update, what's left to do…",
                            label_visibility="collapsed")
        others = [p for p in W.people(cid) if p["id"] != user_id]
        mention = st.multiselect("Also notify", [p["id"] for p in others],
                                 format_func=lambda i: W.name_of(cid, i), key=f"{k}_at",
                                 placeholder="Also notify… (the person handling it and "
                                             "earlier commenters are told anyway)")
        if st.form_submit_button("Post comment"):
            if W.post_comment(cid, item_type, item_key, title, user_id, body,
                              mention, assignee_id=assignee):
                st.rerun()
            else:
                st.warning("Write something first." if not (body or "").strip()
                           else "Couldn't post it. Try again.")
    st.caption("Comments stay inside RECOSA: notification emails never include them.")


def render_rules(client: dict, user_id: str) -> None:
    """Team page: the default person per area for one company."""
    cid = client["id"]
    if not W.has_team(cid):
        return
    st.markdown("**Who handles what**")
    st.caption("New action-plan tasks and incidents go to this person automatically, "
               "and they're told in their inbox. Anyone who may edit can still give a "
               "task to someone else.")
    rr = W.rules(cid)
    people = W.assignable(cid)
    ids = [None] + [p["id"] for p in people]
    manage = can_manage_people(client.get("role"))
    cols = st.columns(len(W.AREAS))
    for col, (area, label) in zip(cols, W.AREAS.items()):
        cur = rr.get(area)
        if manage:
            pick = col.selectbox(label, ids, index=ids.index(cur) if cur in ids else 0,
                                 format_func=lambda i: "Nobody" if i is None else W.name_of(cid, i),
                                 key=f"rule_{cid}_{area}")
            if pick != cur:
                if W.set_rule(cid, area, pick, user_id):
                    st.toast(f"{label}: {'nobody' if pick is None else W.name_of(cid, pick)}.")
                    st.rerun()
                st.error("Couldn't save that rule.")
        else:
            col.caption(f"{label}: {W.name_of(cid, cur) if cur else 'nobody'}")
