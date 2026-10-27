"""
pages_admin/templates.py — document template viewer (S25).

READ-ONLY BY DESIGN. There is no edit path here and adding one would be a
mistake, not an improvement (D-13).

Templates are authored in `template_seed.py` and applied through generated seed
SQL, so the review trail is commit history: diffable, attributable, permanent.
These are documents a lawyer signs off. If they were editable here, the trail
would be a Postgres row with an `updated_at`, and "which version did counsel
approve, and what changed after" becomes unanswerable.

What this page is for: seeing what is in force, spotting languages that have
fallen behind during a translation window, and rendering a template against a
real client before it reaches one.
"""

import streamlit as st

from database import get_supabase_admin

st.title("Document templates")
st.caption(
    "Read-only. Templates are authored in `template_seed.py` and applied "
    "through seed SQL so that every change is reviewable in git."
)

LANGS = ("en", "fr", "nl", "de")

STATUS_ICON = {
    "in_force": "🟢",
    "draft": "⚪",
    "pending_translation": "🟡",
    "superseded": "⚫",
}

TIER_LABEL = {
    1: "Tier 1 — pure template, no runtime LLM",
    2: "Tier 2 — template with LLM inserts",
    3: "Tier 3 — per-client assessment",
}


# ── Data ──────────────────────────────────────────────────────────────────
# Service-role client: this page must show drafts and superseded versions,
# which the client-facing RLS policy deliberately hides (it filters to
# status='in_force'). Read-only, so bypassing RLS here carries no write risk.

sb = get_supabase_admin()

try:
    templates = (
        sb.table("document_templates")
        .select("*")
        .order("sort_order")
        .execute()
        .data or []
    )
    versions = (
        sb.table("document_template_versions")
        .select("*")
        .order("version_no", desc=True)
        .execute()
        .data or []
    )
except Exception as e:
    st.error(f"Could not load templates: {e}")
    st.stop()

if not templates:
    st.info(
        "No templates yet. Run `python3 template_seed.py > seed_s25_cookie_policy.sql` "
        "and apply the result."
    )
    st.stop()

by_template: dict[str, list[dict]] = {}
for v in versions:
    by_template.setdefault(v["template_id"], []).append(v)


# ── Overview ──────────────────────────────────────────────────────────────

in_force = [v for v in versions if v["status"] == "in_force"]
c1, c2, c3 = st.columns(3)
c1.metric("Templates", len(templates))
c2.metric("Versions in force", len(in_force))
c3.metric("Languages covered", len({v["language"] for v in in_force}))

st.divider()


# ── Per template ──────────────────────────────────────────────────────────

for t in templates:
    tv = by_template.get(t["id"], [])
    live = {v["language"]: v for v in tv if v["status"] == "in_force"}

    heading = f"{t['title']}  ·  `{t['doc_type']}`"
    if not t.get("active"):
        heading += "  ·  retired"

    with st.expander(heading, expanded=len(templates) == 1):
        st.caption(TIER_LABEL.get(t.get("tier"), f"Tier {t.get('tier')}"))

        if not tv:
            st.warning("No versions authored for this template.")
            continue

        # Revision split across languages is legitimate mid-translation, but
        # it means the language versions are not word-for-word equivalent —
        # so it is stated rather than left for someone to notice.
        revisions = {v["source_revision"] for v in live.values()}
        if len(revisions) > 1:
            st.warning(
                "Languages are in force at different source revisions "
                f"({', '.join(str(r) for r in sorted(revisions))}). The wording "
                "of these versions differs; a translation is mid-flight."
            )

        missing = [l for l in LANGS if l not in live]
        if missing:
            st.caption(
                "No in-force version in: "
                + ", ".join(l.upper() for l in missing)
                + ". Generation for a client issuing documents in those "
                "languages will report the gap rather than substitute another."
            )

        rows = []
        for v in sorted(tv, key=lambda r: (r["language"], -r["version_no"])):
            rows.append({
                "Lang": v["language"].upper(),
                "Ver": v["version_no"],
                "Rev": v["source_revision"],
                "Status": f"{STATUS_ICON.get(v['status'], '')} {v['status']}",
                "Materiality": v.get("materiality"),
                "In force from": v.get("effective_from") or "—",
                "Reviewed by": v.get("reviewed_by") or "—",
                "Chars": len(v.get("body_md") or ""),
            })
        st.dataframe(rows, hide_index=True, width="stretch")

        # ── Body ──────────────────────────────────────────────────────
        labels = {
            f"{v['language'].upper()} v{v['version_no']} ({v['status']})": v
            for v in sorted(tv, key=lambda r: (r["language"], -r["version_no"]))
        }
        chosen = st.selectbox(
            "Show body", options=list(labels), key=f"tmpl_body_{t['id']}"
        )
        version = labels[chosen]

        tab_src, tab_rendered = st.tabs(["Source", "Rendered with a client"])

        with tab_src:
            st.caption(
                "Merge fields appear as `{{field}}`; conditionals as "
                "`{{#if:flag}}…{{/if:flag}}`; block renderers as "
                "`{{#block:name}}`."
            )
            st.code(version.get("body_md") or "", language="markdown")

        with tab_rendered:
            st.caption(
                "Renders this template against a real client. Nothing is "
                "written and no files are produced."
            )
            try:
                clients = (
                    sb.table("clients")
                    .select("id, company_name, legal_name, country, document_languages")
                    .order("company_name")
                    .limit(200)
                    .execute()
                    .data or []
                )
            except Exception as e:
                clients = []
                st.error(f"Could not load clients: {e}")

            if not clients:
                st.info("No clients to render against.")
            else:
                pick = st.selectbox(
                    "Client",
                    options=[c["id"] for c in clients],
                    format_func=lambda i: next(
                        (c.get("company_name") or c.get("legal_name") or i)
                        for c in clients if c["id"] == i
                    ),
                    key=f"tmpl_client_{t['id']}",
                )

                if st.button("Render", key=f"tmpl_render_{t['id']}"):
                    try:
                        from docgen_templates import preview_templated_document
                        body, missing_req, outstanding = preview_templated_document(
                            pick, t["doc_type"], version["language"]
                        )
                    except Exception as e:
                        st.error(f"Render failed: {e}")
                        body, missing_req, outstanding = None, [], []

                    if missing_req:
                        st.error(
                            "Blocked — required fields missing for this client: "
                            + ", ".join(missing_req)
                        )
                    if outstanding:
                        st.warning(
                            f"{len(outstanding)} optional field(s) would render "
                            "as visible placeholders: "
                            + ", ".join(o["label"] for o in outstanding)
                        )
                    if body:
                        st.markdown(body)
                    elif not missing_req:
                        st.info(
                            "Nothing rendered — there may be no in-force "
                            f"template in {version['language'].upper()}."
                        )

st.divider()
st.caption(
    "To change a template: edit `template_seed.py`, run it to regenerate the "
    "seed SQL, review the diff, and apply. The generated SQL carries a "
    "do-not-edit header — editing it directly means the next regeneration "
    "silently discards the change."
)
