import time
import json
import requests
import streamlit as st
from datetime import datetime, timezone

from database import (
    # Regulatory
    load_regulatory_updates,
    approve_regulatory_update,
    reject_regulatory_update,
    create_client_alerts,
    ingest_alert_to_qdrant,
    mark_alert_ingested,
    # Marketing
    load_marketing_updates,
    approve_marketing_update,
    reject_marketing_update,
    save_linkedin_draft,
    # Sources
    load_monitoring_sources,
    save_monitoring_source,
    update_monitoring_source,
    delete_monitoring_source,
    # Runs
    load_monitor_runs,
    get_supabase_admin,
)
from slug_generation import slugify

st.title("📡 Monitoring")
st.caption("Regulatory and marketing monitoring — review, approve, and publish.")


# ── Freshness gating helper ─────────────────────────────────────
# Applies to the "Publish to Compliance Pulse" and "Send email alert"
# controls only. Does NOT affect KB ingestion — old-but-valid
# regulatory content is still useful in the knowledge base regardless
# of age.

FRESHNESS_THRESHOLD_DAYS = 21  # adjust as needed


def compute_age_days(published_at: str | None) -> int | None:
    """Returns age in days from published_at to now, or None if missing/invalid."""
    if not published_at:
        return None
    try:
        pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - pub_dt).days
    except Exception:
        return None


def freshness_status(published_at: str | None) -> dict:
    """
    Returns {"is_fresh": bool, "age_days": int|None, "reason": str|None}

    is_fresh=False means the Pulse/alert controls should be gated
    (disabled by default, with a manual override available).
    """
    age_days = compute_age_days(published_at)
    if age_days is None:
        return {"is_fresh": False, "age_days": None, "reason": "No publish date on record"}
    if age_days > FRESHNESS_THRESHOLD_DAYS:
        return {"is_fresh": False, "age_days": age_days,
                 "reason": f"Published {age_days} days ago (over {FRESHNESS_THRESHOLD_DAYS}-day freshness threshold)"}
    return {"is_fresh": True, "age_days": age_days, "reason": None}


def _format_as_markdown(plain_text: str, title: str = "") -> str | None:
    """
    Converts plain, unformatted article text into clean Markdown —
    headers for natural sections, bold for emphasis, bullet/numbered
    lists where the content implies a list. Doesn't rewrite the
    content, just adds structure.
    """
    import os
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        st.error("MISTRAL_API_KEY not set.")
        return None

    system_prompt = (
        "You format plain article text into clean Markdown for a compliance "
        "SaaS blog. Add structure only — do not rewrite, shorten, or change "
        "the wording or meaning of the content.\n\n"
        "Rules:\n"
        "- Add a single # title at the top only if a title isn't already "
        "implied by the first line.\n"
        "- Use ## for natural section headers where the text shifts topic "
        "(don't invent headers that aren't implied by the content).\n"
        "- Use **bold** sparingly, only for genuinely emphasised terms or "
        "key figures/dates.\n"
        "- Convert clearly enumerable content (steps, lists of items) into "
        "- bullet or 1. numbered lists.\n"
        "- Preserve paragraph breaks as-is.\n"
        "- Do not add content, opinions, or a call-to-action that wasn't in "
        "the original text.\n"
        "- Return ONLY the Markdown — no preamble, no explanation, no code "
        "fences."
    )

    user_prompt = f"TITLE (for context, don't necessarily repeat as a heading): {title}\n\n{plain_text}"

    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistral-large-latest",
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 2000,
            },
            timeout=45,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        st.error(f"Could not format as Markdown: {e}")
        return None


# ── LinkedIn draft generation (defined before tabs so it's available) ─────────

def _generate_linkedin_draft(item: dict, context: str = "regulatory") -> str | None:
    """Generate a LinkedIn post draft from a regulatory or marketing item."""
    import os
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        st.error("MISTRAL_API_KEY not set.")
        return None

    if context == "regulatory":
        system_prompt = """You are a content writer for RECOSA, an EU regulatory compliance platform for SMEs.
Write a LinkedIn post about this regulatory update. Tone: expert but accessible, concise, actionable.
Format:
- Hook sentence (grab attention)
- 2-3 key takeaways for SMEs (use emojis sparingly)
- Call to action mentioning RECOSA
- 3-5 relevant hashtags

Max 250 words. Write in English."""
    else:
        system_prompt = """You are a content writer for RECOSA, an EU regulatory compliance platform for SMEs.
Write a LinkedIn post inspired by this news item, from the perspective of an EU compliance expert.
Tone: thought leadership, concise, adds RECOSA's perspective.
Format:
- Hook sentence
- 2-3 key insights
- RECOSA angle (how this relates to what we help SMEs with)
- 3-5 relevant hashtags

Max 250 words. Write in English."""

    user_prompt = f"""TITLE: {item.get('title', '')}
SUMMARY: {item.get('summary', '')}
SOURCE: {item.get('source', '')}

Write the LinkedIn post."""

    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistral-large-latest",
                "temperature": 0.7,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                "max_tokens": 500,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        st.error(f"Could not generate LinkedIn draft: {e}")
        return None


# ── Tabs ──────────────────────────────────────────────────────
tab_reg, tab_mkt, tab_sources, tab_runs = st.tabs([
    "📋 Regulatory Feed",
    "📣 Marketing Feed",
    "⚙️ Sources",
    "🕓 Run History",
])


# ═══════════════════════════════════════════════════════════════
# TAB 1 — REGULATORY FEED
# ═══════════════════════════════════════════════════════════════

with tab_reg:

    # ── Manual trigger ────────────────────────────────────────
    st.subheader("Manual trigger")
    col_btn, col_status = st.columns([1, 3])

    with col_btn:
        run_reg = st.button(
            "▶ Run Regulatory Monitoring",
            type="primary",
            use_container_width=True,
            key="run_regulatory",
        )

    if run_reg:
        import os
        api_key = os.environ.get("MISTRAL_API_KEY", "")
        if not api_key:
            st.error("MISTRAL_API_KEY not set in environment.")
        else:
            progress_box = st.empty()
            log_box      = st.empty()
            log_lines    = []

            def log(msg):
                log_lines.append(msg)
                log_box.code("\n".join(log_lines), language=None)

            with st.spinner("Running regulatory monitoring..."):
                try:
                    from monitor import run_monitoring
                    result = run_monitoring(triggered_by="manual")
                    log(f"DONE — Fetched: {result.get('fetched', 0)} | "
                        f"New: {result.get('saved', 0)} | "
                        f"Flagged: {result.get('flagged', 0)} | "
                        f"Duplicates: {result.get('skipped', 0)} | "
                        f"Errors: {result.get('errors', 0)}")
                    st.success(
                        f"Regulatory monitoring complete — "
                        f"{result.get('saved', 0)} new items saved"
                        + (f", {result.get('flagged', 0)} flagged for review"
                           if result.get('flagged') else "")
                        + "."
                    )
                    st.rerun()

                except Exception as e:
                    st.error(f"Monitor failed: {e}")

    st.divider()

    # ── Manual item entry ─────────────────────────────────────
    with st.expander("➕ Add item manually", expanded=False):
        st.caption(
            "For items the monitor didn't catch, or content you're entering "
            "by hand (e.g. a known gap in the feed). Saved as 'pending', same "
            "as monitor-detected items — goes through the normal approval flow."
        )
        with st.form("manual_reg_form", clear_on_submit=True):
            m_title = st.text_input("Title *")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                m_source = st.text_input("Source *", placeholder="e.g. CCB")
                m_url = st.text_input("Source URL", placeholder="https://...")
                m_lang = st.selectbox("Language", ["en", "fr", "nl"])
            with col_m2:
                m_severity = st.selectbox("Severity", ["info", "important", "urgent"])
                m_regs_raw = st.text_input("Regulations (comma-separated)",
                                            placeholder="e.g. GDPR, NIS2")
                m_countries_raw = st.text_input("Countries (comma-separated)",
                                                 placeholder="e.g. EU, BE")
            m_summary = st.text_area("Summary *", height=100)
            m_action_required = st.checkbox("Action required")
            m_action_desc = st.text_input("Action description", disabled=not m_action_required)
            m_published_date = st.date_input("Published date", value=datetime.now())

            m_submitted = st.form_submit_button("➕ Add item", type="primary")
            if m_submitted:
                if not m_title.strip() or not m_source.strip() or not m_summary.strip():
                    st.error("Title, source, and summary are required.")
                else:
                    regs = [r.strip() for r in m_regs_raw.split(",") if r.strip()]
                    countries = [c.strip() for c in m_countries_raw.split(",") if c.strip()]
                    manual_item = {
                        "source":             m_source.strip(),
                        "title":              m_title.strip(),
                        "summary":            m_summary.strip(),
                        "url":                m_url.strip() or None,
                        "regulations":        regs,
                        "countries":          countries or ["EU"],
                        "severity":           m_severity,
                        "action_required":    m_action_required,
                        "action_description": m_action_desc.strip() if m_action_required else "",
                        "language":           m_lang,
                        "published_at":       datetime.combine(
                                                   m_published_date, datetime.min.time()
                                               ).isoformat(),
                        "status":             "pending",
                    }
                    from database import save_regulatory_update
                    result = save_regulatory_update(manual_item)
                    if result:
                        st.success(f"Added — review it below in the pending queue.")
                        st.rerun()
                    else:
                        st.error("Could not add item (may be a duplicate URL, or a save error).")

    # ── Review queue ──────────────────────────────────────────
    st.subheader("Pending regulatory updates")

    status_filter = st.selectbox(
        "Filter by status",
        ["pending", "url_flagged", "approved", "rejected", "all"],
        index=0,
        key="reg_status_filter",
    )

    updates = load_regulatory_updates(
        status=None if status_filter == "all" else status_filter
    )

    if not updates:
        st.info("No regulatory updates found.")
    else:
        st.caption(f"{len(updates)} items")
        for u in updates:
            severity_icon = {"urgent": "🔴", "important": "🟡", "info": "🔵"}.get(u.get("severity", "info"), "🔵")
            status_icon   = {"pending": "⏳", "url_flagged": "⚠️", "approved": "✅", "rejected": "❌"}.get(u.get("status", "pending"), "⏳")

            with st.expander(
                f"{severity_icon} {status_icon} {u.get('title', 'Untitled')} — {u.get('source', '')}",
                expanded=False
            ):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**Summary:** {u.get('summary', '—')}")
                    regs = ", ".join(u.get("regulations") or [])
                    countries = ", ".join(u.get("countries") or [])
                    lang = u.get("language", "en")
                    st.caption(f"Regulations: {regs} · Countries: {countries} · Language: {lang}")
                    if u.get("action_required"):
                        st.warning(f"⚡ Action required: {u.get('action_description', '')}")
                    if u.get("status") == "url_flagged":
                        st.error(f"⚠️ URL issue: {u.get('url_check_reason', 'unknown reason')}")
                    if u.get("url"):
                        st.markdown(f"[🔗 Source]({u['url']})")
                    detected = u.get("detected_at", "")[:10] if u.get("detected_at") else "—"
                    st.caption(f"Detected: {detected}")

                with col_b:
                    if u.get("status") in ("pending", "url_flagged"):
                        if u.get("status") == "url_flagged":
                            st.error(f"⚠️ URL issue: {u.get('url_check_reason', 'unknown reason')}")

                        current_url = u.get("url") or ""
                        edited_url = st.text_input(
                            "Source URL (edit or clear to publish without a source link)",
                            value=current_url,
                            key=f"fix_url_{u['id']}",
                        )

                        severity_choice = st.selectbox(
                            "Severity",
                            ["info", "important", "urgent"],
                            index=["info", "important", "urgent"].index(u.get("severity", "info")),
                            key=f"sev_{u['id']}",
                        )

                        fresh = freshness_status(u.get("published_at"))
                        if not fresh["is_fresh"]:
                            st.warning(f"⚠️ {fresh['reason']} — Pulse/alert options disabled below.")
                            override = st.checkbox(
                                "Publish/alert anyway (override freshness check)",
                                key=f"override_{u['id']}",
                            )
                        else:
                            override = True

                        controls_enabled = fresh["is_fresh"] or override

                        send_email = st.checkbox(
                            "Send email alert", key=f"email_{u['id']}",
                            disabled=not controls_enabled,
                        )
                        publish_pulse = st.checkbox(
                            "Publish to Compliance Pulse", key=f"pulse_{u['id']}",
                            disabled=not controls_enabled,
                        )

                        col_approve, col_reject = st.columns(2)
                        with col_approve:
                            if st.button("✅ Approve", key=f"approve_{u['id']}", use_container_width=True):
                                user_id = st.session_state.get("user_id", "admin")

                                new_url = edited_url.strip()
                                if new_url != current_url:
                                    get_supabase_admin().table("regulatory_updates").update(
                                        {"url": new_url or None}
                                    ).eq("id", u["id"]).execute()
                                if u.get("status") == "url_flagged":
                                    get_supabase_admin().table("regulatory_updates").update(
                                        {"status": "pending"}
                                    ).eq("id", u["id"]).execute()

                                approve_regulatory_update(u["id"], user_id, severity_choice, send_email and controls_enabled)
                                if publish_pulse and controls_enabled:
                                    get_supabase_admin().table("regulatory_updates").update(
                                        {"published_to_pulse": True}
                                    ).eq("id", u["id"]).execute()
                                create_client_alerts(u["id"], u)
                                # Ingest to Qdrant — always happens regardless of
                                # freshness, since old-but-valid content is still
                                # useful in the knowledge base
                                result = ingest_alert_to_qdrant(u)
                                if result.get("success"):
                                    mark_alert_ingested(u["id"], result["chunks_ingested"])
                                st.rerun()
                        with col_reject:
                            if st.button("❌ Reject", key=f"reject_{u['id']}", use_container_width=True):
                                reject_regulatory_update(u["id"])
                                st.rerun()

                    elif u.get("status") == "approved":
                        st.success("Approved")
                        kb = "✅" if u.get("kb_ingested") else "⏳"
                        st.caption(f"KB ingested: {kb}")

                        # ── Publish-to-Pulse edit/unpublish toggle ──────
                        current_pulse = u.get("published_to_pulse", False)
                        new_pulse = st.checkbox(
                            "Published to Compliance Pulse",
                            value=current_pulse,
                            key=f"pulse_edit_{u['id']}",
                        )
                        if new_pulse != current_pulse:
                            if st.button(
                                "💾 Update Pulse status",
                                key=f"pulse_save_{u['id']}",
                                use_container_width=True,
                            ):
                                get_supabase_admin().table("regulatory_updates").update(
                                    {"published_to_pulse": new_pulse}
                                ).eq("id", u["id"]).execute()
                                st.success(
                                    "Published to Pulse." if new_pulse else "Unpublished from Pulse."
                                )
                                st.rerun()

                        # LinkedIn draft generation
                        draft_key = f"li_draft_{u['id']}"
                        if not u.get("linkedin_draft") and draft_key not in st.session_state:
                            if st.button("✍️ Generate LinkedIn draft", key=f"li_{u['id']}", use_container_width=True):
                                with st.spinner("Generating..."):
                                    draft = _generate_linkedin_draft(u)
                                    if draft:
                                        save_linkedin_draft(u["id"], draft, table="regulatory_updates")
                                        st.session_state[draft_key] = draft
                        
                        shown_draft = st.session_state.get(draft_key) or u.get("linkedin_draft")
                        if shown_draft:
                            st.text_area("LinkedIn draft", value=shown_draft,
                                         height=150, key=f"li_text_{u['id']}")
                            st.caption("Copy and paste into LinkedIn.")

                    else:
                        st.error("Rejected")


# ═══════════════════════════════════════════════════════════════
# TAB 2 — MARKETING FEED
# ═══════════════════════════════════════════════════════════════

with tab_mkt:

    # ── Manual trigger ────────────────────────────────────────
    st.subheader("Manual trigger")
    col_btn2, col_status2 = st.columns([1, 3])

    with col_btn2:
        run_mkt = st.button(
            "▶ Run Marketing Monitoring",
            type="primary",
            use_container_width=True,
            key="run_marketing",
        )

    if run_mkt:
        with st.spinner("Running marketing monitoring — this may take a minute..."):
            try:
                from monitor_marketing import run_marketing_monitoring
                result = run_marketing_monitoring(triggered_by="manual")
                st.success(
                    f"Marketing monitoring complete — "
                    f"{result.get('saved', 0)} new items saved"
                    + (f", {result.get('flagged', 0)} flagged for review"
                       if result.get('flagged') else "")
                    + f", {result.get('skipped', 0)} duplicates."
                )
                st.rerun()
            except Exception as e:
                st.error(f"Monitor failed: {e}")

    st.divider()

    # ── Manual item entry ─────────────────────────────────────
    with st.expander("➕ Add article/item manually", expanded=False):
        st.caption(
            "For RECOSA-authored articles/opinion pieces, or third-party items "
            "the monitor didn't catch. Saved as 'pending' — goes through the "
            "normal approval flow, including the Publish-to-Pulse checkbox."
        )

        m2_title = st.text_input("Title *", key="m2_title")

        # Auto-suggest the slug into the widget's OWN session-state key
        # (m2_slug_input) before it's created — writing to a separate key
        # doesn't work once a widget has been rendered, since the widget's
        # displayed value is then controlled solely by its own key.
        if m2_title and not st.session_state.get("m2_slug_input"):
            st.session_state["m2_slug_input"] = slugify(m2_title)

        col_m2a, col_m2b = st.columns(2)
        with col_m2a:
            m2_source = st.text_input("Source *", value="RECOSA",
                                        help="Use 'RECOSA' for your own authored pieces.",
                                        key="m2_source")
            m2_category = st.text_input("Category", placeholder="e.g. GDPR, NIS2, EU AI Act",
                                          key="m2_category")
            m2_lang = st.selectbox("Language", ["en", "fr", "nl"], key="m2_lang")
        with col_m2b:
            m2_severity = st.selectbox("Severity", ["info", "important", "urgent"], key="m2_severity")
            m2_url = st.text_input("External source URL (leave blank for RECOSA-authored pieces)",
                                     key="m2_url")
            m2_published_date = st.date_input("Published date", value=datetime.now(), key="m2_pubdate")

        m2_summary = st.text_area("Card summary (2-3 sentences) *", height=80, key="m2_summary")

        st.markdown("**Full article (optional)** — fills the detail page at recosa.eu/pulse/{slug}")
        col_m2c, col_m2d = st.columns([4, 1])
        with col_m2c:
            m2_slug = st.text_input(
                "URL slug", key="m2_slug_input",
                help="Auto-suggested from the title above — edit freely.",
            )
        with col_m2d:
            st.write("")  # vertical spacer to align button with input
            if st.button("↻ Regenerate", key="m2_regen_slug"):
                st.session_state["m2_slug_input"] = slugify(m2_title)
                st.rerun()
        m2_body_plain = st.text_area(
            "Article body — write normally, no formatting needed",
            height=180, key="m2_body_plain",
            placeholder="Just write it like an email or a normal document. "
                        "Click 'Format as Markdown' below to add headers, "
                        "bold, and lists automatically.",
        )

        if st.button("✨ Format as Markdown", key="m2_format_btn"):
            if not m2_body_plain.strip():
                st.warning("Write the article text above first.")
            else:
                with st.spinner("Formatting..."):
                    formatted = _format_as_markdown(m2_body_plain, m2_title)
                    if formatted:
                        st.session_state["m2_body_md_edit"] = formatted

        if st.session_state.get("m2_body_md_edit"):
            st.markdown("**Formatted Markdown** — review and edit before saving")
            m2_body = st.text_area(
                "Formatted Markdown", height=220, key="m2_body_md_edit",
                label_visibility="collapsed",
            )
        else:
            m2_body = ""

        if st.button("➕ Add article/item", type="primary", key="m2_submit"):
            if not m2_title.strip() or not m2_source.strip() or not m2_summary.strip():
                st.error("Title, source, and card summary are required.")
            else:
                final_slug = m2_slug.strip() or None
                slug_ok = True
                if final_slug:
                    existing = get_supabase_admin().table("marketing_updates") \
                        .select("id").eq("slug", final_slug).execute()
                    if existing.data:
                        slug_ok = False
                        st.error(f"Slug '{final_slug}' is already in use.")

                if slug_ok:
                    manual_item = {
                        "source":       m2_source.strip(),
                        "title":        m2_title.strip(),
                        "summary":      m2_summary.strip(),
                        "url":          m2_url.strip() or None,
                        "category":     m2_category.strip() or "Policy",
                        "severity":     m2_severity,
                        "language":     m2_lang,
                        "body_content": m2_body.strip() or None,
                        "slug":         final_slug,
                        "published_at": datetime.combine(
                                             m2_published_date, datetime.min.time()
                                         ).isoformat(),
                        "status":       "pending",
                    }
                    result = save_marketing_update(manual_item)
                    if result:
                        st.success("Added — review it below in the pending queue.")
                        st.session_state["m2_slug_input"] = ""
                        st.session_state["m2_body_plain"] = ""
                        st.session_state["m2_body_md_edit"] = ""
                        st.rerun()
                    else:
                        st.error("Could not add item (may be a duplicate URL, or a save error).")

    # ── Marketing review feed ─────────────────────────────────
    st.subheader("Pending marketing items")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        mkt_status = st.selectbox(
            "Filter by status",
            ["pending", "url_flagged", "approved", "rejected", "all"],
            index=0,
            key="mkt_status_filter",
        )
    with col_f2:
        # Get unique categories from sources
        mkt_sources = load_monitoring_sources(monitor_type="marketing")
        categories = ["all"] + sorted(set(s.get("category", "") for s in mkt_sources if s.get("category")))
        mkt_category = st.selectbox("Filter by category", categories, key="mkt_cat_filter")

    mkt_updates = load_marketing_updates(
        status=None if mkt_status == "all" else mkt_status,
        category=None if mkt_category == "all" else mkt_category,
    )

    if not mkt_updates:
        st.info("No marketing updates found.")
    else:
        st.caption(f"{len(mkt_updates)} items")
        for u in mkt_updates:
            severity_icon = {"urgent": "🔴", "important": "🟡", "info": "🔵"}.get(u.get("severity", "info"), "🔵")
            status_icon   = {"pending": "⏳", "url_flagged": "⚠️", "approved": "✅", "rejected": "❌"}.get(u.get("status", "pending"), "⏳")
            cat_badge     = f"[{u.get('category', '')}] " if u.get("category") else ""

            with st.expander(
                f"{severity_icon} {status_icon} {cat_badge}{u.get('title', 'Untitled')} — {u.get('source', '')}",
                expanded=False,
            ):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**Summary:** {u.get('summary', '—')}")
                    if u.get("relevance_reason"):
                        st.caption(f"💡 Relevance: {u['relevance_reason']}")
                    lang = u.get("language", "en")
                    st.caption(f"Language: {lang}")
                    if u.get("status") == "url_flagged":
                        st.error(f"⚠️ URL issue: {u.get('url_check_reason', 'unknown reason')}")
                    if u.get("url"):
                        st.markdown(f"[🔗 Source]({u['url']})")
                    created = u.get("created_at", "")[:10] if u.get("created_at") else "—"
                    st.caption(f"Detected: {created}")

                with col_b:
                    if u.get("status") in ("pending", "url_flagged"):
                        if u.get("status") == "url_flagged":
                            st.error(f"⚠️ URL issue: {u.get('url_check_reason', 'unknown reason')}")

                        mkt_current_url = u.get("url") or ""
                        mkt_edited_url = st.text_input(
                            "Source URL (edit or clear to publish without a source link)",
                            value=mkt_current_url,
                            key=f"mkt_fix_url_{u['id']}",
                        )

                        fresh = freshness_status(u.get("published_at") or u.get("created_at"))
                        if not fresh["is_fresh"]:
                            st.warning(f"⚠️ {fresh['reason']} — Pulse publishing disabled below.")
                            mkt_override = st.checkbox(
                                "Publish anyway (override freshness check)",
                                key=f"mkt_override_{u['id']}",
                            )
                        else:
                            mkt_override = True

                        mkt_controls_enabled = fresh["is_fresh"] or mkt_override

                        publish_pulse = st.checkbox(
                            "Publish to Compliance Pulse", key=f"mkt_pulse_{u['id']}",
                            disabled=not mkt_controls_enabled,
                        )

                        col_a2, col_r2 = st.columns(2)
                        with col_a2:
                            if st.button("✅ Approve", key=f"mkt_approve_{u['id']}", use_container_width=True):
                                mkt_new_url = mkt_edited_url.strip()
                                if mkt_new_url != mkt_current_url:
                                    get_supabase_admin().table("marketing_updates").update(
                                        {"url": mkt_new_url or None}
                                    ).eq("id", u["id"]).execute()
                                if u.get("status") == "url_flagged":
                                    get_supabase_admin().table("marketing_updates").update(
                                        {"status": "pending"}
                                    ).eq("id", u["id"]).execute()

                                approve_marketing_update(
                                    u["id"],
                                    publish_to_pulse=publish_pulse and mkt_controls_enabled,
                                )
                                st.rerun()
                        with col_r2:
                            if st.button("❌ Reject", key=f"mkt_reject_{u['id']}", use_container_width=True):
                                reject_marketing_update(u["id"])
                                st.rerun()

                    elif u.get("status") == "approved":
                        st.success("Approved")

                        # ── Publish-to-Pulse edit/unpublish toggle ──────
                        mkt_current_pulse = u.get("published_to_pulse", False)
                        mkt_new_pulse = st.checkbox(
                            "Published to Compliance Pulse",
                            value=mkt_current_pulse,
                            key=f"mkt_pulse_edit_{u['id']}",
                        )
                        if mkt_new_pulse != mkt_current_pulse:
                            if st.button(
                                "💾 Update Pulse status",
                                key=f"mkt_pulse_save_{u['id']}",
                                use_container_width=True,
                            ):
                                get_supabase_admin().table("marketing_updates").update(
                                    {"published_to_pulse": mkt_new_pulse}
                                ).eq("id", u["id"]).execute()
                                st.success(
                                    "Published to Pulse." if mkt_new_pulse else "Unpublished from Pulse."
                                )
                                st.rerun()

                        st.divider()

                        # ── Article detail-page fields ──────────────────
                        # Only relevant for RECOSA-authored pieces that
                        # should get their own /pulse/{slug} page rather
                        # than just a card teaser with a dead "Read more".
                        st.markdown("**Full article (optional)**")
                        st.caption(
                            "Fill in to give this item its own detail page at "
                            "recosa.eu/pulse/{slug}. Leave blank to keep it as a "
                            "card-only teaser with no 'Read more' link."
                        )

                        slug_state_key = f"mkt_slug_suggested_{u['id']}"
                        if slug_state_key not in st.session_state:
                            st.session_state[slug_state_key] = u.get("slug") or slugify(u.get("title", ""))

                        edited_slug = st.text_input(
                            "URL slug",
                            value=st.session_state[slug_state_key],
                            key=f"mkt_slug_input_{u['id']}",
                            help="Used in the article URL: recosa.eu/pulse/{slug}",
                        )
                        if st.button("↻ Regenerate slug from title", key=f"mkt_regen_slug_{u['id']}"):
                            st.session_state[slug_state_key] = slugify(u.get("title", ""))
                            st.rerun()

                        edited_body = st.text_area(
                            "Article body (Markdown)",
                            value=u.get("body_content") or "",
                            height=200,
                            key=f"mkt_body_{u['id']}",
                        )

                        edited_lang = st.selectbox(
                            "Language",
                            ["en", "fr", "nl"],
                            index=["en", "fr", "nl"].index(u.get("language", "en")),
                            key=f"mkt_lang_{u['id']}",
                        )

                        if st.button("💾 Save article content", key=f"mkt_save_article_{u['id']}"):
                            final_slug = edited_slug.strip() or None
                            save_fields = {
                                "body_content": edited_body.strip() or None,
                                "language": edited_lang,
                            }
                            if final_slug:
                                # Check uniqueness (excluding this item itself)
                                existing = get_supabase_admin().table("marketing_updates") \
                                    .select("id").eq("slug", final_slug).execute()
                                conflict = any(row["id"] != u["id"] for row in (existing.data or []))
                                if conflict:
                                    st.error(f"Slug '{final_slug}' is already in use by another item.")
                                else:
                                    save_fields["slug"] = final_slug
                                    get_supabase_admin().table("marketing_updates").update(
                                        save_fields
                                    ).eq("id", u["id"]).execute()
                                    st.success("Article content saved.")
                                    st.rerun()
                            else:
                                get_supabase_admin().table("marketing_updates").update(
                                    save_fields
                                ).eq("id", u["id"]).execute()
                                st.success("Article content saved.")
                                st.rerun()

                        st.divider()

                        # LinkedIn draft
                        mkt_draft_key = f"mkt_li_draft_{u['id']}"
                        if not u.get("linkedin_draft") and mkt_draft_key not in st.session_state:
                            if st.button("✍️ Generate LinkedIn draft", key=f"mkt_li_{u['id']}", use_container_width=True):
                                with st.spinner("Generating..."):
                                    draft = _generate_linkedin_draft(u, context="marketing")
                                    if draft:
                                        save_linkedin_draft(u["id"], draft, table="marketing_updates")
                                        st.session_state[mkt_draft_key] = draft

                        mkt_shown_draft = st.session_state.get(mkt_draft_key) or u.get("linkedin_draft")
                        if mkt_shown_draft:
                            st.text_area("LinkedIn draft", value=mkt_shown_draft,
                                         height=150, key=f"mkt_li_text_{u['id']}")
                            st.caption("Copy and paste into LinkedIn.")
                    else:
                        st.error("Rejected")


# ═══════════════════════════════════════════════════════════════
# TAB 3 — SOURCES
# ═══════════════════════════════════════════════════════════════

with tab_sources:
    st.subheader("Monitoring sources")
    st.caption("Add, remove, or toggle sources for regulatory and marketing monitoring. Changes take effect on the next run.")

    source_type_tab = st.radio(
        "Show",
        ["Regulatory", "Marketing"],
        horizontal=True,
        key="source_type_tab",
    )
    monitor_type_key = "regulatory" if source_type_tab == "Regulatory" else "marketing"

    sources = load_monitoring_sources(monitor_type=monitor_type_key)

    # ── Existing sources ──────────────────────────────────────
    if not sources:
        st.info(f"No {source_type_tab.lower()} sources configured yet.")
    else:
        for s in sources:
            col_name, col_type, col_cat, col_toggle, col_del = st.columns([3, 1, 1, 1, 1])
            with col_name:
                st.markdown(f"**{s['name']}**")
                st.caption(s["url"])
            with col_type:
                st.caption(s.get("fetch_type", "rss").upper())
            with col_cat:
                st.caption(s.get("category", "—"))
            with col_toggle:
                active = s.get("active", True)
                label  = "🟢 Active" if active else "⚫ Off"
                if st.button(label, key=f"toggle_{s['id']}", use_container_width=True):
                    update_monitoring_source(s["id"], {"active": not active})
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"del_{s['id']}", use_container_width=True, help="Delete source"):
                    delete_monitoring_source(s["id"])
                    st.rerun()

    st.divider()

    # ── Add new source ────────────────────────────────────────
    st.subheader("Add new source")
    with st.form("add_source_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Name *", placeholder="e.g. Euractiv Tech")
            new_url  = st.text_input("URL *", placeholder="https://...")
            new_cat  = st.text_input("Category", placeholder="e.g. Policy, Press, Competition")
        with col2:
            new_fetch_type    = st.selectbox("Fetch type", ["search", "rss", "scrape"])
            new_monitor_type  = st.selectbox("Monitor type", ["regulatory", "marketing"],
                                              index=0 if monitor_type_key == "regulatory" else 1)
            if new_fetch_type == "search":
                new_query = st.text_input("Search query *",
                                           placeholder="e.g. GDPR enforcement fine Belgium 2026")
                new_keywords_raw  = ""
            else:
                new_query         = ""
                new_keywords_raw  = st.text_input("Filter keywords (comma-separated)",
                                                   placeholder="e.g. GDPR, NIS2, compliance")
            if new_monitor_type == "regulatory":
                new_regs_raw  = st.text_input("Regulations (comma-separated)",
                                               placeholder="e.g. GDPR, NIS2, EU_AI_ACT")
                new_countries_raw = st.text_input("Countries (comma-separated)",
                                                   placeholder="e.g. EU, BE, FR")
            else:
                new_regs_raw      = ""
                new_countries_raw = ""

        submitted = st.form_submit_button("➕ Add source", type="primary")
        if submitted:
            if not new_name:
                st.error("Name is required.")
            elif new_fetch_type == "search" and not new_query.strip():
                st.error("Search query is required for search-type sources.")
            elif new_fetch_type in ("rss", "scrape") and not new_url.strip():
                st.error("URL is required for RSS and scrape sources.")
            else:
                keywords  = [k.strip() for k in new_keywords_raw.split(",") if k.strip()]
                regs      = [r.strip() for r in new_regs_raw.split(",") if r.strip()]
                countries = [c.strip() for c in new_countries_raw.split(",") if c.strip()]
                result = save_monitoring_source({
                    "name":            new_name.strip(),
                    "url":             new_url.strip() if new_url.strip() else None,
                    "fetch_type":      new_fetch_type,
                    "monitor_type":    new_monitor_type,
                    "category":        new_cat.strip(),
                    "query":           new_query.strip() if new_query.strip() else None,
                    "filter_keywords": keywords,
                    "regulations":     regs,
                    "countries":       countries,
                    "active":          True,
                })
                if result:
                    st.success(f"Source '{new_name}' added.")
                    st.rerun()
                else:
                    st.error("Could not add source. Check the URL and try again.")


# ═══════════════════════════════════════════════════════════════
# TAB 4 — RUN HISTORY
# ═══════════════════════════════════════════════════════════════

with tab_runs:
    st.subheader("Run history")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        run_type_filter = st.selectbox(
            "Monitor type",
            ["all", "regulatory", "marketing"],
            key="run_type_filter",
        )
    with col_r2:
        if st.button("🔄 Refresh", key="refresh_runs"):
            st.rerun()

    runs = load_monitor_runs(
        monitor_type=None if run_type_filter == "all" else run_type_filter,
        limit=30,
    )

    if not runs:
        st.info("No runs recorded yet.")
    else:
        for run in runs:
            status_icon = {"completed": "✅", "running": "⏳", "failed": "❌"}.get(run.get("status", ""), "❓")
            trigger_icon = "🤖" if run.get("triggered_by") == "cron" else "👤"
            try:
                from zoneinfo import ZoneInfo
                from datetime import datetime as _dt
                raw_ts = run.get("started_at", "")
                if raw_ts:
                    utc_dt = _dt.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    started = utc_dt.astimezone(ZoneInfo("Europe/Brussels")).strftime("%Y-%m-%d %H:%M")
                else:
                    started = "—"
            except Exception:
                started = run.get("started_at", "")[:16].replace("T", " ") if run.get("started_at") else "—"
            duration = f"{run.get('duration_seconds', 0)}s" if run.get("duration_seconds") else "—"
            monitor_label = run.get("monitor_type", "").capitalize()

            with st.expander(
                f"{status_icon} {trigger_icon} {monitor_label} — {started} ({duration})",
                expanded=False,
            ):
                source_stats = run.get("source_stats") or []
                flagged_total = sum(stat.get("flagged", 0) for stat in source_stats)

                col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
                col_s1.metric("Fetched",    run.get("total_fetched", 0))
                col_s2.metric("Saved",      run.get("total_saved", 0))
                col_s3.metric("Flagged",    flagged_total)
                col_s4.metric("Duplicates", run.get("total_skipped", 0))
                col_s5.metric("Errors",     run.get("total_errors", 0))

                token_usage = run.get("token_usage") or {}
                if token_usage:
                    st.caption(
                        f"Tokens: {token_usage.get('input', 0)} in / "
                        f"{token_usage.get('output', 0)} out — "
                        f"${token_usage.get('cost_usd', 0):.4f}"
                    )

                if run.get("error_message"):
                    st.error(run["error_message"])

                if source_stats:
                    st.markdown("**Per-source breakdown:**")
                    for stat in source_stats:
                        fetched = stat.get("fetched", 0)
                        saved   = stat.get("saved", 0)
                        skipped = stat.get("skipped", 0)
                        flagged = stat.get("flagged", 0)
                        error   = stat.get("error")

                        flagged_suffix = f" / {flagged} flagged ⚠️" if flagged else ""

                        if error:
                            icon = "🔴"
                            detail = f"error: {error[:60]}"
                        elif saved > 0 or flagged > 0:
                            icon = "🟢"
                            detail = f"{fetched} fetched / {saved} new / {skipped} duplicates{flagged_suffix}"
                        elif fetched > 0:
                            icon = "🟡"
                            detail = f"{fetched} fetched / 0 new (all duplicates)"
                        else:
                            icon = "🔴"
                            detail = "0 fetched"

                        st.caption(f"{icon} {stat['name']}: {detail}")
