import streamlit as st

import table_view as tv
from database import get_supabase_admin, get_token_summary_by_client
from datetime import datetime, timedelta, timezone

st.title("Dashboard")
st.caption("Usage, activity and abuse monitoring across all clients.")

admin = get_supabase_admin()

# ── Period selector ───────────────────────────────────────────
period = st.radio(
    "Period",
    ["Last 7 days", "Last 30 days", "All time"],
    horizontal=True,
    index=1,
)

now = datetime.now(timezone.utc)
if period == "Last 7 days":
    since = (now - timedelta(days=7)).isoformat()
elif period == "Last 30 days":
    since = (now - timedelta(days=30)).isoformat()
else:
    since = None

st.divider()

# ── Top-level stats ───────────────────────────────────────────
try:
    from database import count_open_tickets
    t1, t2, t3 = st.columns(3)
    _open = count_open_tickets()
    t1.metric("Open tickets", _open, help="Open or in progress.")
    _soon = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    # S59: trials are the customer accounts'.
    _trials = admin.table("accounts").select("id, trial_ends_at") \
        .eq("status", "trial").execute().data or []
    t2.metric("Trials running", len(_trials))
    t3.metric("Trials ending within 7 days",
              sum(1 for p in _trials if (p.get("trial_ends_at") or "9") <= _soon))

    col1, col2, col3, col4 = st.columns(4)

    clients_res = admin.table("clients").select("id", count="exact").execute()
    col1.metric("Total clients", clients_res.count or 0, help="All time.")

    profiles_res = admin.table("profiles").select("id", count="exact").execute()
    col2.metric("Registered users", profiles_res.count or 0, help="All time.")

    docs_q = admin.table("documents").select("id", count="exact")
    if since:
        docs_q = docs_q.gte("generated_at", since)
    docs_res = docs_q.execute()
    col3.metric("Documents generated", docs_res.count or 0)

    gaps_q = admin.table("gap_assessments").select("id", count="exact")
    if since:
        gaps_q = gaps_q.gte("created_at", since)
    gaps_res = gaps_q.execute()
    col4.metric("Gap assessments", gaps_res.count or 0)

except Exception as e:
    st.warning(f"Could not load top-level stats: {e}")

st.divider()

# ── Per-client table ──────────────────────────────────────────
st.subheader("👥 Clients")

try:
    clients_res = admin.table("clients") \
        .select("id, user_id, account_id, company_name, sector, country, regulations, created_at") \
        .order("created_at", desc=True) \
        .execute()
    clients = clients_res.data or []

    if not clients:
        st.info("No clients yet.")
    else:
        # Load usage counts
        docs_all = admin.table("documents").select("client_id").execute().data or []
        doc_counts = {}
        for d in docs_all:
            cid = d.get("client_id")
            if cid:
                doc_counts[cid] = doc_counts.get(cid, 0) + 1

        gaps_all = admin.table("gap_assessments").select("client_id").execute().data or []
        gap_counts = {}
        for g in gaps_all:
            cid = g.get("client_id")
            if cid:
                gap_counts[cid] = gap_counts.get(cid, 0) + 1

        # Per company (chat_history.client_id). It was counted per owner
        # until 9 Nov, so every company of one owner showed the same number.
        # A question is one user message; the assistant's answers are not counted.
        chats_all = admin.table("chat_history").select("client_id") \
            .eq("role", "user").execute().data or []
        chat_counts = {}
        for ch in chats_all:
            k = ch.get("client_id")
            if k:
                chat_counts[k] = chat_counts.get(k, 0) + 1

        # Token summary per client
        token_summary = get_token_summary_by_client(since=since)
        token_by_client = {s.get("client_id") or s.get("user_id"): s for s in token_summary}

        DOC_ABUSE_THRESHOLD = 20

        # The shared table (table_view.py, BO review 9 Nov): sortable; a
        # row's ⋮ opens the company's account on Companies. It replaced one
        # row of metric boxes per company. Counts are all time; cost follows
        # the period above.
        _rows = []
        for client in clients:
            cid, uid = client["id"], client["user_id"]
            n_docs = doc_counts.get(cid, 0)
            tok = token_by_client.get(cid) or token_by_client.get(uid) or {}
            cost_usd = tok.get("total_cost_usd", 0.0)
            _rows.append({"id": cid, "cells": {
                "company": client.get("company_name"),
                "joined": client.get("created_at"),
                "sector": client.get("sector"), "country": client.get("country"),
                "regs": ", ".join(client.get("regulations") or []),
                "docs": n_docs, "gaps": gap_counts.get(cid, 0), "chats": chat_counts.get(cid, 0),
                "cost": (f"${cost_usd:.4f}" if cost_usd > 0 else None, cost_usd),
                "flag": (f"⚠️ >{DOC_ABUSE_THRESHOLD} documents", 1)
                        if n_docs >= DOC_ABUSE_THRESHOLD else ("✅ OK", 0),
            }, "actions": [
                {"id": "account", "label": "Open its account on Companies", "icon": "🏢",
                 "disabled": None if client.get("account_id") else "Not linked to an account"},
            ]})
        _hit = tv.table(_rows, [
            {"key": "company", "label": "Company"}, {"key": "joined", "label": "Joined", "kind": "date"},
            {"key": "sector", "label": "Sector"}, {"key": "country", "label": "Country"},
            {"key": "regs", "label": "Regulations"},
            {"key": "docs", "label": "Docs", "kind": "number"},
            {"key": "gaps", "label": "Gaps", "kind": "number"},
            {"key": "chats", "label": "Questions", "kind": "number"},
            {"key": "cost", "label": "AI cost"}, {"key": "flag", "label": "Flag"},
        ], key="dash_clients", sort=("joined", "desc"))
        if _hit and _hit["action"] == "account":
            _c = next((c for c in clients if c["id"] == _hit["row"]), None)
            if _c and _c.get("account_id"):
                st.session_state.acc_open = _c["account_id"]
                st.session_state["_tv_focus_accounts"] = True
                st.switch_page("pages_admin/companies.py")

except Exception as e:
    st.error(f"Could not load client data: {e}")

# ── Token usage detail ────────────────────────────────────────
st.subheader("💰 Token usage & cost")

CLIENT_FEATURES = {"chat", "chat_classify", "docgen", "docgen_suggest", "gap_single",
                   "gap_full", "translate", "draft_insert"}

FEAT_LABELS = {
    "chat":                  "💬 Chat",
    "docgen":                "📄 Document generation",
    "docgen_suggest":        "🤖 Activity suggestions",
    "gap_single":            "🔍 Document review",
    "gap_full":              "🏢 Full compliance check",
    "monitoring_summarise":  "📡 Regulatory monitoring",
    "embedding":             "🧠 KB embeddings",
    "chat_classify":         "💬 Chat — question routing",
    "translate":             "🌐 Translation",
    "draft_insert":          "✍️ Drafted inserts",
    "monitoring_format":     "📡 Monitoring — formatting",
    "linkedin_draft":        "📣 LinkedIn drafts",
    "marketing_search":      "📣 Marketing monitoring",
    "marketing_monitor_analyse": "📣 Marketing monitoring — analysis",
}

try:
    from database import load_token_usage
    all_rows = load_token_usage(since=since)

    client_rows   = [r for r in all_rows if r.get("feature") in CLIENT_FEATURES]
    internal_rows = [r for r in all_rows if r.get("feature") not in CLIENT_FEATURES]

    tab_client, tab_internal = st.tabs(["👥 Client usage", "⚙️ Internal / operational"])

    with tab_client:
        if not client_rows:
            st.info("No client token usage recorded yet for this period.")
        else:
            c_tokens = sum(r.get("total_tokens", 0) for r in client_rows)
            c_cost   = sum(float(r.get("cost_usd", 0)) for r in client_rows)
            c_calls  = len(client_rows)

            t1, t2, t3 = st.columns(3)
            t1.metric("API calls", c_calls)
            t2.metric("Total tokens", f"{c_tokens:,}")
            t3.metric("Total cost (USD)", f"${c_cost:.4f}")
            st.caption("Estimated at Mistral's list prices per model (database._MISTRAL_PRICES).")

            feat_totals = {}
            for r in client_rows:
                f = r.get("feature", "unknown")
                feat_totals[f] = feat_totals.get(f, 0) + r.get("total_tokens", 0)

            st.markdown("**By feature:**")
            for feat, tokens in sorted(feat_totals.items(), key=lambda x: -x[1]):
                st.caption(f"{FEAT_LABELS.get(feat, feat)}: {tokens:,} tokens")

    with tab_internal:
        if not internal_rows:
            st.info("No internal token usage recorded yet for this period.")
        else:
            i_tokens = sum(r.get("total_tokens", 0) for r in internal_rows)
            i_cost   = sum(float(r.get("cost_usd", 0)) for r in internal_rows)
            i_calls  = len(internal_rows)

            t1, t2, t3 = st.columns(3)
            t1.metric("API calls", i_calls)
            t2.metric("Total tokens", f"{i_tokens:,}")
            t3.metric("Total cost (USD)", f"${i_cost:.4f}")
            st.caption("Monitoring, LinkedIn drafts, embeddings. Logged since 9 Nov; "
                       "earlier internal calls were not recorded.")

            feat_totals = {}
            for r in internal_rows:
                f = r.get("feature", "unknown")
                feat_totals[f] = feat_totals.get(f, 0) + r.get("total_tokens", 0)

            st.markdown("**By feature:**")
            for feat, tokens in sorted(feat_totals.items(), key=lambda x: -x[1]):
                st.caption(f"{FEAT_LABELS.get(feat, feat)}: {tokens:,} tokens")

except Exception as e:
    st.warning(f"Could not load token usage: {e}")
