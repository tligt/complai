"""
pages/compliance_record.py — S27. The auditor-facing compliance record.

DIFFERENT AUDIENCE FROM EVERY OTHER PAGE.
-----------------------------------------
The rest of the app is for a client doing daily work. This is for the person
they hand things to: their auditor, their counsel, a supervisory authority, or
a customer's procurement team.

That audience asks one question — **what were you operating under, and when** —
so the default view answers it: one row per document and language, showing the
version in force, the date it took effect, and where it came from. Everything
else is behind an expander.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Drafts, by default. A draft is the client's working state: produced, not
adopted, not what the organisation operates under. Listing it beside in-force
documents invites a reader to count it as coverage, which is the false
assurance the adoption step exists to remove. There is a toggle, because a
draft is still evidence that something is in progress.

Generation. This page reports; it does not produce. A reader who can generate
documents from the compliance record is a reader who can change what the record
says while reading it.

Rendering only. Every judgement — what state a document is in, whose gap it is,
which version superseded which — comes from register.py, which has no Streamlit
in it (D-61).

WHY THIS FILE IS NOT CALLED register.py
---------------------------------------
It was, and it could not import the module it depends on. Streamlit puts a
page's own directory on sys.path, so `import register` inside pages/register.py
resolved to the page itself. Silent until runtime, and the traceback points at
the import line rather than at the collision.

A module in pages/ must not share a name with a root module it imports.
"""

import streamlit as st

import register as REG
from auth import get_user_id
from database import (
    get_supabase,
    get_register_status,
    get_template_languages,
    get_client_document_history,
    get_signed_url,
    document_source_label,
    set_legal_hold,
    DOCUMENT_STATUSES,
)
from obligations import DOC_CATALOG, REGULATION_LABELS

st.title("🗄️ Compliance record")
st.caption(
    "What your organisation operates under, and since when. This is the view "
    "to share with an auditor."
)

user_id = get_user_id()
if not user_id:
    st.error("Please log in to view the compliance record.")
    st.stop()

try:
    client = (get_supabase().table("clients").select("*")
              .eq("user_id", user_id).single().execute().data) or {}
except Exception:
    client = {}

if not client:
    st.warning("Please complete your company profile first.")
    st.stop()

client_id     = client.get("id")
company_name  = client.get("company_name", "Your company")
regulations   = client.get("regulations") or ["GDPR"]
doc_languages = [l.lower() for l in (client.get("document_languages") or ["en"])]

register       = get_register_status(client_id, user_id) if client_id else {}
template_langs = get_template_languages()

show_drafts = st.toggle(
    "Include drafts",
    value=False,
    help=(
        "Drafts are produced but not adopted — your organisation is not "
        "operating under them. Off by default so this page answers only what "
        "applies."
    ),
)

# ── Summary ───────────────────────────────────────────────────────────────
relevant = {
    k: v for k, v in DOC_CATALOG.items()
    if v["regulations"] and any(r in regulations for r in v["regulations"])
}

statuses = {
    dt: REG.document_status(
        doc_type=dt,
        languages=doc_languages,
        register_rows=register.get(dt),
        template_languages=(template_langs.get(dt) if template_langs else None),
    )
    for dt in relevant
}

cov = REG.coverage(statuses.values())

c1, c2, c3 = st.columns(3)
c1.metric("Documents in force", f"{cov['covered']} / {cov['required']}")
c2.metric("Coverage", f"{cov['percent']}%")
if cov["blocked_on_us"]:
    # Counted separately and never against the client (D-59): a coverage figure
    # that falls because RECOSA has not written a template yet is billing the
    # client for our backlog.
    c3.metric("Awaiting a RECOSA template", cov["blocked_on_us"])

if cov["partly_blocked"]:
    # In force in every language RECOSA can serve, still short one it cannot.
    # Said out loud so the figure above is not mistaken for a claim that every
    # language is covered.
    st.caption(
        f":gray[{cov['partly_blocked']} document(s) counted as in force are "
        "still missing a language RECOSA has no template for yet. Those are "
        "listed below and are not outstanding on your side.]"
    )

st.caption(
    f"{company_name} · document languages "
    + ", ".join(l.upper() for l in doc_languages)
    + " · regulations "
    + ", ".join(REGULATION_LABELS.get(r, r) for r in regulations)
)

st.divider()

# ── One section per document ──────────────────────────────────────────────
for doc_type, meta in relevant.items():
    status = statuses[doc_type]
    rows_by_lang = register.get(doc_type, {})

    if status["state"] == REG.NOT_GENERATED and not status["in_force"]:
        # Nothing to report but the absence. Said once, plainly, rather than
        # given a section of its own — an auditor reading a page of empty
        # headings learns less than one reading a list of what is missing.
        continue

    st.markdown(f"### {meta['label']}")
    note = REG.status_note(status, multilingual=len(doc_languages) > 1)
    if note:
        st.caption(note.capitalize())

    for lang in doc_languages:
        row = (rows_by_lang or {}).get(lang)
        if not row:
            continue
        if row.get("status") == "draft" and not show_drafts:
            continue

        history = get_client_document_history(client_id, user_id, doc_type,
                                              language=lang)
        chain = REG.supersession_chain(history)
        current = next((c for c in chain if c["id"] == row["id"]), row)

        head = f"**{lang.upper()}**"
        if current.get("version"):
            head += f" · **v{current['version']}**"
        if current.get("status") == "in_force":
            head += f" · :green[In force] from {current.get('effective_from') or '—'}"
        elif current.get("status") == "draft":
            head += " · :orange[Draft — not adopted]"
        else:
            head += f" · :gray[{DOCUMENT_STATUSES.get(current.get('status'), '')}]"

        st.markdown(head)

        # Provenance. The register holds documents RECOSA produced AND
        # documents the client uploaded, and an auditor needs to know which is
        # which: an uploaded revision is one RECOSA cannot score, cannot check
        # for a removed clause, and cannot propagate a regulatory update into.
        src = current.get("source") or ""
        st.caption(document_source_label(src))
        if src in ("client_upload", "client_modified", "client_supplied"):
            st.caption(
                ":gray[Supplied or reworked by the client. RECOSA holds this "
                "document but does not vouch for its contents, and regulatory "
                "updates are not applied to it.]"
            )
        elif current.get("source_revision"):
            st.caption(
                f":gray[Produced from a reviewed template, source revision "
                f"{current['source_revision']}.]"
            )

        if current.get("change_comment"):
            st.caption(f"“{current['change_comment']}”")

        # Retention and hold. Shown on in-force rows too, because the question
        # "how long will you keep the old ones" is one an auditor asks about
        # the practice, not about a particular superseded file.
        if current.get("legal_hold"):
            st.warning(
                "🔒 Legal hold — retained regardless of age"
                + (f": {current['hold_reason']}" if current.get("hold_reason") else "")
            )

        fpath = current.get("file_path")
        url = get_signed_url("compliance-files", fpath, expires_in=300) if fpath else None
        if url:
            st.link_button("Download", url)

        # ── The chain ──────────────────────────────────────────────────────
        previous = [c for c in chain
                    if c["id"] != current["id"]
                    and c.get("status") in ("superseded", "archived")]
        if previous:
            with st.expander(f"What applied before ({len(previous)})"):
                st.caption(
                    "Retained as the record of what your organisation "
                    "operated under at the time. A complaint about processing "
                    "in a past year is answered by the version that applied "
                    "then, not the current one."
                )
                st.caption(
                    "**Hold** keeps a version past its retention date, for as "
                    "long as a complaint, investigation, audit or proceeding "
                    "makes it relevant. Retention periods run on a clock; a "
                    "hold stops that clock, so evidence is not deleted during "
                    "the proceeding that needs it."
                )
                for old in previous:
                    line = f"**v{old.get('version')}**"
                    if old.get("effective_from"):
                        line += f" · {old['effective_from']}"
                    if old.get("superseded_on"):
                        line += f" → {old['superseded_on']}"
                    if old.get("superseded_by_version"):
                        line += f" · superseded by v{old['superseded_by_version']}"
                    elif old.get("status") == "archived":
                        line += " · archived, not replaced"
                    st.markdown(line)

                    if old.get("change_comment"):
                        st.caption(f"“{old['change_comment']}”")
                    if old.get("retain_until"):
                        st.caption(f":gray[Retained until {old['retain_until']}]")

                    # What the hold does, and what releasing it costs. Stated
                    # at the control rather than in a help tooltip: a client
                    # about to release a hold on a document whose retention has
                    # already run out is one click from losing it, and a
                    # tooltip is not where that belongs.
                    effect = REG.hold_release_effect(old.get("retain_until"))
                    ocols = st.columns([1, 1, 3])
                    ourl = get_signed_url("compliance-files",
                                          old.get("file_path") or "",
                                          expires_in=300) if old.get("file_path") else None
                    if ourl:
                        ocols[0].link_button("Download", ourl,
                                             use_container_width=True)

                    # Legal hold belongs on superseded versions above all: they
                    # are the ones a retention rule would otherwise delete
                    # during the proceeding that needs them.
                    held = bool(old.get("legal_hold"))
                    if ocols[1].button(
                        "Release hold" if held else "Hold",
                        key=f"hold_{old['id']}",
                        use_container_width=True,
                        help=(
                            "A hold keeps this version regardless of its "
                            "retention date, for as long as a complaint, "
                            "investigation, audit or proceeding is live."
                        ),
                    ):
                        set_legal_hold(old["id"], user_id, not held,
                                       reason="Set from the compliance record")
                        st.rerun()

                    if held:
                        ocols[2].caption(
                            "🔒 On hold — kept regardless of its retention date"
                        )
                        # The consequence of releasing, sized to the risk.
                        if effect["state"] == REG.HOLD_RELEASE_EXPIRED:
                            st.error(effect["message"])
                        elif effect["state"] == REG.HOLD_RELEASE_NEAR:
                            st.warning(effect["message"])
                        else:
                            st.caption(effect["message"])

        st.write("")

    st.divider()

# ── What is missing ───────────────────────────────────────────────────────
missing = {dt: s for dt, s in statuses.items()
           if s["state"] in (REG.NOT_GENERATED, REG.NOT_AVAILABLE)
           and not s["in_force"]}

if missing:
    st.subheader("Not yet in force")
    st.caption(
        "Shown so this page is a complete answer rather than a favourable one. "
        "A record that lists only what exists tells an auditor nothing about "
        "what does not."
    )
    for dt, s in missing.items():
        label = DOC_CATALOG[dt]["label"]
        if s["state"] == REG.NOT_AVAILABLE:
            # Ours. Said as ours — a reader who assumes otherwise concludes the
            # client ignored an obligation they had no way to discharge here.
            st.markdown(
                f"- **{label}** — no RECOSA template in "
                + ", ".join(l.upper() for l in s["not_available"])
                + " yet. Not outstanding on your side."
            )
        else:
            st.markdown(f"- **{label}** — not generated")

st.divider()
st.caption(
    "Generated from the RECOSA document register. Versions are numbered when "
    "they are put in force, so the sequence has no gaps. Superseded versions "
    "are retained as the record of what applied at the time."
)
