import ioimport io
import os
import requests
import streamlit as st
from pypdf import PdfReader
from dotenv import load_dotenv
from rag import Chunk, build_index, chunk_text, retrieve

load_dotenv()

st.set_page_config(page_title="COMPLAI", page_icon="⚖️", layout="centered")

st.title("COMPLAI")
st.caption("Upload regulatory documents or company files, then ask compliance questions.")


def extract_text(uploaded_file) -> str:
    if uploaded_file.name.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(uploaded_file.read()))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    return uploaded_file.read().decode("utf-8", errors="replace")


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
]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.header("Knowledge Base")

    uploaded_files = st.file_uploader(
        "Upload files",
        type=["txt", "pdf"],
        accept_multiple_files=True,
        help="Upload regulatory texts or company documents.",
    )

    if uploaded_files:
        new_names = {f.name for f in uploaded_files}
        added = new_names - st.session_state.documents.keys()

        for f in uploaded_files:
            if f.name in added:
                with st.spinner(f"Processing {f.name}..."):
                    text = extract_text(f)
                    if not text.strip():
                        st.error(
                            f"{f.name}: No text found — may be a scanned/image PDF."
                        )
                        continue
                    raw_chunks = chunk_text(text)
                    chunks = [Chunk(text=c, source=f.name) for c in raw_chunks]
                    st.session_state.documents[f.name] = {"chunks": chunks}
                    rebuild_index()
                st.success(f"{f.name}: {len(chunks)} chunks indexed.")

    if st.session_state.documents:
        st.divider()
        st.markdown(f"**{len(st.session_state.documents)} document(s) loaded**")
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
    top_k = st.slider(
        "Chunks to retrieve per query", min_value=1, max_value=10, value=4
    )

has_index = bool(st.session_state.documents)

if not has_index:
    st.info("Upload regulatory documents or company files in the sidebar to get started.")
    with st.expander("How it works"):
        st.markdown(
            """
            1. **Upload** any number of `.pdf` or `.txt` files (regulatory texts, company policies, etc.).
            2. Each file is split into overlapping **chunks** for better coverage.
            3. All chunks are indexed using **Mistral semantic embeddings** — retrieval understands meaning, not just keywords.
            4. When you ask a question, the most relevant chunks are **retrieved** across all documents.
            5. Those chunks are sent to **Mistral Large** for a structured compliance answer.

            > PDFs must contain selectable text. Scanned/image-only PDFs are not supported.
            """
        )
else:
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
                )
                history = st.session_state.messages[:-1]
                answer = answer_question(prompt, context_chunks, history)

            st.markdown(answer)

            with st.expander("Sources used"):
                for i, chunk in enumerate(context_chunks, 1):
                    st.markdown(f"**{i}. {chunk.source}**")
                    st.text(chunk.text[:400] + ("..." if len(chunk.text) > 400 else ""))

        st.session_state.messages.append({"role": "assistant", "content": answer})

import os
import anthropic
import streamlit as st
from pypdf import PdfReader
from rag import Chunk, build_index, chunk_text, retrieve

st.set_page_config(page_title="COMPLAI", page_icon="⚖️", layout="centered")

st.title("COMPLAI")
st.caption("Upload regulatory documents or company files, then ask compliance questions.")


def get_anthropic_client():
    base_url = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
    api_key = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "dummy")
    if base_url:
        return anthropic.Anthropic(base_url=base_url, api_key=api_key)
    return anthropic.Anthropic(api_key=api_key)


def extract_text(uploaded_file) -> str:
    if uploaded_file.name.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(uploaded_file.read()))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    return uploaded_file.read().decode("utf-8", errors="replace")


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
    client = get_anthropic_client()
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
    messages.append(
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        }
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=system_prompt,
        messages=messages,
    )
    return message.content[0].text


for key, default in [
    ("documents", {}),
    ("all_chunks", []),
    ("embeddings", None),
    ("messages", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.header("Knowledge Base")

    uploaded_files = st.file_uploader(
        "Upload files",
        type=["txt", "pdf"],
        accept_multiple_files=True,
        help="Upload regulatory texts or company documents.",
    )

    if uploaded_files:
        new_names = {f.name for f in uploaded_files}
        added = new_names - st.session_state.documents.keys()

        for f in uploaded_files:
            if f.name in added:
                with st.spinner(f"Processing {f.name}..."):
                    text = extract_text(f)
                    if not text.strip():
                        st.error(
                            f"{f.name}: No text found — may be a scanned/image PDF."
                        )
                        continue
                    raw_chunks = chunk_text(text)
                    chunks = [Chunk(text=c, source=f.name) for c in raw_chunks]
                    st.session_state.documents[f.name] = {"chunks": chunks}
                    rebuild_index()
                st.success(f"{f.name}: {len(chunks)} chunks indexed.")

    if st.session_state.documents:
        st.divider()
        st.markdown(f"**{len(st.session_state.documents)} document(s) loaded**")
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
    top_k = st.slider(
        "Chunks to retrieve per query", min_value=1, max_value=10, value=4
    )

has_index = bool(st.session_state.documents)

if not has_index:
    st.info("Upload regulatory documents or company files in the sidebar to get started.")
    with st.expander("How it works"):
        st.markdown(
            """
            1. **Upload** any number of `.pdf` or `.txt` files (regulatory texts, company policies, etc.).
            2. Each file is split into overlapping **chunks** for better coverage.
            3. All chunks are indexed using **Mistral semantic embeddings** — meaning retrieval understands meaning, not just keywords.
            4. When you ask a question, the most relevant chunks are **retrieved** across all documents.
            5. Those chunks (with their source labels) are sent to **Claude** as context for a structured compliance answer.

            > PDFs must contain selectable text. Scanned/image-only PDFs are not supported.
            """
        )
else:
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
                )
                history = st.session_state.messages[:-1]
                answer = answer_question(prompt, context_chunks, history)

            st.markdown(answer)

            with st.expander("Sources used"):
                for i, chunk in enumerate(context_chunks, 1):
                    st.markdown(f"**{i}. {chunk.source}**")
                    st.text(chunk.text[:400] + ("..." if len(chunk.text) > 400 else ""))

        st.session_state.messages.append({"role": "assistant", "content": answer})
