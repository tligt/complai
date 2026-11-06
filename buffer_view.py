"""
buffer_view.py — S57 (D-147, D-149): the "Send to Buffer" box under a
LinkedIn draft on the back office's Monitoring page (regulatory and
marketing feeds).

Each time, the admin chooses how: add to the channel's queue (Buffer's next
free slot), schedule for a date and time (Brussels time), or save it as a
draft in Buffer, to finish and publish there. And how to cite the source:
"Source: <link>" in the post, or the source's name in the post and the link
in the first comment — then with a RECOSA image, since the post has no link
preview. The draft is sent as plain text (no Markdown on LinkedIn), with
every "RECOSA" as a real mention of the RECOSA page (linkedin_post.py).

The text typed on the page is saved back as the item's draft. Every send is
logged in social_posts and listed under the box.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

import buffer_client as B
import linkedin_post as LP
from database import get_supabase_admin

TZ = ZoneInfo("Europe/Brussels")
_MODES = {"queue": "Add to the queue", "scheduled": "Schedule", "draft": "Save as a draft in Buffer"}
_LINKEDIN_MAX = 3000          # LinkedIn's limit for a post's text

# Kept for callers of the S57 name.
plain_text = LP.plain_text


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


def render_send(item: dict, table: str, text: str, user_id: str | None = None) -> None:
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
        picked = st.multiselect(
            "Channels", list(by_id), default=default, key=f"{key}_ch",
            format_func=lambda i: f"{by_id[i].get('name')} ({by_id[i].get('service')})")
        if mode == "draft":
            st.caption("A draft is saved on the channel in Buffer and not published: you "
                       "finish it and schedule it there.")
        due = None
        if mode == "scheduled":
            c1, c2 = st.columns(2)
            tomorrow = (datetime.now(TZ) + timedelta(days=1)).date()
            d = c1.date_input("Date", value=tomorrow, min_value=datetime.now(TZ).date(),
                              key=f"{key}_d")
            t = c2.time_input("Time (Brussels)", value=time(9, 0), step=900, key=f"{key}_t")
            due = datetime.combine(d, t, tzinfo=TZ)

        # ── Source, image ────────────────────────────────────────────────
        # Buffer posts a first comment only on a paid plan (6 Nov): until
        # BUFFER_PAID_PLAN = "true" is set, "Source: link" is the default, so
        # the link is never silently dropped.
        _paid = (os.environ.get("BUFFER_PAID_PLAN") or "").strip().lower() == "true"
        _modes = list(LP.SOURCE_MODES)
        src_mode = st.radio("Source", _modes, format_func=LP.SOURCE_MODES.get,
                            index=_modes.index("comment" if _paid else "link"), key=f"{key}_src")
        if src_mode == "comment" and not _paid:
            st.caption("On Buffer's free plan the first comment isn't posted, so the link "
                       "won't be published. Set BUFFER_PAID_PLAN = \"true\" in the back "
                       "office's secrets after upgrading.")
        src_name = st.text_input("Source name", value=item.get("source") or "",
                                 key=f"{key}_srcname") if src_mode == "comment" else item.get("source")
        src_url = item.get("url") or ""
        if src_mode != "none" and not src_url:
            st.caption("This item has no source link.")
        with_image = st.checkbox("Add a RECOSA image (the headline on a RECOSA card)",
                                 value=(src_mode == "comment"), key=f"{key}_img",
                                 help="A post whose link is in the comment has no link preview; "
                                      "the card gives it a picture.")

        # ── What will go out ─────────────────────────────────────────────
        post, comment = LP.with_source(LP.plain_text(text), src_mode, src_name, src_url)
        with st.container(border=True):
            st.caption("What LinkedIn will show")
            st.text(post)
            if comment:
                st.caption(f"First comment: {comment}")
        n_mentions = len(LP.mentions(post))
        notes = []
        if LP.plain_text(text) != (text or "").strip():
            notes.append("Markdown marks such as **bold** are removed (LinkedIn shows them as they are)")
        if n_mentions:
            notes.append(f"“RECOSA” becomes a mention of the RECOSA page ({n_mentions}×)")
        if notes:
            st.caption(". ".join(notes) + ".")
        n = len(post)
        if n > _LINKEDIN_MAX:
            st.warning(f"{n} characters: LinkedIn takes at most {_LINKEDIN_MAX}. Shorten the draft.")
        too_early = mode == "scheduled" and due is not None and due <= datetime.now(TZ)
        if too_early:
            st.caption("Pick a time in the future.")
        disabled = not post.strip() or n > _LINKEDIN_MAX or not picked or too_early

        if st.button("Send to Buffer", type="primary", key=f"{key}_go", disabled=disabled):
            try:
                get_supabase_admin().table(table).update({"linkedin_draft": text}).eq("id", item["id"]).execute()
            except Exception:
                pass
            image_url = None
            if with_image:
                try:
                    image_url = LP.upload_card(LP.headline_card(item.get("title") or "",
                                                                item.get("category")))
                except Exception as e:
                    print(f"RECOSA card not made: {e}")
                if not image_url:
                    st.warning("The RECOSA image couldn't be prepared; sending without it.")
            ok = 0
            for cid in picked:
                c = by_id[cid]
                linkedin = c.get("service") == "linkedin"
                try:
                    res = B.create_post(
                        cid, post, due if mode == "scheduled" else None,
                        draft=(mode == "draft"),
                        first_comment=comment if linkedin else None,
                        annotations=LP.mentions(post) if linkedin else None,
                        image_url=image_url)
                    _log(source_table=table, source_id=item["id"], mode=mode, channel_id=cid,
                         channel_name=c.get("name"), service=c.get("service"), text=post,
                         due_at=res.get("dueAt"), buffer_id=res.get("id"), status="sent",
                         sent_by=user_id)
                    ok += 1
                except B.BufferError as e:
                    _log(source_table=table, source_id=item["id"], mode=mode, channel_id=cid,
                         channel_name=c.get("name"), service=c.get("service"), text=post,
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
