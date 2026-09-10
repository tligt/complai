"""
pages/wording.py — S29A. The prose RECOSA cannot derive.

Five sections that go into the incident response plan and the business
continuity plan. RECOSA drafts each one; the client edits it; it is then merged
like any other field.

WHY THIS IS A PAGE AND NOT PART OF GENERATION
---------------------------------------------
Tier 2 means a template with client-authored prose in it, not a template a
model fills in at render time.

Generating the prose during generation would mean every regeneration produced
different text, nothing was reviewable before it landed in a document, and a
lawyer reviewing a template reviewed a shape rather than a document. That is
the whole of template-first (D-01).

So the LLM runs here, at authoring time, where a person sees the output and
owns it before it reaches anything. Same category as the S26C translation
drafts: assistance, under review, stored.

The draft is a STARTING POINT and the page says so. D-43/D-44: RECOSA supplies
something defensible, the client owns the answer, and it is not scored.
"""

import streamlit as st

import draft_inserts
from auth import get_user_id
from database import get_supabase, log_audit_event
from template_nis2 import INSERTS

st.title("Incident and continuity wording")
st.caption(
    "Five short sections that go into your incident response plan and your "
    "business continuity plan. RECOSA drafts each one; you correct it. What "
    "you save here is what appears in the documents."
)

user_id = get_user_id()
if not user_id:
    st.error("Please log in.")
    st.stop()

try:
    client = (get_supabase().table("clients").select("*")
              .eq("user_id", user_id).single().execute().data) or {}
except Exception as e:
    st.error(f"Could not load your profile: {e}")
    st.stop()

if not client:
    st.warning("Please complete your company profile first.")
    st.stop()

client_id = client["id"]

# The languages this client's DOCUMENTS are produced in — not the interface
# language (D-75). A section written only in English produced English
# paragraphs under French headings in a plan meant to be read during an
# incident.
doc_langs = [l.lower() for l in (client.get("document_languages") or ["en"])]


def _unplaced(key: str) -> tuple[str, str] | None:
    """Text in a language OUTSIDE this client's document languages.

    Returns (language, text) or None.

    The English written before the languages were sorted out does not appear in
    any column when the client's documents are NL and FR — so the page looked
    empty while the documents were still rendering that English as a fallback.

    Same treatment as the activity form: surfaced with a warning rather than
    hidden, and rather than being pinned into a column it might not belong in.
    English is text that happens to be there, not a privileged source.
    """
    blob = client.get(INSERTS[key]["column"]) or {}
    if not isinstance(blob, dict):
        return None
    if any((blob.get(l) or "").strip() for l in doc_langs):
        return None
    for lang, text in blob.items():
        if (text or "").strip():
            return lang, text.strip()
    legacy = (client.get(key) or "").strip()
    return ("en", legacy) if legacy else None


def _text(key: str, lang: str) -> str:
    """Stored text for one language. No cross-language fallback (D-56).

    Falls back to the legacy TEXT column only for English, which is what the
    S30 backfill assumed. Showing English in a French box would invite the
    client to "correct" it and overwrite the English.
    """
    blob = client.get(INSERTS[key]["column"]) or {}
    if isinstance(blob, dict) and (blob.get(lang) or "").strip():
        return blob[lang].strip()
    return (client.get(key) or "").strip() if lang == "en" else ""


# Counted against the DOCUMENT languages only. Text sitting in a language the
# client does not produce documents in is a fallback, not a completed section.
_filled = sum(
    1 for k in INSERTS
    if all(_text(k, l) for l in doc_langs)
)
st.progress(
    _filled / len(INSERTS),
    text=f"{_filled} of {len(INSERTS)} complete in "
         + ", ".join(l.upper() for l in doc_langs),
)

if _filled < len(INSERTS):
    st.info(
        "Documents that use a section you have not written yet will refuse to "
        "generate rather than produce a placeholder. A continuity plan with "
        "**[to complete]** where the testing section should be is worse than "
        "no continuity plan, because it looks finished."
    )

st.divider()

for key, spec in INSERTS.items():
    done = all(_text(key, l) for l in doc_langs)
    status = client.get("insert_translation_status") or {}
    pending_review = [
        l for l in doc_langs
        if (status.get(key) or {}).get(l) == "machine_unreviewed"
    ]

    header = f"{'✅' if done else '⚪'}  {spec['label']}"
    if pending_review:
        header += f"  ·  {len(pending_review)} to confirm"

    orphan = _unplaced(key)
    if orphan:
        header += "  ·  :orange[text in another language]"

    with st.expander(header, expanded=not done):
        st.caption(spec["prompt"])

        if orphan:
            _lang, _txt = orphan
            st.warning(
                f"**Written in {_lang.upper()}**, which is not one of your "
                f"document languages:\n\n*{_txt}*\n\nYour documents fall back "
                "to it, so this text is what currently appears in them. Copy "
                "it into the right column below — or write something new — and "
                "it stops being a fallback."
            )

        # One column per document language, same shape as the activity form
        # (D-56): no privileged source, and no box pre-filled from a language
        # it is not.
        cols = st.columns(len(doc_langs))
        entered: dict[str, str] = {}

        for col, lang in zip(cols, doc_langs):
            with col:
                st.markdown(f"**{lang.upper()}**")

                if (status.get(key) or {}).get(lang) == "machine_unreviewed":
                    st.caption(":orange[Draft — edit or re-save to confirm]")

                draft_key = f"draft_{key}_{lang}"
                pending = st.session_state.get(draft_key)
                if pending:
                    st.info(pending)
                    if st.button("Use this", key=f"use_{key}_{lang}",
                                 type="primary", use_container_width=True):
                        st.session_state[f"ta_{key}_{lang}"] = pending
                        st.session_state.pop(draft_key, None)
                        st.rerun()
                    if st.button("Discard", key=f"drop_{key}_{lang}",
                                 use_container_width=True):
                        st.session_state.pop(draft_key, None)
                        st.rerun()

                entered[lang] = st.text_area(
                    f"Text ({lang.upper()})",
                    value=st.session_state.get(f"ta_{key}_{lang}",
                                               _text(key, lang)),
                    key=f"ta_{key}_{lang}",
                    height=150,
                    label_visibility="collapsed",
                )

                if st.button("Draft it for me", key=f"gen_{key}_{lang}",
                             use_container_width=True, disabled=bool(pending)):
                    with st.spinner(f"Drafting in {lang.upper()}…"):
                        out = draft_inserts.draft(
                            key, client, language=lang,
                            user_id=user_id, client_id=client_id,
                        )
                    if out:
                        st.session_state[draft_key] = out
                        st.rerun()
                    else:
                        st.warning("Could not draft this one. Write it yourself.")

        # A word floor, not a character one: "We have no monitoring in place"
        # is six words and legitimate, while a 60-character floor flagged it.
        short = [
            l for l, t in entered.items()
            if t.strip() and len(t.split()) < 6
        ]
        if short:
            st.caption(
                ":orange[Very short in "
                + ", ".join(l.upper() for l in short)
                + ". If that is genuinely all there is to say, say so in a "
                "sentence — this goes into a document someone reads during an "
                "incident.]"
            )

        if st.button("Save", key=f"save_{key}", type="primary"):
            blob = dict(client.get(spec["column"]) or {})
            new_status = {k: dict(v) for k, v in status.items()}
            changed = False

            for lang, text in entered.items():
                before = (blob.get(lang) or "").strip()
                if text.strip():
                    blob[lang] = text.strip()
                    # Anything in a box at submit is theirs, edited or not —
                    # which is what makes re-saving a draft confirm it (D-76).
                    new_status.setdefault(key, {})[lang] = "human"
                elif before:
                    blob.pop(lang, None)
                    new_status.get(key, {}).pop(lang, None)
                changed = changed or text.strip() != before

            try:
                get_supabase().table("clients").update({
                    spec["column"]: blob,
                    # Legacy column kept in step as the fallback, preferring
                    # English (D-75's related defect: writing whichever
                    # language was typed first overwrote it).
                    key: blob.get("en") or next(iter(blob.values()), None),
                    "insert_translation_status": new_status,
                }).eq("id", client_id).execute()

                if changed:
                    log_audit_event(
                        company_id=client_id, user_id=user_id,
                        event_type="document", event_subtype="wording_changed",
                        resource_id=key,
                        summary=f"{spec['label']} updated",
                        metadata={"insert": key,
                                  "languages": sorted(blob)},
                    )
                for lang in doc_langs:
                    st.session_state.pop(f"ta_{key}_{lang}", None)
                st.success("Saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save: {e}")

st.divider()
st.caption(
    "These are your words, not RECOSA's. Nothing here is scored — the "
    "documents reproduce what you have written, and a section describing "
    "something you do not do is worse than one admitting it is not yet in "
    "place."
)
