import streamlit as st

from display import country_label, fmt_datetime, plural, regulation_label, regulations_text
from auth import get_user_id
from database import load_client_alerts, mark_alert_read, mark_all_alerts_read, get_supabase, get_supabase_admin
from database import count_unread_alerts as _count_unread_alerts_fresh
from zoneinfo import ZoneInfo
from datetime import datetime as _dt

user_id = get_user_id()

st.title("Alerts")
st.caption("Changes in the regulations that apply to you.")


@st.fragment
def _alerts_panel(user_id: str):
    """Everything below the title, as one fragment.

    A click anywhere in here (the unread toggle, Mark read, Mark all as
    read) reruns only this fragment, not the whole page script — so it
    no longer re-imports and re-derives everything else app.py's
    navigation loads on every interaction. Uses the fresh (uncached)
    count_unread_alerts deliberately: this fragment writes to the same
    rows it reads, in the same rerun, and cached_reads' TTL would show
    the pre-mark-read count for a few seconds otherwise.
    """
    # ── Header: count and mark all read, at the top (usability audit H8) ──
    unread = _count_unread_alerts_fresh(user_id)

    h1, h2 = st.columns([3, 1])
    if unread:
        h1.warning(f"You have **{plural(unread, 'unread alert')}**.")
        if h2.button("✓ Mark all as read", use_container_width=True, key="alerts_mark_all"):
            mark_all_alerts_read(user_id)
            st.rerun(scope="fragment")
    else:
        h1.caption("You're up to date — no unread alerts.")

    # ── Load ──────────────────────────────────────────────────────
    try:
        # Not filtered by user_id (S38) — see database.load_client_alerts's
        # note; RLS's has_client_access(client_id, user_id) already scopes
        # this to alerts for clients the account owns or is a member of.
        supabase = get_supabase()
        alerts = (supabase.table("client_alerts")
                  .select("*, regulatory_updates(id, alert_ref, title, summary, url, severity, "
                          "source, regulations, countries, published_at, action_description, language)")
                  .order("notified_at", desc=True)
                  .limit(300)
                  .execute().data) or []
    except Exception as e:
        st.error(f"Could not load alerts: {e}")
        alerts = []

    if not alerts:
        st.info("No regulatory alerts yet. Check back soon — we monitor EU regulatory sources daily.")
        return

    # ── Filters ───────────────────────────────────────────────────
    severity_icons = {"urgent": "🔴", "important": "🟡", "info": "🔵"}
    severity_labels = {"urgent": "Urgent", "important": "Important", "info": "For information"}
    severity_order = {"urgent": 0, "important": 1, "info": 2}
    _upd = lambda a: a.get("regulatory_updates") or {}

    all_regs = sorted({r for a in alerts for r in (_upd(a).get("regulations") or [])})
    f1, f2, f3 = st.columns([2, 2, 1])
    pick_regs = f1.multiselect("Regulation", all_regs, format_func=regulation_label,
                               placeholder="All regulations", key="alerts_f_reg")
    pick_sev = f2.multiselect("Importance", list(severity_labels), format_func=severity_labels.get,
                              placeholder="Any importance", key="alerts_f_sev")
    f3.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
    show_unread_only = f3.toggle("Unread only", value=False, key="alerts_unread_toggle")

    def _keep(a):
        u = _upd(a)
        if show_unread_only and a.get("read_at"):
            return False
        if pick_regs and not set(pick_regs) & set(u.get("regulations") or []):
            return False
        if pick_sev and u.get("severity", "info") not in pick_sev:
            return False
        return True

    shown = [a for a in alerts if _keep(a)]
    if not shown:
        st.info("No alert matches these filters.")
        return

    # Unread first, then by importance; each group newest first (the query order).
    shown.sort(key=lambda a: (1 if a.get("read_at") else 0,
                              severity_order.get(_upd(a).get("severity", "info"), 2)))
    fresh = [a for a in shown if not a.get("read_at")]
    older = [a for a in shown if a.get("read_at")]

    _LANG = {"fr": "French", "nl": "Dutch", "de": "German"}

    def _card(alert, full: bool):
        update = _upd(alert)
        is_read = bool(alert.get("read_at"))
        icon = severity_icons.get(update.get("severity", "info"), "🔵")
        raw = alert.get("notified_at", "")
        try:
            dt = fmt_datetime(raw)
        except Exception:
            dt = raw[:10] if raw else ""
        title = update.get("title", "Regulatory update")
        lang = _LANG.get((update.get("language") or "en").lower()[:2])
        with st.container(border=True):
            col_content, col_action = st.columns([8, 2])
            with col_content:
                st.markdown(f"{icon} " + (f"**{title}**" if not is_read else title)
                            + (f"  :gray[· in {lang}]" if lang else ""))
                if full and update.get("summary"):
                    st.caption(update["summary"])
                if full and update.get("action_description"):
                    st.info(f"**What to do:** {update['action_description']}")
                countries = update.get("countries") or []
                st.caption(" · ".join(filter(None, [
                    update.get("alert_ref") or "",
                    update.get("source", ""),
                    regulations_text(update.get("regulations") or []),
                    ", ".join("EU" if c == "EU" else country_label(c) for c in countries),
                    dt,
                ])))
            with col_action:
                if update.get("url"):
                    st.link_button("🔗 Read more", update["url"], use_container_width=True)
                if not is_read:
                    if st.button("✓ Mark read", key=f"read_{alert['id']}",
                                 use_container_width=True):
                        mark_alert_read(alert["id"], user_id)
                        st.rerun(scope="fragment")

    # Unread alerts in full; the ones already read folded away, one line each.
    for alert in fresh:
        _card(alert, full=True)
    if older:
        with st.expander(f"Read alerts ({len(older)})", expanded=not fresh):
            for alert in older:
                _card(alert, full=False)


_alerts_panel(user_id)
