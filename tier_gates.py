"""
tier_gates.py — "this needs a higher plan" checks + the upsell popup.

Visible-but-inert, by explicit decision: a gated control stays on the page
and clickable rather than being disabled or hidden, and clicking it opens
the popup below instead of doing the thing. The reasoning is that a
disabled button with no explanation reads as broken, not as "upgrade to use
this" — the control has to stay reachable for the upsell to ever be seen.

Streamlit-dependent (st.dialog), so — same discipline as cached_reads.py —
this is imported by pages, never by database.py or the cron scripts.

One gate exists so far (client_limit_reached). Adding the next one is:
a small function here answering "is this account over its limit", plus
a call to upsell_dialog() with the message; nothing about the pattern
needs to change.
"""

import streamlit as st

from database import get_user_profile
from cached_reads import load_clients


def client_limit_reached(user_id: str) -> bool:
    """Professional: one client. Advisory: unlimited.

    Checked against the real count, not the tier alone — a Professional
    account with zero clients yet is not "at its limit", it just hasn't
    used its one slot. Advisory is never gated here; S48's per-seat/
    per-division limits are a different, not-yet-built question.
    """
    profile = get_user_profile(user_id)
    tier = profile.get("subscription_tier") or "professional"
    if tier == "advisory":
        return False
    return len(load_clients(user_id) or []) >= 1


@st.dialog("Upgrade to add another client")
def upsell_dialog(reason: str):
    st.write(reason)
    st.page_link("pages/profile.py", label="Go to Profile to upgrade →")
