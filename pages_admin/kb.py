"""
RECOSA Admin — Knowledge Base Management
Upload, edit, and delete regulatory documents in the Qdrant vector store.

9 Nov (BO review): the documents are the shared table (table_view.py); a
row's ⋮ menu edits or deletes it, in a pop-up — the separate Edit and
Delete tabs with a "select document" box are gone. Country codes are
upper-case ISO codes: retrieval matches them exactly, and "nl", "de", "lu"
(offered here until 9 Nov) would have made a document invisible — two
documents had "be" and "fr" and were never retrieved; fixed the same day.
"""

import io

import streamlit as st
from pypdf import PdfReader

import table_view as tv
from rag import (
    ingest_to_qdrant,
    get_knowledge_base_summary,
    update_source_metadata,
    delete_source,
)

st.title("Knowledge Base")
st.caption("Manage the regulatory documents ingested into Qdrant.")

LANG_OPTIONS   = {"en": "EN — English", "fr": "FR — French", "nl": "NL — Dutch"}
COUNTRY_OPTIONS = {"EU": "🇪🇺 EU", "BE": "🇧🇪 Belgium", "FR": "🇫🇷 France",
                   "NL": "🇳🇱 Netherlands", "DE": "🇩🇪 Germany", "LU": "🇱🇺 Luxembourg"}
DOC_TYPE_OPTIONS = ["core", "supplementary", "guidance", "decision", "other"]
DOC_TYPE_LABELS = {"core": "📖 Core regulation", "supplementary": "📎 Supplementary",
                   "guidance": "📝 Guidance", "decision": "⚖️ Decision", "other": "📁 Other"}
REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT", "EPRIVACY", "EAA", "CONSUMER_RIGHTS", "general"]


@st.cache_data(ttl=300, show_spinner="Reading the knowledge base…")
def _kb_summary():
    """Qdrant's summary, read once (9 Nov: it was read three times per page
    load, once per tab — about 20 s with nothing on screen). Cleared on
    Refresh and after every upload, edit or delete."""
    return get_knowledge_base_summary()


def _idx(options, value, default=0):
    return options.index(value) if value in options else default


tab_docs, tab_upload = st.tabs(["📋 Documents", "⬆️ Upload"])


# ═══════════════════════════════════════════════════════════════
# TAB 1 — DOCUMENTS
# ═══════════════════════════════════════════════════════════════

@st.dialog("Edit a document", width="large")
def _edit_dialog(meta: dict) -> None:
    src = meta["source"]
    same_name = [i for i in _kb_summary() if i["source"] == src]
    st.caption(f"{src} · {meta.get('chunks', '?')} passages"
               + (f" — the change applies to all {len(same_name)} entries named “{src}”"
                  if len(same_name) > 1 else ""))
    with st.form("kb_edit"):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("Source name", value=src)
        new_doc_type = c1.selectbox("Document type", DOC_TYPE_OPTIONS,
                                    index=_idx(DOC_TYPE_OPTIONS, meta.get("doc_type")),
                                    format_func=lambda d: DOC_TYPE_LABELS.get(d, d))
        new_reg = c1.selectbox("Regulation", REGULATION_OPTIONS,
                               index=_idx(REGULATION_OPTIONS, meta.get("parent_regulation"),
                                          REGULATION_OPTIONS.index("general")))
        langs = list(LANG_OPTIONS)
        new_lang = c2.selectbox("Language", langs, index=_idx(langs, meta.get("language")),
                                format_func=LANG_OPTIONS.get)
        countries = list(COUNTRY_OPTIONS)
        new_country = c2.selectbox("Country", countries,
                                   index=_idx(countries, (meta.get("country") or "EU").upper()),
                                   format_func=COUNTRY_OPTIONS.get)
        save = st.form_submit_button("💾 Save", type="primary")
    if save:
        with st.spinner("Updating…"):
            new_src = new_name.strip()
            count = update_source_metadata(
                old_source=src,
                new_source=new_src if new_src and new_src != src else None,
                new_country=new_country, new_language=new_lang,
                new_doc_type=new_doc_type, new_parent_regulation=new_reg,
            )
        _kb_summary.clear()
        st.session_state.kb_notice = f"✅ Updated {count} passages of “{src}”."
        st.rerun()


@st.dialog("Delete a document")
def _delete_dialog(meta: dict) -> None:
    src = meta["source"]
    st.warning(f"All passages named **{src}** will be removed from the knowledge base. "
               "This cannot be undone: the file would have to be uploaded again.")
    if st.button("🗑️ Delete permanently", type="primary"):
        with st.spinner("Deleting…"):
            count = delete_source(src)
        _kb_summary.clear()
        st.session_state.kb_notice = f"✅ Deleted {count} passages of “{src}”."
        st.rerun()


with tab_docs:
    c_a, c_b = st.columns([4, 1])
    c_a.caption("Documents currently ingested in Qdrant. Click a column title to sort; "
                "a row's ⋮ menu edits or deletes it.")
    if c_b.button("🔄 Refresh", key="refresh_kb", use_container_width=True):
        _kb_summary.clear()
        st.rerun()
    notice = st.session_state.pop("kb_notice", None)
    if notice:
        st.success(notice)

    try:
        kb_summary = _kb_summary()
        if not kb_summary:
            st.info("No documents found in the knowledge base.")
        else:
            col1, col2 = st.columns(2)
            col1.metric("Documents", len(kb_summary))
            col2.metric("Passages (chunks)", sum(i.get("chunks", 0) for i in kb_summary))
            rows = {f"{i['source']}|{i.get('language')}|{i.get('country')}": i for i in kb_summary}
            hit = tv.table(
                [{"id": rid, "cells": {
                    "type": DOC_TYPE_LABELS.get(i.get("doc_type"), i.get("doc_type")),
                    "source": i.get("source"), "reg": i.get("parent_regulation"),
                    "lang": (i.get("language") or "").upper(),
                    "country": (i.get("country") or "").upper(),
                    "chunks": i.get("chunks", 0), "added": i.get("detected_at") or None,
                }, "actions": [
                    {"id": "edit", "label": "Edit", "icon": "✏️"},
                    {"id": "delete", "label": "Delete", "icon": "🗑️", "danger": True},
                ]} for rid, i in rows.items()],
                [{"key": "type", "label": "Type"}, {"key": "source", "label": "Document"},
                 {"key": "reg", "label": "Regulation"}, {"key": "lang", "label": "Language"},
                 {"key": "country", "label": "Country"},
                 {"key": "chunks", "label": "Passages", "kind": "number"},
                 {"key": "added", "label": "Added", "kind": "date"}],
                key="kb_docs", sort=("type", "asc"))
            if hit and hit["row"] in rows:
                (_edit_dialog if hit["action"] == "edit" else _delete_dialog)(rows[hit["row"]])
    except Exception as e:
        st.error(f"Could not load the knowledge base: {e}")


# ═══════════════════════════════════════════════════════════════
# TAB 2 — UPLOAD
# ═══════════════════════════════════════════════════════════════

with tab_upload:
    st.subheader("Upload document to knowledge base")
    st.caption("Upload a PDF, TXT, or DOCX file to ingest into Qdrant.")

    col1, col2 = st.columns(2)
    with col1:
        source_name  = st.text_input("Source name *", placeholder="e.g. GDPR Full Text EN")
        doc_type     = st.selectbox("Document type", DOC_TYPE_OPTIONS)
        parent_reg   = st.selectbox("Regulation", REGULATION_OPTIONS)
    with col2:
        language     = st.selectbox("Language", list(LANG_OPTIONS.keys()),
                                     format_func=lambda x: LANG_OPTIONS[x])
        country      = st.selectbox("Country", list(COUNTRY_OPTIONS.keys()),
                                     format_func=lambda x: COUNTRY_OPTIONS[x])

    uploaded_file = st.file_uploader(
        "Select file", type=["pdf", "txt", "docx"], key="kb_upload"
    )

    if uploaded_file and st.button("⬆️ Ingest to knowledge base", type="primary",
                                    use_container_width=True, key="btn_ingest"):
        if not source_name.strip():
            st.error("Please enter a source name.")
        else:
            with st.spinner(f"Processing {uploaded_file.name}..."):
                try:
                    # Extract text
                    name = uploaded_file.name.lower()
                    if name.endswith(".pdf"):
                        reader = PdfReader(io.BytesIO(uploaded_file.read()))
                        text = "\n\n".join([p.extract_text() or "" for p in reader.pages])
                    elif name.endswith(".docx"):
                        import docx as _docx
                        doc = _docx.Document(io.BytesIO(uploaded_file.read()))
                        text = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                    else:
                        text = uploaded_file.read().decode("utf-8", errors="replace")

                    if not text.strip():
                        st.error("No text found in file.")
                    else:
                        _kb_summary.clear()
                        result = ingest_to_qdrant(
                            text=text,
                            source=source_name.strip(),
                            language=language,
                            country=country,
                            doc_type=doc_type,
                            parent_regulation=parent_reg,
                        )
                        if result:
                            _kb_summary.clear()
                            st.success(f"✅ Ingested {result} chunks for '{source_name}'")
                        else:
                            st.error("Ingestion failed — check Qdrant connection.")

                except Exception as e:
                    st.error(f"Could not ingest: {e}")
