import streamlit as st
from database import (
    get_supabase,
    get_supabase_admin,
    count_unread_alerts,
    load_document_files,
    load_audit_files,
    get_current_client_documents,
)
from auth import get_user_id

st.title("📊 Dashboard")
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
    st.stop()

company_name = client.get("company_name", "Your company")
client_id    = client.get("id")
regulations  = client.get("regulations") or ["GDPR"]

# ── Obligation ID → document type mapping ─────────────────────
OBLIGATION_TO_DOC = {
    "gdpr_01": "privacy_policy",
    "gdpr_07": "privacy_policy",
    "gdpr_12": "privacy_policy",
    "gdpr_15": "privacy_policy",
    "gdpr_02": "rop",
    "gdpr_03": "rop",
    "gdpr_09": "rop",
    "gdpr_05": "dpa",
    "gdpr_11": "dpa",
    "gdpr_06": "incident_response",
    "nis2_01": "incident_response",
    "nis2_02": "incident_response",
    "nis2_03": "incident_response",
    "nis2_04": "incident_response",
    "eprivacy_01": "cookie_policy",
    "eprivacy_02": "cookie_policy",
}

# ── Document catalog ──────────────────────────────────────────
DOC_CATALOG = {
    "privacy_policy":    {"label": "Privacy Policy",              "regulations": ["GDPR"]},
    "rop":               {"label": "Records of Processing (RoPA)", "regulations": ["GDPR"]},
    "dpa":               {"label": "Data Processing Agreement",    "regulations": ["GDPR"]},
    "incident_response": {"label": "Incident Response Plan",      "regulations": ["GDPR", "NIS2"]},
    "cookie_policy":     {"label": "Cookie Policy",               "regulations": ["GDPR"]},
}

REG_LABELS = {"GDPR": "GDPR", "NIS2": "NIS2", "EU_AI_ACT": "EU AI Act"}

REG_DOCS = {
    "GDPR":     ["privacy_policy", "rop", "dpa", "incident_response", "cookie_policy"],
    "NIS2":     ["incident_response"],
    "EU_AI_ACT": [],
}

# ── Load data ─────────────────────────────────────────────────
try:
    docs_raw = load_document_files(user_id, client_id) or []
    docs_by_type = {}
    for doc in docs_raw:
        dt = doc.get("document_type")
        if dt and dt not in docs_by_type:
            docs_by_type[dt] = doc
except Exception:
    docs_by_type = {}

try:
    client_docs = get_current_client_documents(client_id, user_id) if client_id else {}
except Exception:
    client_docs = {}

try:
    unread_alerts = count_unread_alerts(user_id)
except Exception:
    unread_alerts = 0

try:
    audits = load_audit_files(user_id=user_id)
    last_audit = audits[0] if audits else None
except Exception:
    last_audit = None

# ── Load last gap assessment ──────────────────────────────────
last_gap = None
doc_gap_status = {}  # doc_type → {"status": compliant/partial/missing, "details": [...]}

try:
    admin = get_supabase_admin()
    gap_res = admin.table("gap_assessments") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    if gap_res.data:
        last_gap = gap_res.data[0]
        gaps = last_gap.get("gaps") or []

        # Aggregate obligation statuses per document type
        doc_obligations = {}  # doc_type → list of statuses
        for item in gaps:
            obligation_id = item.get("id", "")
            doc_type = OBLIGATION_TO_DOC.get(obligation_id)
            if doc_type:
                if doc_type not in doc_obligations:
                    doc_obligations[doc_type] = []
                doc_obligations[doc_type].append({
                    "id": obligation_id,
                    "status": item.get("status", "missing"),
                    "explanation": item.get("explanation", ""),
                    "recommendation": item.get("recommendation", ""),
                })

        # Derive per-document status
        for doc_type, items in doc_obligations.items():
            statuses = [i["status"] for i in items]
            if all(s == "compliant" for s in statuses):
                agg = "compliant"
            elif all(s == "missing" for s in statuses):
                agg = "missing"
            else:
                agg = "partial"
            doc_gap_status[doc_type] = {"status": agg, "details": items}

except Exception as e:
    st.warning(f"Could not load gap assessment: {e}")

gap_date = str(last_gap.get("created_at", ""))[:10] if last_gap else None

# ═══════════════════════════════════════════════════════════════
# SECTION 1 — Regulation Status
# ═══════════════════════════════════════════════════════════════
st.subheader(f"Compliance status — {company_name}")
st.caption("Based on your last gap assessment and document repository.")

def reg_status(reg: str):
    required = REG_DOCS.get(reg, [])
    if not required:
        return "🔵", "Not yet assessed"
    if not doc_gap_status:
        # No gap assessment — fall back to document presence
        present = sum(1 for d in required if d in client_docs or d in docs_by_type)
        coverage = present / len(required)
        if coverage >= 0.8:
            return "🟢", "On track"
        elif coverage >= 0.4:
            return "🟡", "In progress"
        else:
            return "🔴", "Action needed"
    # Use gap assessment results
    statuses = [doc_gap_status.get(d, {}).get("status", "missing") for d in required]
    if all(s == "compliant" for s in statuses):
        return "🟢", "On track"
    elif any(s == "compliant" for s in statuses) or any(s == "partial" for s in statuses):
        return "🟡", "In progress"
    else:
        return "🔴", "Action needed"

cols = st.columns(len(regulations))
for col, reg in zip(cols, regulations):
    emoji, label = reg_status(reg)
    with col:
        st.markdown(f"**{REG_LABELS.get(reg, reg)}**")
        st.markdown(f"### {emoji} {label}")

if gap_date:
    st.caption(f"Last gap assessment: {gap_date}")
else:
    st.caption("No gap assessment run yet — status based on document presence only.")

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 2 — Document Checklist
# ═══════════════════════════════════════════════════════════════
st.subheader("📋 Document checklist")
if gap_date:
    st.caption(f"Status from gap assessment run on {gap_date}. Click a row to see details.")
else:
    st.caption("Run a gap assessment to see per-document compliance status.")

relevant_docs = {
    k: v for k, v in DOC_CATALOG.items()
    if any(r in regulations for r in v["regulations"])
}

for doc_type, meta in relevant_docs.items():
    col_label, col_status, col_action = st.columns([3, 2, 2])

    in_repo    = doc_type in client_docs
    in_history = doc_type in docs_by_type
    doc_record = client_docs.get(doc_type) or docs_by_type.get(doc_type)
    gap_info   = doc_gap_status.get(doc_type)

    with col_label:
        reg_tags = " · ".join(
            f"`{REG_LABELS.get(r, r)}`"
            for r in meta["regulations"]
            if r in regulations
        )
        st.markdown(f"**{meta['label']}**  {reg_tags}")

    with col_status:
        if gap_info:
            # Show gap assessment result — most informative
            gs = gap_info["status"]
            if gs == "compliant":
                st.success("✅ Compliant")
            elif gs == "partial":
                st.warning("🟡 Partial")
            else:
                st.error("❌ Not compliant")
        elif in_repo or in_history:
            # Document exists but no gap assessment
            source = (client_docs.get(doc_type) or {}).get("source", "")
            if source == "complai_generated":
                st.success("✅ Generated")
            else:
                st.info("ℹ️ In repository")
        else:
            st.error("➕ Missing")

    with col_action:
        if not in_repo and not in_history:
            if st.button("Generate →", key=f"gen_{doc_type}"):
                st.switch_page("pages/documents.py")
        else:
            if st.button("Gap assessment →", key=f"gap_{doc_type}"):
                st.switch_page("pages/gap.py")

    # Expandable details from gap assessment
    if gap_info and gap_info["details"]:
        with st.expander(f"Details — {meta['label']}", expanded=False):
            for item in gap_info["details"]:
                s = item["status"]
                icon = "✅" if s == "compliant" else ("🟡" if s == "partial" else "❌")
                st.markdown(f"{icon} **{item['id'].upper()}** — {item['explanation']}")
                if item.get("recommendation"):
                    st.caption(f"→ {item['recommendation']}")

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
    st.markdown("**🔍 Gap assessment**")
    if last_gap:
        score_gdpr    = last_gap.get("score_gdpr", "—")
        score_nis2    = last_gap.get("score_nis2", "—")
        score_overall = last_gap.get("score_overall", "—")
        st.info(f"Run on {gap_date}")
        st.caption(f"GDPR: {score_gdpr}/100  ·  NIS2: {score_nis2}/100  ·  Overall: {score_overall}/100")
        if st.button("Run new assessment →"):
            st.switch_page("pages/gap.py")
    else:
        st.warning("No assessment run yet")
        if st.button("Run assessment →"):
            st.switch_page("pages/gap.py")

with col3:
    st.markdown("**💬 AI Compliance Chat**")
    st.info("Ask any compliance question")
    if st.button("Open chat →"):
        st.switch_page("pages/chat.py")
