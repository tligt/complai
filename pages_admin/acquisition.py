"""
pages_admin/acquisition.py — D-176, 13 Nov.

Where signups and leads actually come from: the &src=, ?check= and
?signup= values the website, the free-check funnel and the pricing page
carry, read straight from funnel_events and leads — RECOSA's own,
first-party record of every step (S49, D-115). Umami tracks the same
journeys from outside; this is the un-sampled copy that's already in our
own database, read back for the first time here.

Nothing here is aggregated ahead of time — load_funnel_events and
load_leads return raw rows, grouped in Python. At this scale (low
hundreds of rows) that's simpler than a SQL view, and the "Recent events"
table at the bottom shows the literal raw values, not just a summary.
"""

from datetime import datetime, timezone, timedelta
from collections import Counter

import streamlit as st

import table_view as tv
from database import load_funnel_events, load_leads, get_supabase_admin, SUBSCRIPTION_TIERS

st.title("Acquisition")
st.caption("Where signups and leads come from, read from our own funnel_events and leads "
          "tables — not Umami. The two should roughly agree; if they don't, one of them is "
          "wrong. See each event's actual &src=/?check=/?signup= value in \"Recent events\" "
          "below.")

period = st.radio("Period", ["Last 7 days", "Last 30 days", "All time"],
                  horizontal=True, index=1, key="acq_period")
now = datetime.now(timezone.utc)
since = {"Last 7 days": (now - timedelta(days=7)).isoformat(),
        "Last 30 days": (now - timedelta(days=30)).isoformat(),
        "All time": None}[period]

events = load_funnel_events(since=since)
leads = load_leads(since=since)

if not events and not leads:
    st.info("No funnel events or leads recorded yet in this period.")
    st.stop()

# ── Top line ──────────────────────────────────────────────────────────────
by_event = Counter(e["event"] for e in events)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Check/quiz completed", by_event.get("quiz_completed", 0) + by_event.get("scope_completed", 0))
m2.metric("Leads captured", len(leads))
m3.metric("Signups", by_event.get("signup", 0))
m4.metric("Trials started", by_event.get("trial_started", 0))

st.divider()

# ── Funnel events by stage and source ───────────────────────────────────
st.subheader("Funnel events, by stage and source")
st.caption("Each row is one (event, source, check/plan) combination and how many times it "
          "happened in this period. \"source\" is the &src= value; \"tool\" is ?check= for "
          "the free checks or the plan for a signup/trial.")
rows = Counter((e["event"], e.get("source") or "—", e.get("tool") or "—") for e in events)
tv.table(
    [{"id": f"{i}", "cells": {"event": k[0], "source": k[1], "tool": k[2], "count": n}}
     for i, (k, n) in enumerate(sorted(rows.items(), key=lambda kv: -kv[1]))],
    [{"key": "event", "label": "Event"}, {"key": "source", "label": "Source (&src=)"},
     {"key": "tool", "label": "Tool / plan"}, {"key": "count", "label": "Count", "kind": "number"}],
    key="acq_events", sort=("count", "desc"), empty="No events in this period.")

st.divider()

# ── Leads by tool and source ────────────────────────────────────────────
st.subheader("Leads, by tool and source")
st.caption("An email given on the public quiz or website check. \"Converted\" means that "
          "address later signed up.")
lead_rows = Counter((l.get("tool") or "—", l.get("source") or "—") for l in leads)
converted = Counter((l.get("tool") or "—", l.get("source") or "—") for l in leads if l.get("converted_profile_id"))
tv.table(
    [{"id": f"{i}", "cells": {"tool": k[0], "source": k[1], "count": n,
                              "converted": converted.get(k, 0)}}
     for i, (k, n) in enumerate(sorted(lead_rows.items(), key=lambda kv: -kv[1]))],
    [{"key": "tool", "label": "Tool"}, {"key": "source", "label": "Source (&src=)"},
     {"key": "count", "label": "Leads", "kind": "number"},
     {"key": "converted", "label": "Converted", "kind": "number"}],
    key="acq_leads", sort=("count", "desc"), empty="No leads in this period.")

st.divider()

# ── Trial starts by plan ─────────────────────────────────────────────────
# Not in funnel_events (trial_started doesn't carry the plan) — the
# account itself has it.
st.subheader("Trials started, by plan")
try:
    _accs = get_supabase_admin().table("accounts") \
        .select("plan, created_at") \
        .gte("created_at", since).execute().data if since else \
        get_supabase_admin().table("accounts").select("plan, created_at").execute().data
except Exception as e:
    st.caption(f"Could not load accounts: {e}")
    _accs = []
_by_plan = Counter((a.get("plan") or "—") for a in (_accs or []))
if _by_plan:
    tv.table(
        [{"id": p, "cells": {"plan": SUBSCRIPTION_TIERS.get(p, p), "count": n}}
         for p, n in sorted(_by_plan.items(), key=lambda kv: -kv[1])],
        [{"key": "plan", "label": "Plan"}, {"key": "count", "label": "Accounts opened", "kind": "number"}],
        key="acq_plans", sort=("count", "desc"), empty="None.")
else:
    st.caption("No accounts opened in this period.")

st.divider()

# ── Raw recent events ────────────────────────────────────────────────────
st.subheader("Recent events")
st.caption("The literal rows, newest first — to see an actual &src= or ?check= value, not "
          "just a count.")
tv.table(
    [{"id": str(i), "cells": {"when": e["created_at"], "event": e["event"],
                              "tool": e.get("tool"), "source": e.get("source")}}
     for i, e in enumerate(events[:200])],
    [{"key": "when", "label": "When", "kind": "datetime"}, {"key": "event", "label": "Event"},
     {"key": "tool", "label": "Tool / plan"}, {"key": "source", "label": "Source (&src=)"}],
    key="acq_recent", sort=("when", "desc"), empty="None.")
