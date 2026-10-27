import streamlit as st
from datetime import datetime, timezone

from display import fmt_date, plural
import register as REG
from database import get_supabase_admin
from cached_reads import (
    count_unread_alerts,
    load_document_files,
    load_audit_files,
    get_current_client_documents, get_register_status,
    get_template_languages,
)
from auth import get_user_id
from active_client import get_active_client
from obligations import (
    OBLIGATION_TO_DOC, DOC_CATALOG, REG_DOCS, REGULATION_LABELS,
    OBLIGATION_BY_ID, operational_for_regulations,
    split_by_force, applies_from_label,
)

st.title("Home")
from guide import page_tip
page_tip("dashboard")
st.caption("What to do next, then where you stand.")

user_id = get_user_id()
if not user_id:
    st.error("Please log in to view your dashboard.")
    st.stop()

# ── Load client profile ───────────────────────────────────────
client = get_active_client(user_id)

# S53. An open incident's deadlines come before everything else here: they
# are the only items on this page measured in hours.
import incident_store as _INC
_inc_tasks = _INC.open_findings(user_id, client)
if _inc_tasks:
    # Usability audit H10: one line per incident. Deadlines that depend on
    # the assessment are not listed one by one — "assess it, the earliest
    # possible one is in 20 h" instead of eight apparent emergencies.
    _by_inc: dict = {}
    for _f in _inc_tasks:
        _by_inc.setdefault(_f.get("incident_title") or _f["title"], []).append(_f)
    _lines = []
    for _title, _fs in _by_inc.items():
        _decided = [f for f in _fs if f.get("deadline_state") != "to_decide"]
        _open = [f for f in _fs if f.get("deadline_state") == "to_decide"]
        if _decided:
            _first = min(_decided, key=lambda f: f.get("due_at") or datetime.max.replace(tzinfo=timezone.utc))
            _lines.append(f"**{_title}**: {_first.get('deadline_label') or _first['title']} — {_first['detail']}"
                          + (f" (+{len(_decided) - 1} more)" if len(_decided) > 1 else ""))
        if _open:
            _first = min(_open, key=lambda f: f.get("due_at") or datetime.max.replace(tzinfo=timezone.utc))
            _lines.append(f"**{_title}**: assess it to know which {'other ' if _decided else ''}"
                          f"notifications apply — the earliest of them ({_first.get('deadline_label')}) "
                          f"is due {_first['detail']}.")
    _due = [f for f in _inc_tasks if f["severity"] == "due"]
    (st.error if _due else st.warning)("  \n".join(_lines), icon="🚨")
    if st.button("Open incidents", key="dash_incidents"):
        st.switch_page("app_pages/incidents.py")

# ── What to do next (usability audit batch 2, H2) ─────────────
# A slot at the top, filled at the END of the script: building the action
# plan takes several seconds, and the status below should not wait for it.
_start_slot = st.container()
_next_slot = st.empty()
_next_slot.caption("Working out what to do next…")


company_name = client.get("company_name", "Your company")
client_id    = client.get("id")
regulations  = client.get("regulations") or ["GDPR"]

# S27. The languages this client's documents are produced in. Every one of them
# needs its own in-force version — a French policy does not discharge an
# obligation towards Dutch-speaking data subjects.
doc_languages = [l.lower() for l in (client.get("document_languages") or ["en"])]

# Obligation → document mapping, the document catalogue and the
# regulation→documents map are all DERIVED from obligations.py. They used to
# be hand-maintained here and disagreed with gap_assessment.py — including
# keying RoPA as "rop" while everything else used "ropa", so a generated
# RoPA never matched this checklist.
REG_LABELS = REGULATION_LABELS

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
    # S27. The per-language view: {doc_type: {language: row}}, including
    # drafts. client_docs above collapses to one row per doc_type, which is
    # what the gap scoring wants; this is what the client needs to see, because
    # "in force in FR, still a draft in EN, not available in NL" is three
    # different problems with three different fixes.
    register = get_register_status(client_id, user_id) if client_id else {}
    template_langs = get_template_languages()
except Exception:
    client_docs = {}
    register = {}
    template_langs = {}

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
gap_by_id = {}       # obligation id → gap result, for operational obligations

try:
    # S38: this client's own most recent assessment, not this session's
    # user_id — a workspace member's session user_id never matches the
    # owner's, which would otherwise hide it. Uses the admin client (RLS
    # bypass) so filtering correctly here is the only access control on
    # this query; get_active_client() above already establishes that this
    # session may see client_id at all.
    admin = get_supabase_admin()
    gap_res = admin.table("gap_assessments") \
        .select("*") \
        .eq("client_id", client_id) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    if gap_res.data:
        last_gap = gap_res.data[0]
        gaps = last_gap.get("gaps") or []

        # Every result by id — operational obligations have no doc_type and
        # would otherwise be silently dropped from the dashboard entirely.
        gap_by_id = {g.get("id"): g for g in gaps if g.get("id")}

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

gap_date = fmt_date(str(last_gap.get("created_at", ""))) if last_gap else None

# ═══════════════════════════════════════════════════════════════
# SECTION 1 — Regulation Status
# ═══════════════════════════════════════════════════════════════
st.subheader(f"Compliance status — {company_name}")

# Usability audit C6 (D-123): the one headline figure, the same as on
# Obligations and the Compliance record. It replaces the On track / In progress
# words, which came from document coverage or the gap assessment depending on
# what existed. Loaded once here and reused for "What to do next" below.
import obligation_view as _OV
try:
    _ob_state = _OV.load_state(user_id, client)
except Exception as e:
    st.warning(f"Could not work out your obligations: {e}")
    _ob_state = None
if _ob_state:
    from guide import notice
    notice("headline_v2",
           "Your status is now one figure per regulation: the share of your "
           "obligations that are in place. It counts practices as well as "
           "documents, so it may be lower than the document figure you saw "
           "before — but it is more complete, and it moves as soon as you fix "
           "something.")
    _OV.render_headline(_ob_state)
    _doc_bits = []
    if gap_date:
        _doc_bits.append(f"Last gap assessment: {gap_date}")
    st.caption(" · ".join(_doc_bits + ["Details per obligation on the Obligations page."]))
    if st.button("Open obligations", key="home_open_obligations"):
        st.switch_page("app_pages/obligations.py")

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
    if v["regulations"] and any(r in regulations for r in v["regulations"])
}

# H7: the "no template yet in this language" sentence, once above the list
# instead of on every row; filled after the loop has the statuses.
_unavailable_slot = st.empty()
_all_statuses = []

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

        # S27: the verdict comes from register.document_status(), which has no
        # Streamlit in it. This page only chooses a colour.
        _status = REG.document_status(
            doc_type=doc_type,
            languages=doc_languages,
            register_rows=register.get(doc_type),
            # None, not empty, when the lookup failed: empty means "we have no
            # template", None means "we did not check", and reporting our own
            # gap on a failed lookup tells a client we cannot help them when we
            # do not know that.
            template_languages=template_langs.get(doc_type)
                if template_langs else None,
        )
        _all_statuses.append(_status)
        _note = REG.status_note(_status, multilingual=len(doc_languages) > 1,
                                include_unavailable=False)
        if _note:
            st.caption(_note.capitalize())

    with col_status:
        # Register state outranks the older in_repo / in_history flags: those
        # cannot tell a document the client OPERATES UNDER from one that was
        # merely produced.
        _st8 = _status["state"]
        if _st8 == REG.IN_FORCE:
            st.success("✅ In force")
        elif _st8 == REG.PARTIAL:
            st.warning("🟡 " + REG.status_note(_status).split(" · ")[0].capitalize())
        elif _st8 == REG.DRAFT:
            st.warning("🟠 Draft — not adopted")
        elif _st8 == REG.NOT_AVAILABLE:
            # Ours, not theirs. Blue rather than red, because red on a row the
            # client cannot act on reads as an accusation.
            st.info("🕓 Not available yet")
        elif _st8 == REG.ARCHIVED:
            st.info("📁 Archived")
        elif gap_info:
            # Show gap assessment result — most informative
            gs = gap_info["status"]
            if gs == "compliant":
                st.success("✅ Compliant")
            elif gs == "partial":
                st.warning("🟡 Partial")
            else:
                st.error("❌ Not compliant")
        elif in_repo or in_history:  # pre-S27 rows with no register entry
            # Document exists but no gap assessment
            source = (client_docs.get(doc_type) or {}).get("source", "")
            if source == "complai_generated":
                st.success("✅ Generated")
            else:
                st.info("ℹ️ In repository")
        else:
            # NOT_GENERATED: the template exists, the client has not produced
            # it. Distinct from "not available", which is ours.
            st.error("➕ Not generated")

    with col_action:
        if not in_repo and not in_history:
            if st.button("Generate →", key=f"gen_{doc_type}"):
                st.switch_page("app_pages/documents.py")
        else:
            if st.button("Gap assessment →", key=f"gap_{doc_type}"):
                st.switch_page("app_pages/gap.py")

    # Expandable details from gap assessment
    if gap_info and gap_info["details"]:
        with st.expander(f"Details — {meta['label']}", expanded=False):
            for item in gap_info["details"]:
                s = item["status"]
                icon = "✅" if s == "compliant" else ("🟡" if s == "partial" else "❌")
                st.markdown(f"{icon} **{item['id'].upper()}** — {item['explanation']}")
                if item.get("recommendation"):
                    st.caption(f"→ {item['recommendation']}")

if len(doc_languages) > 1 and REG.unavailable_banner(_all_statuses):
    _unavailable_slot.info(REG.unavailable_banner(_all_statuses))

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 2b — Operational obligations
# ═══════════════════════════════════════════════════════════════
# These are practices, procedures and arrangements — data subject rights
# handling, privacy by design, staff training, access control. No document
# discharges them, which is exactly why they used to distort the document
# scores: a complete privacy policy was marked Partial because it could not
# satisfy obligations that were never about the policy. They are surfaced
# here on their own terms instead of being hidden or mis-attributed.
# Usability audit C6 follow-up: these counts come from the last gap
# assessment, not from today's data, so they sit folded under a dated title
# instead of beside the headline figure as a second score.
operational = operational_for_regulations(regulations)

if last_gap:
    with st.expander(f"⚙️ Your practices — what the gap assessment of {gap_date} found",
                     expanded=False):
        st.caption(
            "Practices and procedures no document can satisfy, as assessed on "
            f"{gap_date}. A snapshot of that day: the figure at the top is today's."
        )

        # Obligations that do not bind yet are reported but never counted as
        # failures. Marking a client red today for a duty arriving in December
        # 2027 is a false alarm, and false alarms are how a compliance tool
        # loses the client's attention for the alarms that matter.
        operational, forthcoming = split_by_force(operational)

        op_rows = []
        for ob in operational:
            res = gap_by_id.get(ob["id"])
            # No result at all means the obligation postdates the last assessment
            # — which happens every time Compliance Pulse adds a requirement.
            # Defaulting that to "missing" would report an untested obligation as
            # a failure.
            status = (res or {}).get("status", "not_assessed")
            op_rows.append((ob, status, res or {}))

        n_ok      = sum(1 for _, s, _ in op_rows if s == "compliant")
        n_partial = sum(1 for _, s, _ in op_rows if s == "partial")
        n_na      = sum(1 for _, s, _ in op_rows if s == "not_applicable")
        n_unknown = sum(1 for _, s, _ in op_rows if s == "not_assessed")
        n_open    = len(op_rows) - n_ok - n_partial - n_na - n_unknown

        st.markdown(" · ".join(filter(None, [
            f"{n_ok} in place", f"{n_partial} partly", f"{n_open} not in place",
            f"{n_unknown} not assessed" if n_unknown else "",
            f"{len(forthcoming)} not yet in force" if forthcoming else "",
        ])))

        if n_unknown:
            st.caption(
                f"{plural(n_unknown, 'obligation')} {'was' if n_unknown == 1 else 'were'} not covered by the assessment on "
                f"{gap_date} — most likely added since. Re-run to include them."
            )

        ICONS = {"compliant": "✅", "partial": "🟡", "not_applicable": "⚪",
                 "not_assessed": "🔍", "missing": "❌"}

        # Highest priority first — an operational gap on access control matters
        # more than one on penetration testing.
        PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
        op_rows.sort(key=lambda r: (
            0 if r[1] in ("missing", "partial") else 1,
            PRIORITY_RANK.get(r[0]["priority"], 9),
        ))

        for reg in regulations:
            reg_rows = [r for r in op_rows
                        if REG_LABELS.get(r[0]["regulation"]) and
                        (r[0]["regulation"] == reg or
                         (reg == "GDPR" and r[0]["regulation"] == "EPRIVACY"))]
            if not reg_rows:
                continue
            st.markdown(
                f"##### {REG_LABELS.get(reg, reg)} — "
                f"{sum(1 for _, s, _ in reg_rows if s in ('missing', 'partial'))} "
                f"of {len(reg_rows)} need attention"
            )
            for ob, status, res in reg_rows:
                st.markdown(
                    f"{ICONS.get(status, '❔')} **{ob['title']}**  "
                    f"`{ob['article']}`"
                )
                if not ob.get("statutory", True):
                    st.caption("↳ Recommended by RECOSA — not a standalone "
                               "statutory requirement.")
                explanation = res.get("explanation") or ob["description"]
                st.caption(explanation)
                if res.get("recommendation") and status != "compliant":
                    st.caption(f"→ {res['recommendation']}")

        if forthcoming:
            st.markdown(f"##### 🕓 Not yet in force ({len(forthcoming)})")
            st.caption(
                "Already law, but not yet binding. Nothing to do today — "
                "shown so the dates are not a surprise."
            )
            for ob in sorted(forthcoming, key=lambda o: o["applies_from"]):
                st.markdown(
                    f"**{ob['title']}**  `{ob['article']}`  ·  "
                    f"applies from **{applies_from_label(ob)}**"
                )
                st.caption(ob["description"])

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 3 — Activity Summary
# ═══════════════════════════════════════════════════════════════
st.subheader("📌 Activity summary")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**🔔 Regulatory alerts**")
    if unread_alerts > 0:
        st.warning(plural(unread_alerts, "unread alert"))
        if st.button("View alerts →"):
            st.switch_page("app_pages/alerts.py")
    else:
        st.success("All alerts read ✅")

with col2:
    st.markdown("**🔍 Gap assessment**")
    if last_gap:
        score_gdpr    = last_gap.get("score_gdpr", "—")
        score_nis2    = last_gap.get("score_nis2", "—")
        score_overall = last_gap.get("score_overall", "—")
        # C6: named for what it measures — the quality of your documents on
        # the day of the run — so it no longer competes with the headline.
        st.info(f"Document quality, assessed {gap_date}")
        st.caption(f"GDPR: {score_gdpr}/100  ·  NIS2: {score_nis2}/100  ·  Overall: {score_overall}/100")
        try:
            _gap_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                str(last_gap.get("created_at")).replace("Z", "+00:00"))).days
        except Exception:
            _gap_age = 0
        if _gap_age > 30:
            st.caption(f":orange[{_gap_age} days old — rerun it to refresh.]")
        if st.button("Run new assessment →"):
            st.switch_page("app_pages/gap.py")
    else:
        st.warning("No assessment run yet")
        if st.button("Run assessment →"):
            st.switch_page("app_pages/gap.py")

with col3:
    st.markdown("**💬 AI Compliance Chat**")
    st.info("Ask any compliance question")
    if st.button("Open chat →"):
        st.switch_page("app_pages/chat.py")

# ── Fill the "What to do next" slot (see the top of the page) ──
from database import count_unread_replies as _unread_replies
_tasks = _ob_state["open_tasks"] if _ob_state else []
_next = [f for f in _tasks if f.get("link") != "incidents"][:3]

# ── Getting started (usability audit batch 3) ─────────────────
# The five steps in the order the product works: each one feeds the next.
# Shown until all five are done; each is worked out from the data, nothing
# to tick by hand.
_in_force_any = any(r.get("status") == "in_force"
                    for per_lang in (register or {}).values() for r in per_lang.values())
_generated_any = bool(docs_by_type) or bool(register)
try:
    import inventory_store as _INVS
    _has_inventory = bool(_INVS.load_systems(user_id, client_id)) and bool(
        _INVS.load_activities(user_id, client_id))
except Exception:
    _has_inventory = True
_steps = [
    ("Complete the company profile", bool(client.get("contact_email") and client.get("legal_name")),
     "app_pages/company.py", "Legal name and a contact email are what documents need most."),
    ("Add your systems and activities", _has_inventory, "app_pages/inventory.py",
     "The tools you use and what you do with personal data."),
    ("Run a gap assessment", bool(last_gap), "app_pages/gap.py",
     "A first score per regulation, and findings for the action plan."),
    ("Generate your documents", _generated_any, "app_pages/documents.py",
     "Privacy policy, register of processing, and the rest your regulations require."),
    ("Adopt them (mark in force)", _in_force_any, "app_pages/compliance_record.py",
     "A document counts once your company operates under it."),
]
if not all(done for _, done, _, _ in _steps):
    with _start_slot.container(border=True):
        _n_done = sum(1 for _, done, _, _ in _steps if done)
        st.markdown(f"**Getting started** · {_n_done} of {len(_steps)} done")
        st.progress(_n_done / len(_steps))
        _next_step = next(i for i, (_, done, _, _) in enumerate(_steps) if not done)
        for _i, (_label, _done, _page, _why) in enumerate(_steps):
            _c1, _c2 = st.columns([5, 1])
            _c1.markdown(("✅ ~~" + _label + "~~") if _done else
                         (f"**{_i + 1}. {_label}**  \n:gray[{_why}]" if _i == _next_step
                          else f"{_i + 1}. {_label}"))
            if _i == _next_step and _c2.button("Start", key="home_start", type="primary",
                                               use_container_width=True):
                st.switch_page(_page)
_alerts_n = count_unread_alerts(user_id)
_replies_n = _unread_replies(user_id)

with _next_slot.container(border=True):
    st.markdown("**What to do next**")
    if not _next:
        st.success("Nothing outstanding on the action plan.")
    _sev_icon = {"blocking": "🔴", "due": "🟠", "open": "⚪"}
    for _i, _f in enumerate(_next):
        _c1, _c2 = st.columns([5, 1])
        _c1.markdown(f"{_sev_icon.get(_f['severity'], '⚪')} **{_f['title']}**"
                     + (f"  \n:gray[{_f['detail']}]" if _f.get("detail") else ""))
        _page = _OV.TASK_LINK_PAGES.get(_f.get("link") or "")
        if _page and _c2.button("Fix it", key=f"home_fix_{_i}", use_container_width=True):
            st.switch_page(_page)
    _b1, _b2, _b3 = st.columns(3)
    if _tasks and _b1.button(f"Action plan ({len(_tasks)})", key="home_plan",
                             use_container_width=True):
        st.switch_page("app_pages/action_plan.py")
    if _alerts_n and _b2.button(f"Alerts ({_alerts_n} unread)", key="home_alerts",
                                use_container_width=True):
        st.switch_page("app_pages/alerts.py")
    if _replies_n and _b3.button(plural(_replies_n, "support reply", "support replies"),
                                 key="home_support", use_container_width=True):
        st.switch_page("app_pages/support.py")
