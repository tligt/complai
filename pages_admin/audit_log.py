"""
pages_admin/audit_log.py — every company's audit trail, newest first.

An account-level event (a sign-in, a plan change) is written once per
company the person belongs to, so each company's own trail is complete.
Here, across companies, those copies are one event: rows with the same
person, type, text and second are shown once, with their companies listed
(9 Nov — one sign-in showed five times).

The shared table (table_view.py): sortable columns; a row's ⋮ menu filters
on its company.
"""

from datetime import date, datetime, timedelta

import streamlit as st

import table_view as tv
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
st.caption("Every company's trail, newest first. Click a column title to sort; "
           "a row's ⋮ menu filters on its company.")

admin = get_supabase_admin()
try:
    companies = {c["id"]: c["company_name"] for c in
                 admin.table("clients").select("id, company_name").execute().data or []}
except Exception as e:
    st.error(f"Could not load companies: {e}")
    companies = {}
emails = {p["id"]: p.get("email") or "" for p in get_all_profiles() or []}

f1, f2, f3 = st.columns([2, 2, 2])
# A row's ⋮ "Only this company" sets the filter before the widget is drawn.
if st.session_state.get("audit_company_next"):
    st.session_state.audit_company = st.session_state.pop("audit_company_next")
company = f1.selectbox("Company", ["All"] + sorted(companies.values()), key="audit_company")
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
hit = tv.table(
    [{"id": e["id"], "cells": {
        "when": datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")),
        "company": ", ".join(sorted(e["companies"])),
        "who": emails.get(e.get("user_id"), ""),
        "event": EVENT_LABELS.get(e["event_type"], e["event_type"]),
        "what": e.get("summary"),
    }, "actions": [
        {"id": "company", "label": "Show only this company", "icon": "🏢",
         "disabled": None if len(e["companies"]) == 1 and company == "All" else
         ("Already filtered on a company" if company != "All"
          else "This event concerns several companies")},
    ]} for e in shown],
    [{"key": "when", "label": "When", "kind": "datetime"}, {"key": "company", "label": "Company"},
     {"key": "who", "label": "Who"}, {"key": "event", "label": "Event"},
     {"key": "what", "label": "What"}],
    key="audit", sort=("when", "desc"), empty="Nothing recorded for this selection.")
if hit and hit["action"] == "company":
    e = next((x for x in shown if x["id"] == hit["row"]), None)
    if e and len(e["companies"]) == 1 and e["companies"][0] in companies.values():
        st.session_state.audit_company_next = e["companies"][0]
        st.rerun()
