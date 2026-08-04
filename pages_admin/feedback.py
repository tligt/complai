"""
RECOSA — Answer feedback (admin BO).

The point of this page is S24: regulation-aware chunk allocation. A
thumbs-down with reason codes and the retrieved sources attached is the
raw material for deciding what retrieval is getting wrong.

Rows are self-contained — question, answer and sources are snapshotted at
feedback time, so this page still works after a client deletes the
conversation the feedback came from.

No auth guard: admin_app.py handles auth at the app level.
"""

import streamlit as st
from database import (
    load_all_feedback, get_feedback_summary, FEEDBACK_REASONS,
)

REASON_LABELS = dict(FEEDBACK_REASONS)

st.markdown("## Answer feedback")

summary = get_feedback_summary()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", summary["total"])
m2.metric("👍", summary["up"])
m3.metric("👎", summary["down"])
m4.metric("Positive rate",
          f"{summary['positive_rate']}%" if summary["positive_rate"] is not None
          else "—")

if summary["reasons"]:
    st.markdown("#### What's going wrong")
    st.caption("Reason codes across all negative feedback, most frequent first.")
    for code, count in summary["reasons"].items():
        label = REASON_LABELS.get(code, code)
        pct = round(100 * count / max(summary["down"], 1))
        st.markdown(f"**{label}** — {count} ({pct}% of negative)")
        st.progress(min(pct / 100, 1.0))

st.divider()

col_f, col_n = st.columns([2, 1])
with col_f:
    rating_filter = st.selectbox(
        "Show", ["Negative only", "All", "Positive only"], key="fb_filter")
with col_n:
    limit = st.selectbox("Rows", [50, 100, 200], index=1, key="fb_limit")

rating = {"Negative only": "down", "Positive only": "up",
          "All": None}[rating_filter]

rows = load_all_feedback(rating=rating, limit=limit)

if not rows:
    st.info("No feedback recorded yet.")
    st.stop()

st.caption(f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}")

for r in rows:
    icon = "👎" if r["rating"] == "down" else "👍"
    question = (r.get("question") or "").strip() or "(question not captured)"
    header = question[:80] + ("…" if len(question) > 80 else "")

    with st.expander(f"{icon}  {header}", expanded=False):
        st.caption(f"{r['created_at'][:16].replace('T', ' ')}"
                   + (f" · session `{str(r['session_id'])[:8]}`"
                      if r.get("session_id") else ""))

        codes = r.get("reason_codes") or []
        if codes:
            st.markdown("**Flagged as:** "
                        + " · ".join(REASON_LABELS.get(c, c) for c in codes))

        if r.get("comment"):
            st.info(r["comment"])

        st.markdown("**Question**")
        st.markdown(question)

        st.markdown("**Answer given**")
        answer = r.get("answer") or "(not captured)"
        st.markdown(answer[:2000] + ("…" if len(answer) > 2000 else ""))

        sources = r.get("sources") or []
        if sources:
            st.markdown(f"**Sources retrieved ({len(sources)})**")
            # Which regulations were actually pulled — the S24 signal.
            names = [s.get("source", "?") for s in sources]
            st.caption(" · ".join(sorted(set(names))))
            for i, s in enumerate(sources, 1):
                st.markdown(f"*{i}. {s.get('source', 'Unknown')}*")
                text = s.get("text", "") or ""
                st.text(text[:300] + ("…" if len(text) > 300 else ""))
        else:
            st.caption("No sources recorded for this answer.")
