import streamlit as st
from database import (
    get_supabase,
    get_supabase_admin,
    load_client_alerts,
    count_unread_alerts,
    load_document_files,
    load_audit_files,
    get_current_client_documents,
)
from auth import get_user_id

st.title("📊 Compliance Dashboard")
st.caption("Your compliance status at a glance.")

user_id = get_user_id()
if not user_id:
    st.error("Please log in to view your dashboard.")
    st.stop()

# ── Load client profile ───────────────────────────────────────
try:
    supabase = get_supabase()
    client_res = supabase.table("clients") \
        .select("*") \
        .eq("user_id", user_id) \
        .single() \
        .execute()
    client = client_res.data or {}
except Exception:
    client = {}

if not client:
    st.warning("Please complete your company profile first.")
    st.page_link("pages/app.py", label="Go to profile setup →")
    st.stop()

company_name = client.get("company_name", "Your company")
client_id    = client.get("id")
regulations  = client.get("regulations") or ["GDPR"]
country      = client.get("country", "BE")

# ── Document type → regulation mapping ───────────────────────
DOC_CATALOG = {
    "privacy_policy":      {"label": "Privacy Policy",           "regulations": ["GDPR"]},
    "rop":                 {"label": "Records of Processing (RoPA)", "regulations": ["GDPR"]},
    "dpa":                 {"label": "Data Processing Agreement", "regulations": ["GDPR"]},
    "incident_response":   {"label": "Incident Response Plan",   "regulations": ["GDPR", "NIS2"]},
    "cookie_policy":       {"label": "Cookie Policy",            "regulations": ["GDPR"]},
}

# ── Load documents ────────────────────────────────────────────
try:
    docs_raw = load_document_files(user_id, client_id) or []
    # Build lookup: document_type → most recent doc
    docs_by_type = {}
    for doc in docs_raw:
        dt = doc.get("document_type")
        if dt and dt not in docs_by_type:
            docs_by_type[dt] = doc
except Exception:
    docs_by_type = {}

# ── Load client_documents (versioned repo) ────────────────────
try:
    client_docs = get_current_client_documents(client_id, user_id) if client_id else {}
except Exception:
    client_docs = {}

# ── Load alerts ───────────────────────────────────────────────
try:
    unread_alerts = count_unread_alerts(user_id)
except Exception:
    unread_alerts = 0

# ── Load last audit ───────────────────────────────────────────
try:
    audits = load_audit_files(user_id=user_id)
    last_audit = audits[0] if audits else None
except Exception:
    last_audit = None

# ═══════════════════════════════════════════════════════════════
# SECTION 1 — Regulation Status Cards
# ═══════════════════════════════════════════════════════════════
st.subheader(f"Compliance status — {company_name}")
st.caption("Based on documents in your repository and open alerts.")

REG_LABELS = {
    "GDPR":       "GDPR",
    "NIS2":       "NIS2",
    "EU_AI_ACT":  "EU AI Act",
}

REG_DOCS = {
    "GDPR":      ["privacy_policy", "rop", "dpa", "incident_response", "cookie_policy"],
    "NIS2":      ["incident_response"],
    "EU_AI_ACT": [],
}

def reg_status(reg: str) -> tuple[str, str]:
    """Return (emoji, label) for a regulation based on doc coverage + alerts."""
    required_docs = REG_DOCS.get(reg, [])
    if not required_docs:
        return "🔵", "Not yet assessed"
    present = sum(1 for d in required_docs if d in client_docs or d in docs_by_type)
    coverage = present / len(required_docs) if required_docs else 0
    if coverage >= 0.8 and unread_alerts == 0:
        return "🟢", "On track"
    elif coverage >= 0.4:
        return "🟡", "In progress"
    else:
        return "🔴", "Action needed"

cols = st.columns(len(regulations))
for col, reg in zip(cols, regulations):
    emoji, label = reg_status(reg)
    with col:
        st.metric(
            label=REG_LABELS.get(reg, reg),
            value=f"{emoji} {label}",
        )

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 2 — Document Checklist
# ═══════════════════════════════════════════════════════════════
st.subheader("📋 Document checklist")
st.caption("Documents required for your selected regulations.")

# Filter catalog to client's regulations
relevant_docs = {
    k: v for k, v in DOC_CATALOG.items()
    if any(r in regulations for r in v["regulations"])
}

if not relevant_docs:
    st.info("No document types mapped for your selected regulations yet.")
else:
    for doc_type, meta in relevant_docs.items():
        col_label, col_status, col_action = st.columns([3, 2, 2])

        in_repo     = doc_type in client_docs
        in_history  = doc_type in docs_by_type
        doc_record  = client_docs.get(doc_type) or docs_by_type.get(doc_type)

        with col_label:
            reg_tags = " · ".join(
                f"`{REG_LABELS.get(r, r)}`"
                for r in meta["regulations"]
                if r in regulations
            )
            st.markdown(f"**{meta['label']}**  {reg_tags}")

        with col_status:
            if in_repo:
                source = client_docs[doc_type].get("source", "")
                date   = str(client_docs[doc_type].get("created_at", ""))[:10]
                if source == "complai_generated":
                    st.success(f"✅ Generated · {date}")
                else:
                    st.warning(f"⚠️ Uploaded · {date}")
            elif in_history:
                date = str(docs_by_type[doc_type].get("generated_at", ""))[:10]
                st.success(f"✅ Generated · {date}")
            else:
                st.error("➕ Missing")

        with col_action:
            if not in_repo and not in_history:
                if st.button("Generate →", key=f"gen_{doc_type}"):
                    st.switch_page("pages/documents.py")
            elif doc_record:
                # Show download link if available
                file_path = (
                    doc_record.get("file_path_docx")
                    or doc_record.get("file_path")
                    or None
                )
                if file_path:
                    st.caption("📥 Available in Documents")
                else:
                    st.caption("📄 In repository")

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 3 — Activity Summary
# ═══════════════════════════════════════════════════════════════
st.subheader("📌 Activity summary")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**🔔 Regulatory alerts**")
    if unread_alerts > 0:
        st.warning(f"{unread_alerts} unread alert(s)")
        if st.button("View alerts →"):
            st.switch_page("pages/alerts.py")
    else:
        st.success("All alerts read ✅")

with col2:
    st.markdown("**🔍 Last gap assessment**")
    if last_audit:
        audit_date = str(last_audit.get("created_at", ""))[:10]
        risk = last_audit.get("risk_level", "—")
        st.info(f"Run on {audit_date}")
        st.caption(f"Risk level: {risk}")
        if st.button("View report →"):
            st.switch_page("pages/gap.py")
    else:
        st.warning("No assessment run yet")
        if st.button("Run assessment →"):
            st.switch_page("pages/gap.py")

with col3:
    st.markdown("**💬 AI Compliance Chat**")
    st.info("Ask any compliance question")
    if st.button("Open chat →"):
        st.switch_page("pages/app.py")
