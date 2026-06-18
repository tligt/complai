import streamlit as st
from database import get_supabase_admin
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
    col3.metric("Documents generated", docs_res.count or 0, help=f"In selected period")

    gaps_q = admin.table("gap_assessments").select("id", count="exact")
    if since:
        gaps_q = gaps_q.gte("created_at", since)
    gaps_res = gaps_q.execute()
    col4.metric("Gap assessments", gaps_res.count or 0, help=f"In selected period")

except Exception as e:
    st.warning(f"Could not load top-level stats: {e}")

st.divider()

# ── Per-client table ──────────────────────────────────────────
st.subheader("👥 Clients")

try:
    # Load all clients with their profiles
    clients_res = admin.table("clients") \
        .select("id, user_id, company_name, sector, country, regulations, created_at") \
        .order("created_at", desc=True) \
        .execute()
    clients = clients_res.data or []

    if not clients:
        st.info("No clients yet.")
    else:
        # Load usage counts per client
        client_ids  = [c["id"] for c in clients]
        user_ids    = [c["user_id"] for c in clients]

        # Documents per client
        docs_all = admin.table("documents") \
            .select("client_id") \
            .execute().data or []
        doc_counts = {}
        for d in docs_all:
            cid = d.get("client_id")
            if cid:
                doc_counts[cid] = doc_counts.get(cid, 0) + 1

        # Gap assessments per client
        gaps_all = admin.table("gap_assessments") \
            .select("client_id") \
            .execute().data or []
        gap_counts = {}
        for g in gaps_all:
            cid = g.get("client_id")
            if cid:
                gap_counts[cid] = gap_counts.get(cid, 0) + 1

        # Chat messages per user
        chats_all = admin.table("chat_history") \
            .select("user_id") \
            .execute().data or []
        chat_counts = {}
        for ch in chats_all:
            uid = ch.get("user_id")
            if uid:
                chat_counts[uid] = chat_counts.get(uid, 0) + 1

        # Abuse threshold
        DOC_ABUSE_THRESHOLD = 20

        # Render table header
        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([3, 2, 1, 2, 1, 1, 1, 1])
        h1.markdown("**Company**")
        h2.markdown("**Sector**")
        h3.markdown("**Country**")
        h4.markdown("**Regulations**")
        h5.markdown("**Docs**")
        h6.markdown("**Gaps**")
        h7.markdown("**Chats**")
        h8.markdown("**Flag**")

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

            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([3, 2, 1, 2, 1, 1, 1, 1])
            c1.markdown(f"**{client.get('company_name', '—')}**")
            c1.caption(f"Joined {signup}")
            c2.caption(client.get("sector", "—"))
            c3.caption(client.get("country", "—"))
            c4.caption(regs or "—")
            c5.metric("", n_docs, label_visibility="collapsed")
            c6.metric("", n_gaps, label_visibility="collapsed")
            c7.metric("", n_chats, label_visibility="collapsed")
            if flagged:
                c8.error("⚠️")
                c8.caption(f">{DOC_ABUSE_THRESHOLD} docs")
            else:
                c8.caption("✅ OK")

            st.divider()

except Exception as e:
    st.error(f"Could not load client data: {e}")

# ── Token tracking placeholder ────────────────────────────────
st.subheader("💰 Token usage & cost")
st.info(
    "Token tracking is not yet enabled. "
    "This section will show Mistral API token consumption and estimated cost per client "
    "once Sprint 15 (token tracking middleware) is complete."
)
