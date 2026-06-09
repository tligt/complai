import io
import os
import requests
import streamlit as st
from pypdf import PdfReader
from dotenv import load_dotenv
from rag import (
    Chunk, build_index, chunk_text, retrieve,
    ingest_to_qdrant, get_knowledge_base_summary,
    update_source_metadata, delete_source, fetch_html_text
)

load_dotenv()

st.set_page_config(page_title="COMPLAI", page_icon="⚖️", layout="centered")

st.title("COMPLAI")
st.caption("AI-powered compliance assistant for GDPR, NIS2, and the EU AI Act.")

COUNTRY_OPTIONS = {
    "EU": "🇪🇺 EU only",
    "be": "🇧🇪 Belgium",
    "fr": "🇫🇷 France",
    "nl": "🇳🇱 Netherlands",
    "de": "🇩🇪 Germany",
    "lu": "🇱🇺 Luxembourg",
}

REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT", "general"]
LANG_LABELS = {"en": "EN — English", "fr": "FR — French", "nl": "NL — Dutch"}
LANG_FLAGS = {"en": "EN", "fr": "FR", "nl": "NL"}


def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(uploaded_file.read()))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    elif name.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(uploaded_file.read()))
            return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except ImportError:
            st.error("python-docx not installed. Please use PDF or TXT.")
            return ""
    return uploaded_file.read().decode("utf-8", errors="replace")


def detect_language(text: str) -> str:
    try:
        from langdetect import detect
        lang = detect(text[:2000])
        return lang if lang in ["en", "fr", "nl"] else "en"
    except Exception:
        return "en"


def rebuild_index():
    all_chunks = []
    for doc in st.session_state.documents.values():
        all_chunks.extend(doc["chunks"])
    if all_chunks:
        embeddings = build_index(all_chunks)
        st.session_state.all_chunks = all_chunks
        st.session_state.embeddings = embeddings
    else:
        st.session_state.all_chunks = []
        st.session_state.embeddings = None


def answer_question(question: str, context_chunks: list[Chunk], history: list[dict]) -> str:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not found in environment")

    context_parts = [f"[Source: {c.source}]\n{c.text}" for c in context_chunks]
    context = "\n\n---\n\n".join(context_parts)

    system_prompt = (
        "You are a compliance expert assistant helping EU SMEs understand and comply with "
        "GDPR, NIS2, and the EU AI Act. Answer questions strictly based on the provided "
        "context passages. Each passage is labelled with its source document. "
        "You also have access to the conversation history — use it to understand follow-up "
        "questions and references to earlier answers. "
        "Structure your answers clearly: identify the relevant regulation, explain the "
        "obligation or requirement, and where possible indicate the specific article or section. "
        "If the answer is not in the context, say so clearly. "
        "Do not use knowledge outside the provided context."
    )

    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "mistral-large-latest",
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "max_tokens": 2048,
        }
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


for key, default in [
    ("documents", {}),
    ("all_chunks", []),
    ("embeddings", None),
    ("messages", []),
    ("recent_queries", []),
    ("selected_country", "EU"),
    ("selected_language", "en"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:

    # ── Admin section ──────────────────────────────────────────
    with st.expander("⚙️ Admin — Knowledge Base"):

        admin_tab1, admin_tab2, admin_tab3 = st.tabs(["➕ Add", "✏️ Edit", "🗑️ Delete"])

        # ── Add document ──
        with admin_tab1:
            st.caption("Upload a file or ingest from a URL.")

            input_method = st.radio("Input method", ["📄 File upload", "🌐 URL (HTML page)"], horizontal=True, key="input_method")

            if input_method == "📄 File upload":
                admin_file = st.file_uploader("Upload document", type=["pdf", "txt", "docx"], key="admin_upload")
                admin_url = None
            else:
                admin_url = st.text_input("Page URL", placeholder="https://...", key="admin_url")
                admin_file = None

            source_name = st.text_input("Source name", placeholder="e.g. CCB NIS2 Guide Belgium", key="admin_source_name")
            doc_type = st.radio(
                "Document type",
                options=["core", "supplementary"],
                index=1,
                format_func=lambda x: "📜 Core" if x == "core" else "📎 Supplementary",
                key="admin_doc_type",
                horizontal=True,
            )
            parent_reg = st.selectbox("Related regulation", options=REGULATION_OPTIONS, key="admin_parent_reg")
            admin_country = st.selectbox("Country scope", options=list(COUNTRY_OPTIONS.keys()), format_func=lambda x: COUNTRY_OPTIONS[x], key="admin_country")
            admin_lang = st.selectbox("Language", options=["en", "fr", "nl"], format_func=lambda x: LANG_LABELS[x], key="admin_lang")

            if st.button("Ingest into Knowledge Base", type="primary", key="btn_ingest"):
                admin_text = ""
                if input_method == "📄 File upload" and admin_file and source_name:
                    admin_text = extract_text(admin_file)
                elif input_method == "🌐 URL (HTML page)" and admin_url and source_name:
                    with st.spinner("Fetching page..."):
                        try:
                            admin_text = fetch_html_text(admin_url)
                        except Exception as e:
                            st.error(f"Could not fetch URL: {e}")

                if admin_text.strip() and source_name:
                    with st.spinner("Ingesting..."):
                        try:
                            count = ingest_to_qdrant(
                                text=admin_text,
                                source=source_name,
                                language=admin_lang,
                                country=admin_country,
                                doc_type=doc_type,
                                parent_regulation=parent_reg,
                            )
                            st.success(f"✅ {count} chunks ingested from '{source_name}'")
                        except Exception as e:
                            st.error(f"Ingestion failed: {e}")
                elif not source_name:
                    st.warning("Please enter a source name.")
                else:
                    st.warning("No content found to ingest.")

        # ── Edit document ──
        with admin_tab2:
            st.caption("Update metadata for an existing document.")
            try:
                kb = get_knowledge_base_summary()
                source_names = [item["source"] for item in kb]
                if source_names:
                    selected_source = st.selectbox("Select document", options=source_names, key="edit_source")
                    selected_meta = next((i for i in kb if i["source"] == selected_source), {})

                    # Show current metadata clearly
                    st.markdown("**Current metadata:**")
                    col1, col2 = st.columns(2)
                    col1.caption(f"Language: **{selected_meta.get('language', '?').upper()}**")
                    col1.caption(f"Country: **{selected_meta.get('country', '?').upper()}**")
                    col2.caption(f"Type: **{selected_meta.get('doc_type', '?')}**")
                    col2.caption(f"Regulation: **{selected_meta.get('parent_regulation', '?')}**")

                    st.divider()
                    st.markdown("**New values:**")

                    # Force widget values to match selected document via session state
                    country_keys = list(COUNTRY_OPTIONS.keys())
                    current_country = selected_meta.get("country", "EU")
                    current_lang = selected_meta.get("language", "en")
                    current_doc_type = selected_meta.get("doc_type", "supplementary")
                    current_parent = selected_meta.get("parent_regulation", "general")

                    st.session_state["edit_country"] = current_country if current_country in country_keys else "EU"
                    st.session_state["edit_lang"] = current_lang if current_lang in ["en", "fr", "nl"] else "en"
                    st.session_state["edit_doc_type"] = current_doc_type
                    st.session_state["edit_parent_reg"] = current_parent if current_parent in REGULATION_OPTIONS else "general"

                    new_name = st.text_input("Source name (leave blank to keep)", key="edit_name")

                    new_country = st.selectbox(
                        "Country",
                        options=country_keys,
                        format_func=lambda x: COUNTRY_OPTIONS[x],
                        key="edit_country"
                    )

                    new_lang = st.selectbox(
                        "Language",
                        options=["en", "fr", "nl"],
                        format_func=lambda x: LANG_LABELS[x],
                        key="edit_lang"
                    )

                    new_doc_type = st.radio(
                        "Document type",
                        options=["core", "supplementary"],
                        format_func=lambda x: "📜 Core" if x == "core" else "📎 Supplementary",
                        key="edit_doc_type",
                        horizontal=True,
                    )

                    new_parent_reg = st.selectbox(
                        "Related regulation",
                        options=REGULATION_OPTIONS,
                        key="edit_parent_reg"
                    )

                    if st.button("Save changes", type="primary", key="btn_edit"):
                        with st.spinner("Updating..."):
                            count = update_source_metadata(
                                old_source=selected_source,
                                new_source=new_name if new_name else None,
                                new_country=new_country,
                                new_language=new_lang,
                                new_doc_type=new_doc_type,
                                new_parent_regulation=new_parent_reg,
                            )
                            st.success(f"✅ Updated {count} chunks for '{selected_source}'")
                else:
                    st.caption("No documents in knowledge base.")
            except Exception as e:
                st.error(f"Could not load documents: {e}")

        # ── Delete document ──
        with admin_tab3:
            st.caption("Permanently remove a document from the knowledge base.")
            try:
                kb = get_knowledge_base_summary()
                source_names = [item["source"] for item in kb]
                if source_names:
                    del_source = st.selectbox("Select document to delete", options=source_names, key="del_source")
                    del_meta = next((i for i in kb if i["source"] == del_source), {})
                    st.caption(f"{del_meta.get('chunks', '?')} chunks will be removed.")

                    if st.button("🗑️ Delete permanently", type="secondary", key="btn_delete"):
                        with st.spinner("Deleting..."):
                            count = delete_source(del_source)
                            st.success(f"✅ Deleted {count} chunks for '{del_source}'")
                else:
                    st.caption("No documents in knowledge base.")
            except Exception as e:
                st.error(f"Could not load documents: {e}")

    st.divider()

    # ── Knowledge Base summary ─────────────────────────────────
    with st.expander("📚 Regulatory Knowledge Base"):
        try:
            kb_summary = get_knowledge_base_summary()
            if kb_summary:
                current_type = None
                for item in kb_summary:
                    if item["doc_type"] != current_type:
                        current_type = item["doc_type"]
                        label = "Core Regulations" if current_type == "core" else "Supplementary Guidance"
                        st.markdown(f"**{label}**")
                    lang = LANG_FLAGS.get(item["language"], item["language"].upper())
                    country = item["country"].upper()
                    st.caption(f"{lang} [{country}] {item['source']} — {item['chunks']} chunks")
            else:
                st.caption("No documents found.")
        except Exception as e:
            st.caption(f"Could not load knowledge base: {e}")

    st.divider()

    # ── Query settings ─────────────────────────────────────────
    st.markdown("**Query settings**")

    selected_country = st.selectbox(
        "Country context",
        options=list(COUNTRY_OPTIONS.keys()),
        format_func=lambda x: COUNTRY_OPTIONS[x],
        key="country_selector",
    )
    st.session_state.selected_country = selected_country

    selected_language = st.selectbox(
        "Language",
        options=["en", "fr", "nl"],
        format_func=lambda x: LANG_LABELS[x],
        key="language_selector",
    )
    st.session_state.selected_language = selected_language

    top_k = st.slider("Chunks to retrieve per query", min_value=2, max_value=12, value=6)

    st.divider()

    # ── Company documents ──────────────────────────────────────
    st.header("Company Documents")
    st.caption("Upload your own documents to check them for compliance.")

    uploaded_files = st.file_uploader("Upload company documents", type=["txt", "pdf", "docx"], accept_multiple_files=True)

    if uploaded_files:
        new_names = {f.name for f in uploaded_files}
        added = new_names - st.session_state.documents.keys()
        for f in uploaded_files:
            if f.name in added:
                with st.spinner(f"Processing {f.name}..."):
                    text = extract_text(f)
                    if not text.strip():
                        st.error(f"{f.name}: No text found.")
                        continue
                    raw_chunks = chunk_text(text)
                    chunks = [Chunk(text=c, source=f.name) for c in raw_chunks]
                    st.session_state.documents[f.name] = {"chunks": chunks}
                    rebuild_index()
                st.success(f"{f.name}: {len(chunks)} chunks indexed.")

    if st.session_state.documents:
        st.divider()
        st.markdown(f"**{len(st.session_state.documents)} company document(s) loaded**")
        st.caption(f"{len(st.session_state.all_chunks)} total chunks")
        for name in list(st.session_state.documents.keys()):
            col1, col2 = st.columns([5, 1])
            col1.caption(f"📄 {name}")
            if col2.button("✕", key=f"remove_{name}"):
                del st.session_state.documents[name]
                rebuild_index()
                st.session_state.messages = []
                st.rerun()
        if st.button("Clear all", use_container_width=True):
            st.session_state.documents = {}
            st.session_state.messages = []
            rebuild_index()
            st.rerun()

    # ── Recent queries ─────────────────────────────────────────
    if st.session_state.recent_queries:
        st.divider()
        st.markdown("**Recent queries**")
        for q in reversed(st.session_state.recent_queries[-8:]):
            if st.button(f"↩ {q[:45]}{'...' if len(q) > 45 else ''}", key=f"rq_{q[:45]}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": q})
                st.rerun()


# ── Main chat area ─────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask a compliance question..."):
    if prompt not in st.session_state.recent_queries:
        st.session_state.recent_queries.append(prompt)

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving context and generating answer..."):
            context_chunks = retrieve(
                prompt,
                st.session_state.all_chunks,
                st.session_state.embeddings,
                top_k=top_k,
                language=st.session_state.selected_language,
                country=st.session_state.selected_country,
            )
            history = st.session_state.messages[:-1]
            answer = answer_question(prompt, context_chunks, history)

        st.markdown(answer)

        with st.expander("Sources used"):
            for i, chunk in enumerate(context_chunks, 1):
                st.markdown(f"**{i}. {chunk.source}**")
                st.text(chunk.text[:400] + ("..." if len(chunk.text) > 400 else ""))

    st.session_state.messages.append({"role": "assistant", "content": answer})
