import streamlit as st
from datetime import datetime
from auth import get_user_id
from database import get_supabase, load_clients

EVENT_ICONS = {
    "document_generated": "📄",
    "gap_assessment_run": "📊",
    "audit_run": "🔍",
}

st.title("Activity Log")
st.caption("A record of compliance actions taken on your account.")

user_id = get_user_id()
clients = load_clients(user_id)

# Single-owner model until S38 (Advisory multi-client workspace) — one client per user
client_id = clients[0]["id"] if clients else None

if not client_id:
    st.info("No client profile found yet.")
else:
    supabase = get_supabase()
    try:
        rows = (
            supabase.table("audit_log")
            .select("*")
            .eq("company_id", client_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
    except Exception as e:
        st.error(f"Could not load activity log: {e}")
        rows = []

    if not rows:
        st.info("No activity recorded yet.")
    else:
        for row in rows:
            ts = datetime.fromisoformat(
                row["created_at"].replace("Z", "+00:00")
            ).strftime("%d %b %Y, %H:%M")
            icon = EVENT_ICONS.get(row["event_type"], "•")
            st.markdown(f"{icon} **{row['summary']}** — {ts}")
