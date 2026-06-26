"""
RECOSA Admin — Knowledge Base Management
Upload, edit, and delete regulatory documents in the Qdrant vector store.
"""

import os
import io
import streamlit as st
from pypdf import PdfReader
from database import get_supabase_admin
from rag import (
    Chunk, chunk_text, ingest_to_qdrant,
    get_knowledge_base_summary, update_source_metadata, delete_source,
)

st.title("📚 Knowledge Base")
st.caption("Manage the regulatory documents ingested into Qdrant.")

LANG_OPTIONS   = {"en": "EN — English", "fr": "FR — French", "nl": "NL — Dutch"}
COUNTRY_OPTIONS = {"EU": "🇪🇺 EU", "BE": "🇧🇪 Belgium", "FR": "🇫🇷 France",
                   "nl": "🇳🇱 Netherlands", "de": "🇩🇪 Germany", "lu": "🇱🇺 Luxembourg"}
DOC_TYPE_OPTIONS = ["core", "supplementary", "guidance", "decision", "other"]
REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT", "EPRIVACY", "EAA", "CONSUMER_RIGHTS", "general"]

tab_summary, tab_upload, tab_edit, tab_delete = st.tabs([
    "📋 Summary", "⬆️ Upload", "✏️ Edit", "🗑️ Delete"
])


# ═══════════════════════════════════════════════════════════════
# TAB 1 — SUMMARY
# ═══════════════════════════════════════════════════════════════

with tab_summary:
    st.subheader("Knowledge base contents")
    st.caption("Documents currently ingested in Qdrant.")

    if st.button("🔄 Refresh", key="refresh_kb"):
        st.rerun()

    try:
        kb_summary = get_knowledge_base_summary()
        if not kb_summary:
            st.info("No documents found in the knowledge base.")
        else:
            total_chunks = sum(item.get("chunks", 0) for item in kb_summary)
            col1, col2 = st.columns(2)
            col1.metric("Documents", len(kb_summary))
            col2.metric("Total chunks", total_chunks)

            st.divider()

            current_type = None
            for item in kb_summary:
                if item.get("doc_type") != current_type:
                    current_type = item.get("doc_type")
                    label = {
                        "core": "📖 Core Regulations",
                        "supplementary": "📎 Supplementary Guidance",
                        "guidance": "📝 Guidance",
                        "decision": "⚖️ Decisions",
                    }.get(current_type, f"📁 {current_type}")
                    st.markdown(f"**{label}**")

                lang    = item.get("language", "en").upper()
                country = item.get("country", "EU").upper()
                source  = item.get("source", "—")
                chunks  = item.get("chunks", 0)
                reg     = item.get("parent_regulation", "—")

                col_s, col_r, col_l, col_c, col_ch = st.columns([4, 2, 1, 1, 1])
                col_s.caption(f"📄 {source}")
                col_r.caption(reg)
                col_l.caption(lang)
                col_c.caption(country)
                col_ch.caption(f"{chunks} chunks")

    except Exception as e:
        st.error(f"Could not load KB summary: {e}")


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
                        raw_chunks = chunk_text(text)
                        chunks = [
                            Chunk(
                                text=c,
                                source=source_name.strip(),
                                language=language,
                                country=country,
                                doc_type=doc_type,
                                parent_regulation=parent_reg,
                            )
                            for c in raw_chunks
                        ]

                        result = ingest_to_qdrant(chunks)
                        if result:
                            st.success(f"✅ Ingested {len(chunks)} chunks for '{source_name}'")
                        else:
                            st.error("Ingestion failed — check Qdrant connection.")

                except Exception as e:
                    st.error(f"Could not ingest: {e}")


# ═══════════════════════════════════════════════════════════════
# TAB 3 — EDIT
# ═══════════════════════════════════════════════════════════════

with tab_edit:
    st.subheader("Edit document metadata")
    st.caption("Update the source name, language, country, or regulation for an existing document.")

    try:
        kb = get_knowledge_base_summary()
        source_names = [item["source"] for item in kb]

        if not source_names:
            st.info("No documents in knowledge base.")
        else:
            selected_source = st.selectbox("Select document", source_names, key="edit_source")
            meta = next((i for i in kb if i["source"] == selected_source), {})

            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("New source name (leave blank to keep)",
                                          placeholder=selected_source, key="edit_name")
                new_doc_type = st.selectbox("Document type", DOC_TYPE_OPTIONS,
                                             index=DOC_TYPE_OPTIONS.index(
                                                 meta.get("doc_type", "core"))
                                             if meta.get("doc_type") in DOC_TYPE_OPTIONS else 0,
                                             key="edit_doctype")
                new_parent_reg = st.selectbox("Regulation", REGULATION_OPTIONS,
                                               index=REGULATION_OPTIONS.index(
                                                   meta.get("parent_regulation", "general"))
                                               if meta.get("parent_regulation") in REGULATION_OPTIONS else 0,
                                               key="edit_reg")
            with col2:
                new_lang = st.selectbox("Language", list(LANG_OPTIONS.keys()),
                                         format_func=lambda x: LANG_OPTIONS[x],
                                         index=list(LANG_OPTIONS.keys()).index(
                                             meta.get("language", "en"))
                                         if meta.get("language") in LANG_OPTIONS else 0,
                                         key="edit_lang")
                new_country = st.selectbox("Country", list(COUNTRY_OPTIONS.keys()),
                                            format_func=lambda x: COUNTRY_OPTIONS[x],
                                            index=list(COUNTRY_OPTIONS.keys()).index(
                                                meta.get("country", "EU"))
                                            if meta.get("country") in COUNTRY_OPTIONS else 0,
                                            key="edit_country")

            st.caption(f"Currently: {meta.get('chunks', '?')} chunks · "
                       f"{meta.get('language','?').upper()} · {meta.get('country','?').upper()} · "
                       f"{meta.get('doc_type','?')} · {meta.get('parent_regulation','?')}")

            if st.button("💾 Save changes", type="primary", key="btn_edit"):
                with st.spinner("Updating..."):
                    count = update_source_metadata(
                        old_source=selected_source,
                        new_source=new_name.strip() if new_name.strip() else None,
                        new_country=new_country,
                        new_language=new_lang,
                        new_doc_type=new_doc_type,
                        new_parent_regulation=new_parent_reg,
                    )
                    st.success(f"✅ Updated {count} chunks for '{selected_source}'")

    except Exception as e:
        st.error(f"Could not load documents: {e}")


# ═══════════════════════════════════════════════════════════════
# TAB 4 — DELETE
# ═══════════════════════════════════════════════════════════════

with tab_delete:
    st.subheader("Delete document from knowledge base")
    st.caption("Permanently removes all chunks for a document from Qdrant.")

    try:
        kb = get_knowledge_base_summary()
        source_names = [item["source"] for item in kb]

        if not source_names:
            st.info("No documents in knowledge base.")
        else:
            del_source = st.selectbox("Select document to delete", source_names, key="del_source")
            del_meta   = next((i for i in kb if i["source"] == del_source), {})
            st.caption(f"{del_meta.get('chunks', '?')} chunks will be permanently removed.")

            if st.button("🗑️ Delete permanently", type="secondary",
                          key="btn_delete", use_container_width=True):
                with st.spinner("Deleting..."):
                    count = delete_source(del_source)
                    st.success(f"✅ Deleted {count} chunks for '{del_source}'")
                    st.rerun()

    except Exception as e:
        st.error(f"Could not load documents: {e}")
