import time
import json
import requests
import streamlit as st
from datetime import datetime

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

st.title("📡 Monitoring")
st.caption("Regulatory and marketing monitoring — review, approve, and publish.")

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
                    # Import here to avoid circular issues at module level
                    from monitor import run_monitoring
                    # Capture stdout by running inline with live logging

                    sources = load_monitoring_sources(monitor_type="regulatory")
                    log(f"Loaded {len(sources)} active regulatory sources.")

                    from monitor import (
                        parse_rss, parse_scrape,
                        summarise_and_categorise,
                    )
                    from database import (
                        save_regulatory_update,
                        log_token_usage,
                        start_monitor_run,
                        complete_monitor_run,
                    )

                    SYSTEM_UUID = "00000000-0000-0000-0000-000000000000"
                    run_id = start_monitor_run("regulatory", triggered_by="manual")

                    total_fetched = total_saved = total_skipped = total_errors = 0
                    total_in = total_out = 0
                    source_stats = []

                    for source in sources:
                        log(f"\nFetching {source['name']}...")
                        stat = {"name": source["name"], "fetched": 0, "saved": 0, "skipped": 0, "error": None}
                        try:
                            if source.get("fetch_type") == "scrape":
                                items = parse_scrape(source["url"], source)
                            else:
                                items = parse_rss(source["url"], source)

                            log(f"  {len(items)} items fetched")
                            stat["fetched"] = len(items)
                            total_fetched += len(items)

                            if items:
                                enriched, inp, out = summarise_and_categorise(items, source, api_key)
                                total_in += inp; total_out += out
                                log(f"  {len(enriched)} relevant after analysis")
                                for item in enriched:
                                    res = save_regulatory_update(item)
                                    if res:
                                        total_saved += 1; stat["saved"] += 1
                                        log(f"  ✅ {item['title'][:55]}")
                                    else:
                                        total_skipped += 1; stat["skipped"] += 1
                                        log(f"  ⤷ Duplicate: {item['title'][:55]}")
                        except Exception as e:
                            stat["error"] = str(e)
                            total_errors += 1
                            log(f"  ❌ Error: {e}")

                        source_stats.append(stat)

                    if total_in + total_out > 0:
                        log_token_usage(
                            user_id=SYSTEM_UUID,
                            feature="monitoring_summarise",
                            input_tokens=total_in,
                            output_tokens=total_out,
                        )

                    token_usage = {
                        "input": total_in, "output": total_out,
                        "cost_usd": round((total_in/1_000_000)*2.00 + (total_out/1_000_000)*6.00, 6),
                    }

                    if run_id:
                        complete_monitor_run(
                            run_id, total_fetched, total_saved,
                            total_skipped, total_errors,
                            source_stats, token_usage,
                        )

                    log(f"\n{'='*50}")
                    log(f"DONE — Fetched: {total_fetched} | New: {total_saved} | "
                        f"Duplicates: {total_skipped} | Errors: {total_errors}")
                    log(f"Tokens: {total_in} in / {total_out} out — ${token_usage['cost_usd']:.4f}")
                    st.success(f"Regulatory monitoring complete — {total_saved} new items saved.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Monitor failed: {e}")

    st.divider()

    # ── Review queue ──────────────────────────────────────────
    st.subheader("Pending regulatory updates")

    status_filter = st.selectbox(
        "Filter by status",
        ["pending", "approved", "rejected", "all"],
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
            status_icon   = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(u.get("status", "pending"), "⏳")

            with st.expander(
                f"{severity_icon} {status_icon} {u.get('title', 'Untitled')} — {u.get('source', '')}",
                expanded=False
            ):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**Summary:** {u.get('summary', '—')}")
                    regs = ", ".join(u.get("regulations") or [])
                    countries = ", ".join(u.get("countries") or [])
                    st.caption(f"Regulations: {regs} · Countries: {countries}")
                    if u.get("action_required"):
                        st.warning(f"⚡ Action required: {u.get('action_description', '')}")
                    if u.get("url"):
                        st.markdown(f"[🔗 Source]({u['url']})")
                    detected = u.get("detected_at", "")[:10] if u.get("detected_at") else "—"
                    st.caption(f"Detected: {detected}")

                with col_b:
                    if u.get("status") == "pending":
                        severity_choice = st.selectbox(
                            "Severity",
                            ["info", "important", "urgent"],
                            index=["info", "important", "urgent"].index(u.get("severity", "info")),
                            key=f"sev_{u['id']}",
                        )
                        send_email = st.checkbox("Send email alert", key=f"email_{u['id']}")
                        publish_pulse = st.checkbox("Publish to Compliance Pulse", key=f"pulse_{u['id']}")

                        col_approve, col_reject = st.columns(2)
                        with col_approve:
                            if st.button("✅ Approve", key=f"approve_{u['id']}", use_container_width=True):
                                user_id = st.session_state.get("user_id", "admin")
                                approve_regulatory_update(u["id"], user_id, severity_choice, send_email)
                                if publish_pulse:
                                    get_supabase_admin().table("regulatory_updates").update(
                                        {"published_to_pulse": True}
                                    ).eq("id", u["id"]).execute()
                                create_client_alerts(u["id"], u)
                                # Ingest to Qdrant
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
                        pulse = "✅" if u.get("published_to_pulse") else "—"
                        st.caption(f"Compliance Pulse: {pulse}")

                        # LinkedIn draft generation
                        if not u.get("linkedin_draft"):
                            if st.button("✍️ Generate LinkedIn draft", key=f"li_{u['id']}", use_container_width=True):
                                with st.spinner("Generating..."):
                                    draft = _generate_linkedin_draft(u)
                                    if draft:
                                        save_linkedin_draft(u["id"], draft, table="regulatory_updates")
                                        st.rerun()
                        else:
                            st.text_area("LinkedIn draft", value=u["linkedin_draft"],
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
                    f"{result.get('saved', 0)} new items saved, "
                    f"{result.get('skipped', 0)} duplicates."
                )
                st.rerun()
            except Exception as e:
                st.error(f"Monitor failed: {e}")

    st.divider()

    # ── Marketing review feed ─────────────────────────────────
    st.subheader("Pending marketing items")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        mkt_status = st.selectbox(
            "Filter by status",
            ["pending", "approved", "rejected", "all"],
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
            status_icon   = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(u.get("status", "pending"), "⏳")
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
                    if u.get("url"):
                        st.markdown(f"[🔗 Source]({u['url']})")
                    created = u.get("created_at", "")[:10] if u.get("created_at") else "—"
                    st.caption(f"Detected: {created}")

                with col_b:
                    if u.get("status") == "pending":
                        publish_pulse = st.checkbox("Publish to Compliance Pulse", key=f"mkt_pulse_{u['id']}")
                        col_a2, col_r2 = st.columns(2)
                        with col_a2:
                            if st.button("✅ Approve", key=f"mkt_approve_{u['id']}", use_container_width=True):
                                approve_marketing_update(u["id"], publish_to_pulse=publish_pulse)
                                st.rerun()
                        with col_r2:
                            if st.button("❌ Reject", key=f"mkt_reject_{u['id']}", use_container_width=True):
                                reject_marketing_update(u["id"])
                                st.rerun()

                    elif u.get("status") == "approved":
                        st.success("Approved")
                        pulse = "✅" if u.get("published_to_pulse") else "—"
                        st.caption(f"Compliance Pulse: {pulse}")

                        # LinkedIn draft
                        if not u.get("linkedin_draft"):
                            if st.button("✍️ Generate LinkedIn draft", key=f"mkt_li_{u['id']}", use_container_width=True):
                                with st.spinner("Generating..."):
                                    draft = _generate_linkedin_draft(u, context="marketing")
                                    if draft:
                                        save_linkedin_draft(u["id"], draft, table="marketing_updates")
                                        st.rerun()
                        else:
                            st.text_area("LinkedIn draft", value=u["linkedin_draft"],
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
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric("Fetched",    run.get("total_fetched", 0))
                col_s2.metric("Saved",      run.get("total_saved", 0))
                col_s3.metric("Duplicates", run.get("total_skipped", 0))
                col_s4.metric("Errors",     run.get("total_errors", 0))

                token_usage = run.get("token_usage") or {}
                if token_usage:
                    st.caption(
                        f"Tokens: {token_usage.get('input', 0)} in / "
                        f"{token_usage.get('output', 0)} out — "
                        f"${token_usage.get('cost_usd', 0):.4f}"
                    )

                if run.get("error_message"):
                    st.error(run["error_message"])

                source_stats = run.get("source_stats") or []
                if source_stats:
                    st.markdown("**Per-source breakdown:**")
                    for stat in source_stats:
                        fetched = stat.get("fetched", 0)
                        saved   = stat.get("saved", 0)
                        skipped = stat.get("skipped", 0)
                        error   = stat.get("error")

                        if error:
                            icon = "🔴"
                            detail = f"error: {error[:60]}"
                        elif saved > 0:
                            icon = "🟢"
                            detail = f"{fetched} fetched / {saved} new / {skipped} duplicates"
                        elif fetched > 0:
                            icon = "🟡"
                            detail = f"{fetched} fetched / 0 new (all duplicates)"
                        else:
                            icon = "🔴"
                            detail = "0 fetched"

                        st.caption(f"{icon} {stat['name']}: {detail}")


# ═══════════════════════════════════════════════════════════════
# SHARED HELPER — LinkedIn draft generation
# ═══════════════════════════════════════════════════════════════

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
