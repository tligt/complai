"""
buffer_view.py — S57 (D-147): the "Send to Buffer" box under a LinkedIn
draft on the back office's Monitoring page (regulatory and marketing feeds).

Each time, the admin chooses how: add to the channel's queue (Buffer's next
free slot), schedule for a date and time (Brussels time), or save it as a
draft in Buffer, to finish and publish there. The text sent is the draft as edited
on the page, and it is saved back as the item's draft. Every send is logged
in social_posts and listed under the box.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

import buffer_client as B
from database import get_supabase_admin

TZ = ZoneInfo("Europe/Brussels")
_MODES = {"queue": "Add to the queue", "scheduled": "Schedule", "draft": "Save as a draft in Buffer"}
_LINKEDIN_MAX = 3000          # LinkedIn's limit for a post's text


@st.cache_data(ttl=600, show_spinner=False)
def _channels() -> list[dict]:
    return B.channels()


def _history(table: str, source_id: str) -> list[dict]:
    try:
        return (get_supabase_admin().table("social_posts").select("*")
                .eq("source_table", table).eq("source_id", source_id)
                .order("created_at", desc=True).limit(20).execute().data or [])
    except Exception:
        return []


def _log(**row) -> None:
    try:
        get_supabase_admin().table("social_posts").insert(row).execute()
    except Exception as e:
        print(f"Could not log the Buffer send: {e}")


def _fmt(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ).strftime("%d %b %Y %H:%M")
    except ValueError:
        return ts


def render_send(item: dict, table: str, text: str, user_id: str | None) -> None:
    """The box for one item. `text` is the draft as currently edited."""
    key = f"buf_{table[:3]}_{item['id']}"
    # The logged-in admin (the Monitoring page's own user_id is a label).
    user_id = getattr(st.session_state.get("user"), "id", None)
    with st.expander("📤 Send to Buffer", expanded=False):
        if not B.configured():
            st.caption("Add BUFFER_API_KEY to the back office's secrets (Buffer → Settings → "
                       "API → Create a new API key) to send drafts to Buffer.")
            return
        try:
            chans = _channels()
        except B.BufferError as e:
            st.error(str(e))
            return
        if not chans:
            st.info("No channel in Buffer yet. Connect the RECOSA LinkedIn page in Buffer first.")
            return
        by_id = {c["id"]: c for c in chans}
        # RECOSA's own LinkedIn channel first: the Buffer account also holds
        # creagent's page (6 Nov), which must not be the silent default.
        _li = [c for c in chans if c.get("service") == "linkedin"]
        _own = [c for c in _li if "recosa" in (c.get("name") or "").lower()]
        default = [(_own or _li or chans)[0]["id"]]
        mode = st.radio("How", list(_MODES), format_func=_MODES.get, horizontal=True,
                        key=f"{key}_mode")
        due = None
        picked = st.multiselect(
            "Channels", list(by_id), default=default, key=f"{key}_ch",
            format_func=lambda i: f"{by_id[i].get('name')} ({by_id[i].get('service')})")
        if mode == "draft":
            st.caption("A draft is saved on the channel in Buffer and not published: you "
                       "finish it and schedule it there.")
        if True:
            if mode == "scheduled":
                c1, c2 = st.columns(2)
                tomorrow = (datetime.now(TZ) + timedelta(days=1)).date()
                d = c1.date_input("Date", value=tomorrow, min_value=datetime.now(TZ).date(),
                                  key=f"{key}_d")
                t = c2.time_input("Time (Brussels)", value=time(9, 0), step=900, key=f"{key}_t")
                due = datetime.combine(d, t, tzinfo=TZ)
        n = len(text or "")
        if n > _LINKEDIN_MAX:
            st.warning(f"{n} characters: LinkedIn takes at most {_LINKEDIN_MAX}. Shorten the draft.")
        disabled = (not (text or "").strip() or n > _LINKEDIN_MAX
                    or not picked
                    or (mode == "scheduled" and due is not None and due <= datetime.now(TZ)))
        if mode == "scheduled" and due is not None and due <= datetime.now(TZ):
            st.caption("Pick a time in the future.")
        if st.button("Send to Buffer", type="primary", key=f"{key}_go", disabled=disabled):
            try:
                get_supabase_admin().table(table).update({"linkedin_draft": text}).eq("id", item["id"]).execute()
            except Exception:
                pass
            ok = 0
            if True:
                for cid in picked:
                    c = by_id[cid]
                    try:
                        res = B.create_post(cid, text, due if mode == "scheduled" else None,
                                            draft=(mode == "draft"))
                        _log(source_table=table, source_id=item["id"], mode=mode, channel_id=cid,
                             channel_name=c.get("name"), service=c.get("service"), text=text,
                             due_at=res.get("dueAt"), buffer_id=res.get("id"), status="sent",
                             sent_by=user_id)
                        ok += 1
                    except B.BufferError as e:
                        _log(source_table=table, source_id=item["id"], mode=mode, channel_id=cid,
                             channel_name=c.get("name"), service=c.get("service"), text=text,
                             status="error", error=str(e)[:500], sent_by=user_id)
                        st.error(f"{c.get('name')}: {e}")
            if ok:
                st.success(("Saved as a draft" if mode == "draft" else "Sent")
                           + f" to {ok} channel{'s' if ok > 1 else ''}.")
        hist = _history(table, item["id"])
        if hist:
            st.markdown("**Sent before**")
            for h in hist:
                what = ("Idea in Buffer" if h["mode"] == "idea" else
                        f"{h.get('channel_name')} · "
                        + {"queue": "queued", "scheduled": "scheduled", "draft": "draft in Buffer"}.get(h["mode"], h["mode"])
                        + (f" for {_fmt(h.get('due_at'))}" if h.get("due_at") and h["mode"] != "draft" else ""))
                st.caption(("✅ " if h["status"] == "sent" else "⚠️ ") + f"{_fmt(h['created_at'])} — {what}"
                           + (f" — {h['error']}" if h.get("error") else ""))
