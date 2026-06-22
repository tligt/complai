import streamlit as st
from database import get_supabase_admin, get_token_summary_by_client
from datetime import datetime, timedelta

st.title("📊 Client Dashboard")
st.caption("Usage, activity and abuse monitoring across all clients.")

admin = get_supabase_admin()

# ── Period selector ───────────────────────────────────────────
period = st.radio(
    "Period",
    ["Last 7 days", "Last 30 days", "All time"],
    horizontal=True,
    index=1,
)

now = datetime.utcnow()
if period == "Last 7 days":
    since = (now - timedelta(days=7)).isoformat()
elif period == "Last 30 days":
    since = (now - timedelta(days=30)).isoformat()
else:
    since = None

st.divider()

# ── Top-level stats ───────────────────────────────────────────
try:
    col1, col2, col3, col4 = st.columns(4)

    clients_res = admin.table("clients").select("id", count="exact").execute()
    col1.metric("Total clients", clients_res.count or 0)

    profiles_res = admin.table("profiles").select("id", count="exact").execute()
    col2.metric("Registered users", profiles_res.count or 0)

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
        .select("id, user_id, company_name, sector, country, regulations, created_at") \
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

        chats_all = admin.table("chat_history").select("user_id").execute().data or []
        chat_counts = {}
        for ch in chats_all:
            uid = ch.get("user_id")
            if uid:
                chat_counts[uid] = chat_counts.get(uid, 0) + 1

        # Token summary per client
        token_summary = get_token_summary_by_client(since=since)
        token_by_client = {s.get("client_id") or s.get("user_id"): s for s in token_summary}

        DOC_ABUSE_THRESHOLD = 20

        # Header
        h1, h2, h3, h4, h5, h6, h7, h8, h9 = st.columns([3, 2, 1, 2, 1, 1, 1, 1, 1])
        h1.markdown("**Company**")
        h2.markdown("**Sector**")
        h3.markdown("**Country**")
        h4.markdown("**Regulations**")
        h5.markdown("**Docs**")
        h6.markdown("**Gaps**")
        h7.markdown("**Chats**")
        h8.markdown("**Cost $**")
        h9.markdown("**Flag**")

        st.divider()

        for client in clients:
            cid = client["id"]
            uid = client["user_id"]

            n_docs  = doc_counts.get(cid, 0)
            n_gaps  = gap_counts.get(cid, 0)
            n_chats = chat_counts.get(uid, 0)
            regs    = ", ".join(client.get("regulations") or [])
            signup  = str(client.get("created_at", ""))[:10]
            flagged = n_docs >= DOC_ABUSE_THRESHOLD

            tok = token_by_client.get(cid) or token_by_client.get(uid) or {}
            cost_usd = tok.get("total_cost_usd", 0.0)

            c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns([3, 2, 1, 2, 1, 1, 1, 1, 1])
            c1.markdown(f"**{client.get('company_name', '—')}**")
            c1.caption(f"Joined {signup}")
            c2.caption(client.get("sector", "—"))
            c3.caption(client.get("country", "—"))
            c4.caption(regs or "—")
            c5.metric("", n_docs, label_visibility="collapsed")
            c6.metric("", n_gaps, label_visibility="collapsed")
            c7.metric("", n_chats, label_visibility="collapsed")
            c8.caption(f"${cost_usd:.4f}" if cost_usd > 0 else "—")
            if flagged:
                c9.error("⚠️")
                c9.caption(f">{DOC_ABUSE_THRESHOLD}")
            else:
                c9.caption("✅ OK")

            st.divider()

except Exception as e:
    st.error(f"Could not load client data: {e}")

# ── Token usage detail ────────────────────────────────────────
st.subheader("💰 Token usage & cost")

CLIENT_FEATURES = {"chat", "docgen", "docgen_suggest", "gap_single", "gap_full"}
INTERNAL_FEATURES = {"monitoring_summarise", "embedding"}

FEAT_LABELS = {
    "chat":                  "💬 Chat",
    "docgen":                "📄 Document generation",
    "docgen_suggest":        "🤖 Activity suggestions",
    "gap_single":            "🔍 Document review",
    "gap_full":              "🏢 Full compliance check",
    "monitoring_summarise":  "📡 Regulatory monitoring",
    "embedding":             "🧠 KB embeddings",
}

try:
    from database import load_token_usage
    all_rows = load_token_usage(since=since)

    client_rows   = [r for r in all_rows if r.get("feature") in CLIENT_FEATURES]
    internal_rows = [r for r in all_rows if r.get("feature") in INTERNAL_FEATURES]

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
            st.caption("Mistral Large — $2.00/M input · $6.00/M output")

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
            st.caption("Mistral Large (summarisation) + mistral-embed (embeddings)")

            feat_totals = {}
            for r in internal_rows:
                f = r.get("feature", "unknown")
                feat_totals[f] = feat_totals.get(f, 0) + r.get("total_tokens", 0)

            st.markdown("**By feature:**")
            for feat, tokens in sorted(feat_totals.items(), key=lambda x: -x[1]):
                st.caption(f"{FEAT_LABELS.get(feat, feat)}: {tokens:,} tokens")

except Exception as e:
    st.warning(f"Could not load token usage: {e}")
