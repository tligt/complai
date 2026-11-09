"""
pages_admin/audit_log.py — every company's audit trail, newest first.

An account-level event (a sign-in, a plan change) is written once per
company the person belongs to, so each company's own trail is complete.
Here, across companies, those copies are one event: rows with the same
person, type, text and second are shown once, with their companies listed
(9 Nov — one sign-in showed five times).

A sortable table (click a column header); the row menu of the shared table
component comes with the table work (BO review, points 4–6).
"""

from datetime import date, datetime, timedelta

import streamlit as st

from database import get_all_profiles, get_supabase_admin

EVENT_LABELS = {
    "sign_in": "Sign-in",
    "document_generated": "Document generated",
    "document": "Document",
    "gap_assessment_run": "Gap assessment",
    "assessment": "Assessment",
    "audit_run": "Website audit",
    "incident": "Incident",
    "team": "Team",
    "assignment": "Assignment",
    "plan": "Plan",
    "support_ticket_created": "Ticket opened",
    "support_ticket_status_changed": "Ticket status",
}
LIMIT = 1000

st.title("Audit Trail")
st.caption("Every company's trail, newest first. Click a column header to sort.")

admin = get_supabase_admin()
try:
    companies = {c["id"]: c["company_name"] for c in
                 admin.table("clients").select("id, company_name").execute().data or []}
except Exception as e:
    st.error(f"Could not load companies: {e}")
    companies = {}
emails = {p["id"]: p.get("email") or "" for p in get_all_profiles() or []}

f1, f2, f3 = st.columns([2, 2, 2])
company = f1.selectbox("Company", ["All"] + sorted(companies.values()))
period = f2.date_input("Period", value=(date.today() - timedelta(days=30), date.today()),
                       max_value=date.today(), format="DD/MM/YYYY")

q = admin.table("audit_log").select("*").order("created_at", desc=True).limit(LIMIT)
if company != "All":
    q = q.eq("company_id", next(k for k, v in companies.items() if v == company))
if isinstance(period, (list, tuple)) and len(period) == 2:
    q = q.gte("created_at", period[0].isoformat()) \
         .lt("created_at", (period[1] + timedelta(days=1)).isoformat())

with st.spinner("Loading the trail…"):
    try:
        rows = q.execute().data or []
    except Exception as e:
        st.error(f"Could not load the audit trail: {e}")
        rows = []

# One row per event (see the module note). The copies are written one after
# the other, so they can straddle a second: copies of the same person, type
# and text within 5 seconds of each other are one event.
def _ts(r: dict) -> datetime:
    return datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))


events: dict[tuple, dict] = {}
last: dict[tuple, tuple] = {}       # (person, type, text) -> its newest event key
for r in rows:                      # newest first
    base = (r.get("user_id"), r["event_type"], r.get("summary"))
    name = companies.get(r.get("company_id"), "—")
    k = last.get(base)
    if k and (_ts(events[k]) - _ts(r)).total_seconds() <= 5 and name not in events[k]["companies"]:
        events[k]["companies"].append(name)
        events[k]["created_at"] = r["created_at"]   # the window follows the copies
        continue
    k = base + (r["id"],)
    events[k] = {**r, "companies": [name]}
    last[base] = k

types = sorted({e["event_type"] for e in events.values()})
picked = f3.multiselect("Event types", types, format_func=lambda t: EVENT_LABELS.get(t, t),
                        placeholder="All")
shown = [e for e in events.values() if not picked or e["event_type"] in picked]

if not shown:
    st.info("Nothing recorded for this selection.")
    st.stop()

st.caption(f"{len(shown)} event{'s' if len(shown) != 1 else ''}"
           + (f" (the newest {LIMIT} rows were read; narrow the period to see older ones)"
              if len(rows) == LIMIT else ""))
st.dataframe(
    [{
        "When": datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")),
        "Company": ", ".join(sorted(e["companies"])),
        "Who": emails.get(e.get("user_id"), "") or "—",
        "Event": EVENT_LABELS.get(e["event_type"], e["event_type"]),
        "What": e.get("summary") or "",
    } for e in shown],
    hide_index=True, width="stretch", height=min(38 + 35 * len(shown), 700),
    column_config={
        "When": st.column_config.DatetimeColumn(format="DD MMM YYYY, HH:mm", width=150),
        "Company": st.column_config.TextColumn(width=200),
        "Who": st.column_config.TextColumn(width=210),
        "Event": st.column_config.TextColumn(width=130),
        "What": st.column_config.TextColumn(width="large"),
    },
)
