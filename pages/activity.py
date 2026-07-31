import streamlit as st
from datetime import datetime
from database import get_supabase

EVENT_ICONS = {
    "document_generated": "📄",
    "gap_assessment_run": "📊",
    "audit_run": "🔍",
}

st.title("Activity Log")
st.caption("A record of compliance actions taken on your account.")

# NOTE: adjust this to match the actual session key used by pages/gap.py
# and pages/documents.py to track the currently-selected client.
client_id = st.session_state.get("selected_client_id")

if not client_id:
    st.info("Select a client to view their activity log.")
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
