import io
import os
import requests
import streamlit as st
from pypdf import PdfReader
from dotenv import load_dotenv
from rag import Chunk, build_index, chunk_text, retrieve, ingest_to_qdrant

load_dotenv()

st.set_page_config(page_title="COMPLAI", page_icon="⚖️", layout="centered")

st.title("COMPLAI")
st.caption("AI-powered compliance assistant for GDPR, NIS2, and the EU AI Act.")


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
        if lang in ["en", "fr", "nl"]:
            return lang
        return "en"
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


def answer_question(
    question: str,
    context_chunks: list[Chunk],
    history: list[dict],
) -> str:
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
    messages.append({
        "role": "user",
        "content": f"Context:\n{context}\n\nQuestion: {question}"
    })

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
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
    ("admin_open", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:

    # ── Admin section ──────────────────────────────────────────
    with st.expander("⚙️ Admin — Add to Knowledge Base"):
        st.caption("Permanently ingest a document into the regulatory knowledge base.")

        admin_file = st.file_uploader(
            "Upload document",
            type=["pdf", "txt", "docx"],
            key="admin_upload",
            help="PDF, TXT, or DOCX file to add permanently to Qdrant.",
        )

        source_name = st.text_input(
            "Source name",
            placeholder="e.g. CCB NIS2 Guide Belgium",
            key="admin_source_name",
        )

        if admin_file and source_name:
            with st.spinner("Detecting language..."):
                admin_text = extract_text(admin_file)
                detected_lang = detect_language(admin_text)

            lang_labels = {"en": "English", "fr": "French", "nl": "Dutch"}
            confirmed_lang = st.selectbox(
                "Detected language (confirm or correct)",
                options=["en", "fr", "nl"],
                index=["en", "fr", "nl"].index(detected_lang),
                format_func=lambda x: lang_labels[x],
                key="admin_lang",
            )

            if st.button("Ingest into Knowledge Base", type="primary"):
                if not admin_text.strip():
                    st.error("No text found in document.")
                else:
                    with st.spinner(f"Ingesting {admin_file.name}..."):
                        try:
                            count = ingest_to_qdrant(
                                text=admin_text,
                                source=source_name,
                                language=confirmed_lang,
                            )
                            st.success(f"✅ {count} chunks ingested from '{source_name}'")
                        except Exception as e:
                            st.error(f"Ingestion failed: {e}")

    st.divider()

    # ── Company documents ──────────────────────────────────────
    st.header("Company Documents")
    st.caption("Upload your own documents to check them for compliance.")

    uploaded_files = st.file_uploader(
        "Upload company documents",
        type=["txt", "pdf", "docx"],
        accept_multiple_files=True,
        help="Upload T&Cs, privacy policies, internal procedures, etc.",
    )

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
            if col2.button("✕", key=f"remove_{name}", help=f"Remove {name}"):
                del st.session_state.documents[name]
                rebuild_index()
                st.session_state.messages = []
                st.rerun()

        if st.button("Clear all", use_container_width=True):
            st.session_state.documents = {}
            st.session_state.messages = []
            rebuild_index()
            st.rerun()

    st.divider()
    top_k = st.slider("Chunks to retrieve per query", min_value=1, max_value=10, value=6)

    st.divider()
    st.markdown("**Regulatory Knowledge Base**")
    st.caption("✅ GDPR (EN/FR/NL)")
    st.caption("✅ NIS2 (EN/FR/NL)")
    st.caption("✅ EU AI Act (EN/FR/NL)")


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask a compliance question..."):
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
                language="en",
            )
            history = st.session_state.messages[:-1]
            answer = answer_question(prompt, context_chunks, history)

        st.markdown(answer)

        with st.expander("Sources used"):
            for i, chunk in enumerate(context_chunks, 1):
                st.markdown(f"**{i}. {chunk.source}**")
                st.text(chunk.text[:400] + ("..." if len(chunk.text) > 400 else ""))

    st.session_state.messages.append({"role": "assistant", "content": answer})
