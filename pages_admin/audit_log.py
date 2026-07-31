import streamlit as st
from datetime import datetime
from database import get_supabase

EVENT_ICONS = {
    "document_generated": "📄",
    "gap_assessment_run": "📊",
    "audit_run": "🔍",
}

st.title("Audit Trail — All Clients")

supabase = get_supabase()

try:
    clients = supabase.table("clients").select("id, company_name").execute().data
except Exception as e:
    st.error(f"Could not load clients: {e}")
    clients = []

company_lookup = {c["id"]: c["company_name"] for c in clients}
filter_company = st.selectbox("Filter by company", ["All"] + sorted(company_lookup.values()))

query = supabase.table("audit_log").select("*").order("created_at", desc=True).limit(200)
if filter_company != "All":
    cid = next(k for k, v in company_lookup.items() if v == filter_company)
    query = query.eq("company_id", cid)

try:
    rows = query.execute().data
except Exception as e:
    st.error(f"Could not load audit log: {e}")
    rows = []

if not rows:
    st.info("No activity recorded yet.")
else:
    for row in rows:
        ts = datetime.fromisoformat(
            row["created_at"].replace("Z", "+00:00")
        ).strftime("%d %b %Y, %H:%M")
        icon = EVENT_ICONS.get(row["event_type"], "•")
        company_name = company_lookup.get(row["company_id"], "Unknown")
        st.markdown(f"{icon} **{company_name}** — {row['summary']} — {ts}")
