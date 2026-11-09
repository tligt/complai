"""
monitoring_queue.py — the review queue on the back office's Monitoring page
(regulatory and marketing feeds), BO review 9 Nov.

The queue was one closed expander per item, 39 + 61 deep, with no date and
no way to act on several at once. Now:
- the shared table (table_view.py): severity, status, title, source, when
  it was published and found, and which item it repeats; click a row to
  review it below, as before (approve, reject, LinkedIn draft, Buffer);
- bulk actions, rejecting only: the repeats (dedup.mark_duplicates), the
  items found more than N days ago, or a chosen set. Approving stays one
  by one: it can email clients, publish to the Pulse and feed the
  knowledge base, so each one gets a look.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

import table_view as tv
from dedup import mark_duplicates

SEVERITY = {"urgent": "🔴 Urgent", "important": "🟡 Important", "info": "🔵 Info"}
STATUS = {"pending": "⏳ Pending", "url_flagged": "⚠️ Link flagged",
          "approved": "✅ Approved", "rejected": "❌ Rejected"}
OPEN_STATUSES = ("pending", "url_flagged")


def _dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def queue(items: list[dict], *, key: str, found_field: str, reject,
          category: bool = False) -> dict | None:
    """Draw the bulk actions and the table; return the item to review below
    (the clicked one), or None. `reject(id) -> bool` rejects one item."""
    dups = mark_duplicates(items, order=found_field)
    by_id = {u["id"]: u for u in items}
    open_items = [u for u in items if u.get("status") in OPEN_STATUSES]

    notice = st.session_state.pop(f"mq_notice_{key}", None)
    if notice:
        st.success(notice)

    if open_items:
        with st.expander(f"Bulk actions — {len(open_items)} item"
                         f"{'s' if len(open_items) != 1 else ''} to review here", expanded=False):
            st.caption("Rejecting only. Approving stays one by one: it can email clients, "
                       "publish to the Compliance Pulse and add the item to the knowledge base.")
            open_dups = [i for i in dups if by_id[i].get("status") in OPEN_STATUSES]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Repeats ({len(open_dups)})**")
                st.caption("The same item from the same source, reworded. The oldest is kept.")
                if st.button(f"Reject the {len(open_dups)} repeat{'s' if len(open_dups) != 1 else ''}",
                             key=f"mq_dups_{key}", disabled=not open_dups):
                    _reject_all(open_dups, reject, key, "repeat")
            with c2:
                days = st.number_input("Found more than … days ago", min_value=1, value=60,
                                       step=10, key=f"mq_days_{key}")
                cutoff = datetime.now(timezone.utc) - timedelta(days=int(days))
                old = [u["id"] for u in open_items
                       if (_dt(u.get(found_field)) or datetime.now(timezone.utc)) < cutoff]
                if st.button(f"Reject the {len(old)} older item{'s' if len(old) != 1 else ''}",
                             key=f"mq_old_{key}", disabled=not old):
                    _reject_all(old, reject, key, "older item")
            picked = st.multiselect(
                "Or choose items", [u["id"] for u in open_items], key=f"mq_pick_{key}",
                format_func=lambda i: f"{(by_id[i].get('title') or 'Untitled')[:90]} — "
                                      f"{by_id[i].get('source') or ''}",
                placeholder="Pick one or more")
            if st.button(f"Reject the {len(picked)} chosen", key=f"mq_sel_{key}",
                         disabled=not picked):
                _reject_all(picked, reject, key, "chosen item")

    cols = [{"key": "sev", "label": "Severity"}, {"key": "status", "label": "Status"}]
    if category:
        cols.append({"key": "cat", "label": "Category"})
    cols += [{"key": "title", "label": "Title"}, {"key": "source", "label": "Source"},
             {"key": "pub", "label": "Published", "kind": "date"},
             {"key": "found", "label": "Found", "kind": "date"},
             {"key": "dup", "label": "Repeats"}]
    hit = tv.table(
        [{"id": u["id"], "cells": {
            "sev": SEVERITY.get(u.get("severity") or "info"),
            "status": STATUS.get(u.get("status") or "pending", u.get("status")),
            "cat": u.get("category"),
            "title": ((u.get("alert_ref") + " · ") if u.get("alert_ref") else "") + (u.get("title") or "Untitled"),
            "source": u.get("source"),
            "pub": _dt(u.get("published_at")), "found": _dt(u.get(found_field)),
            "dup": "↩ " + (by_id[dups[u["id"]]].get("title") or "")[:40] if u["id"] in dups else None,
        }, "actions": [
            {"id": "open", "label": "Review", "icon": "📂"},
            {"id": "reject", "label": "Reject", "icon": "❌", "danger": True,
             "disabled": None if u.get("status") in OPEN_STATUSES else "Already reviewed"},
        ]} for u in items],
        cols, key=f"mq_{key}", sort=("found", "desc"),
        current=st.session_state.get(f"mq_open_{key}"), empty="Nothing here.")
    if hit and hit["row"] in by_id:
        if hit["action"] == "reject":
            if reject(hit["row"]):
                st.session_state[f"mq_notice_{key}"] = "Rejected: " + (by_id[hit["row"]].get("title") or "")
                if st.session_state.get(f"mq_open_{key}") == hit["row"]:
                    st.session_state.pop(f"mq_open_{key}", None)
                st.rerun()
            st.error("Could not reject it.")
        else:
            st.session_state[f"mq_open_{key}"] = hit["row"]
    sel = by_id.get(st.session_state.get(f"mq_open_{key}") or "")
    if sel:
        if st.button("Close the review", key=f"mq_close_{key}"):
            st.session_state.pop(f"mq_open_{key}", None)
            st.rerun()
    else:
        st.caption("Click an item to review it.")
    return sel


def _reject_all(ids: list[str], reject, key: str, what: str) -> None:
    done = sum(1 for i in ids if reject(i))
    st.session_state[f"mq_notice_{key}"] = (f"Rejected {done} {what}{'s' if done != 1 else ''}"
                                           + ("" if done == len(ids) else f"; {len(ids) - done} failed")
                                           + ".")
    st.session_state.pop(f"mq_pick_{key}", None)
    st.rerun()
