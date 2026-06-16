import streamlit as st
from auth import init_auth, is_logged_in, login_ui, get_user_id
from database import load_client_alerts, mark_alert_read, count_unread_alerts
from zoneinfo import ZoneInfo
from datetime import datetime as _dt

st.set_page_config(
    page_title="COMPLAI — Regulatory Alerts",
    page_icon="🔔",
    layout="centered"
)

init_auth()

if not is_logged_in():
    login_ui()
    st.stop()

user_id = get_user_id()

# ── Header ────────────────────────────────────────────────────
unread = count_unread_alerts(user_id)

st.title("🔔 Regulatory Alerts")
if unread:
    st.warning(f"You have **{unread} unread alert(s)**.")
else:
    st.caption("You're up to date — no unread alerts.")

st.divider()

# ── Filter ────────────────────────────────────────────────────
show_unread_only = st.toggle("Show unread only", value=False, key="alerts_unread_toggle")

# ── Alerts list ───────────────────────────────────────────────
# Load alerts with manual join
from database import get_supabase, get_supabase_admin
try:
    supabase = get_supabase()
    q = supabase.table("client_alerts")         .select("*, regulatory_updates(id, title, summary, url, severity, source, regulations, countries, published_at, action_description)")         .eq("user_id", user_id)         .order("notified_at", desc=True)         .limit(50)
    if show_unread_only:
        q = q.is_("read_at", "null")
    alerts = q.execute().data or []
except Exception as e:
    st.error(f"Could not load alerts: {e}")
    alerts = []

if not alerts:
    if show_unread_only:
        st.success("✅ No unread alerts.")
    else:
        st.info("No regulatory alerts yet. Check back soon — we monitor EU regulatory sources daily.")
    st.stop()

severity_icons = {"urgent": "🔴", "important": "🟡", "info": "🔵"}
severity_order = {"urgent": 0, "important": 1, "info": 2}

# Sort: unread first, then by severity, then by date
alerts.sort(key=lambda a: (
    1 if a.get("read_at") else 0,
    severity_order.get(
        (a.get("regulatory_updates") or {}).get("severity", "info"), 2
    )
))

for alert in alerts:
    update = alert.get("regulatory_updates") or {}
    is_read = bool(alert.get("read_at"))

    severity = update.get("severity", "info")
    icon = severity_icons.get(severity, "🔵")

    # Format timestamp
    try:
        raw = alert.get("notified_at", "")
        dt = _dt.fromisoformat(raw.replace("Z", "+00:00")) \
                .astimezone(ZoneInfo("Europe/Brussels")) \
                .strftime("%d %b %Y %H:%M")
    except Exception:
        dt = raw[:10] if raw else ""

    # Card styling — dimmed if read
    with st.container(border=True):
        col_icon, col_content, col_action = st.columns([1, 7, 2])

        col_icon.markdown(f"### {icon}")
        if not is_read:
            col_icon.markdown("🆕")

        with col_content:
            title = update.get("title", "Regulatory Update")
            if not is_read:
                st.markdown(f"**{title}**")
            else:
                st.markdown(f"{title}")

            if update.get("summary"):
                st.caption(update["summary"])

            if update.get("action_description"):
                st.info(f"**What to do:** {update['action_description']}")

            # Tags
            regs = update.get("regulations") or []
            countries = update.get("countries") or []
            source = update.get("source", "")
            tags = " · ".join(filter(None, [
                source,
                ", ".join(regs) if regs else "",
                ", ".join(countries) if countries else "",
                dt,
            ]))
            st.caption(tags)

        with col_action:
            if update.get("url"):
                st.link_button("🔗 Read more", update["url"], use_container_width=True)

            if not is_read:
                if st.button("✓ Mark read", key=f"read_{alert['id']}",
                             use_container_width=True):
                    mark_alert_read(alert["id"], user_id)
                    st.rerun()
            else:
                st.caption("✓ Read")

# ── Mark all read ─────────────────────────────────────────────
if unread > 0:
    st.divider()
    if st.button("✓ Mark all as read", use_container_width=True):
        for alert in alerts:
            if not alert.get("read_at"):
                mark_alert_read(alert["id"], user_id)
        st.rerun()
