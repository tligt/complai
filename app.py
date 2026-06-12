import io
import os
import requests
from datetime import date
import streamlit as st
from pypdf import PdfReader
from dotenv import load_dotenv
from auth import init_auth, is_logged_in, login_ui, logout, get_user_id
from database import (
    load_clients, create_client_record, update_client_record, delete_client_record,
    load_chat_history, save_message, clear_chat_history, build_client_context
)
from rag import (
    Chunk, build_index, chunk_text, retrieve,
    ingest_to_qdrant, get_knowledge_base_summary,
    update_source_metadata, delete_source, fetch_html_text
)

load_dotenv()

st.set_page_config(page_title="COMPLAI", page_icon="⚖️", layout="centered")

# ── Constants ─────────────────────────────────────────────────────────────────

COUNTRY_OPTIONS = {
    "BE": "🇧🇪 Belgium",
    "FR": "🇫🇷 France",
    "EU": "🇪🇺 EU only",
    "nl": "🇳🇱 Netherlands",
    "de": "🇩🇪 Germany",
    "lu": "🇱🇺 Luxembourg",
}

QUERY_COUNTRY_OPTIONS = {
    "EU": "🇪🇺 EU only",
    "BE": "🇧🇪 Belgium",
    "FR": "🇫🇷 France",
    "nl": "🇳🇱 Netherlands",
    "de": "🇩🇪 Germany",
    "lu": "🇱🇺 Luxembourg",
}

SECTOR_OPTIONS = [
    "SaaS / Technology",
    "Professional services",
    "Healthcare / Medtech",
    "Manufacturing",
    "Finance / Fintech",
    "Logistics / Transport",
    "Retail / E-commerce",
    "Education",
    "Other",
]

SIZE_OPTIONS = ["1-10", "11-50", "51-150", "150+"]
REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT"]
LANG_LABELS = {"en": "EN — English", "fr": "FR — French", "nl": "NL — Dutch"}
LANG_FLAGS = {"en": "EN", "fr": "FR", "nl": "NL"}
ALL_REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT", "general"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(uploaded_file.read()))
        return "\n\n".join([page.extract_text() or "" for page in reader.pages])
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
        st.session_state.all_chunks = all_chunks
        st.session_state.embeddings = build_index(all_chunks)
    else:
        st.session_state.all_chunks = []
        st.session_state.embeddings = None


def answer_question(question: str, context_chunks: list[Chunk], history: list[dict], client_context: str = "") -> str:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not found in environment")

    context_parts = [f"[Source: {c.source}]\n{c.text}" for c in context_chunks]
    context = "\n\n---\n\n".join(context_parts)

    client_section = f"\n\n{client_context}\n" if client_context else ""

    today = date.today().strftime("%B %d, %Y")

    system_prompt = (
        "You are a compliance expert assistant helping EU SMEs understand and comply with "
        "GDPR, NIS2, the EU AI Act, the ePrivacy Directive, the European Accessibility Act, "
        "and the EU Consumer Rights Directive. "
        "Answer questions strictly based on the provided context passages. "
        "Each passage is labelled with its source document. "
        "You also have access to the conversation history — use it to understand follow-up "
        "questions and references to earlier answers. "
        f"{client_section}"
        "When a client profile is provided, tailor your answer to their specific situation: "
        "their country, sector, size, and which regulations apply to them. "
        "Structure your answers clearly: identify the relevant regulation, explain the "
        "obligation or requirement, and where possible indicate the specific article or section. "
        f"Today\'s date is {today}. When answering questions about the EU AI Act, "
        "always indicate whether the relevant obligation is currently in force or upcoming, "
        "based on the following phased enforcement timeline: "
        "prohibited AI practices (Article 5) — in force since February 2, 2025; "
        "GPAI model obligations (Articles 51-56) — in force since August 2, 2025; "
        "high-risk AI systems (Annex III) — applies from August 2, 2026; "
        "other high-risk AI systems (Annex I products) — applies from August 2, 2027. "
        "If the answer is not in the context, say so clearly. "
        "Do not use knowledge outside the provided context."
    )

    messages = [{"role": msg["role"], "content": msg["content"]} for msg in history]
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "mistral-large-latest",
            "temperature": 0.7,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "max_tokens": 2048,
        }
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def init_session():
    defaults = {
        "documents": {},
        "all_chunks": [],
        "embeddings": None,
        "messages": [],
        "recent_queries": [],
        "selected_country": "EU",
        "selected_language": "en",
        "selected_client": None,
        "clients": [],
        "show_new_client_form": False,
        "show_edit_client_form": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def select_client(client: dict):
    """Switch to a client — load their chat history."""
    st.session_state.selected_client = client
    st.session_state.show_new_client_form = False
    st.session_state.show_edit_client_form = False
    user_id = get_user_id()
    history = load_chat_history(client["id"], user_id)
    st.session_state.messages = history
    # Reset company documents when switching clients
    st.session_state.documents = {}
    st.session_state.all_chunks = []
    st.session_state.embeddings = None


# ── Client form ───────────────────────────────────────────────────────────────

def client_form(existing: dict | None = None) -> dict | None:
    """Render a create/edit client form. Returns profile dict on submit, None otherwise."""
    is_edit = existing is not None
    label = "Edit client" if is_edit else "New client"

    with st.form(key="client_form"):
        st.markdown(f"**{label}**")
        company_name = st.text_input(
            "Company name *",
            value=existing.get("company_name", "") if is_edit else ""
        )
        sector = st.selectbox(
            "Sector",
            options=SECTOR_OPTIONS,
            index=SECTOR_OPTIONS.index(existing["sector"]) if is_edit and existing.get("sector") in SECTOR_OPTIONS else 0
        )
        country = st.selectbox(
            "Country",
            options=list(COUNTRY_OPTIONS.keys()),
            format_func=lambda x: COUNTRY_OPTIONS[x],
            index=list(COUNTRY_OPTIONS.keys()).index(existing["country"]) if is_edit and existing.get("country") in COUNTRY_OPTIONS else 0
        )
        company_size = st.selectbox(
            "Company size",
            options=SIZE_OPTIONS,
            index=SIZE_OPTIONS.index(existing["company_size"]) if is_edit and existing.get("company_size") in SIZE_OPTIONS else 1
        )
        regulations = st.multiselect(
            "Applicable regulations",
            options=REGULATION_OPTIONS,
            default=existing.get("regulations", ["GDPR"]) if is_edit else ["GDPR"]
        )

        col1, col2 = st.columns(2)
        submitted = col1.form_submit_button("Save", type="primary", use_container_width=True)
        cancelled = col2.form_submit_button("Cancel", use_container_width=True)

        if cancelled:
            st.session_state.show_new_client_form = False
            st.session_state.show_edit_client_form = False
            st.rerun()

        if submitted:
            if not company_name.strip():
                st.error("Company name is required.")
                return None
            if not regulations:
                st.error("Please select at least one regulation.")
                return None
            return {
                "company_name": company_name.strip(),
                "sector": sector,
                "country": country,
                "company_size": company_size,
                "regulations": regulations,
            }
    return None


# ── App entry point ───────────────────────────────────────────────────────────

init_auth()
init_session()

if not is_logged_in():
    login_ui()
    st.stop()

# Logged in — load clients if not yet loaded
user_id = get_user_id()
if not st.session_state.clients:
    st.session_state.clients = load_clients(user_id)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:

    # ── User info + logout ─────────────────────────────────────────
    col1, col2 = st.columns([3, 1])
    col1.caption(f"👤 {st.session_state.user.email}")
    if col2.button("Log out", key="btn_logout"):
        logout()

    st.divider()

    # ── Client selector ────────────────────────────────────────────
    st.markdown("**Clients**")

    clients = st.session_state.clients
    selected = st.session_state.selected_client

    if clients:
        client_names = [c["company_name"] for c in clients]
        selected_index = 0
        if selected:
            matching = [i for i, c in enumerate(clients) if c["id"] == selected["id"]]
            if matching:
                selected_index = matching[0]

        chosen_name = st.selectbox(
            "Select client",
            options=client_names,
            index=selected_index,
            label_visibility="collapsed",
        )
        chosen_client = next((c for c in clients if c["company_name"] == chosen_name), None)

        if chosen_client and (not selected or chosen_client["id"] != selected["id"]):
            select_client(chosen_client)
            st.rerun()

        # Client profile summary
        if selected:
            regs = selected.get("regulations") or []
            if isinstance(regs, list):
                reg_str = " · ".join(regs)
            else:
                reg_str = str(regs)
            st.caption(
                f"{COUNTRY_OPTIONS.get(selected.get('country','BE'), selected.get('country',''))}  "
                f"· {selected.get('sector','')}  "
                f"· {selected.get('company_size','')} FTE\n"
                f"{reg_str}"
            )

            col_edit, col_del = st.columns(2)
            if col_edit.button("✏️ Edit", use_container_width=True, key="btn_edit_client"):
                st.session_state.show_edit_client_form = True
                st.session_state.show_new_client_form = False

            if col_del.button("🗑️ Delete", use_container_width=True, key="btn_del_client"):
                if delete_client_record(selected["id"], user_id):
                    st.session_state.clients = load_clients(user_id)
                    st.session_state.selected_client = None
                    st.session_state.messages = []
                    st.rerun()

    else:
        st.caption("No clients yet. Create your first client below.")

    if st.button("➕ New client", use_container_width=True, key="btn_new_client"):
        st.session_state.show_new_client_form = True
        st.session_state.show_edit_client_form = False

    # ── New client form ────────────────────────────────────────────
    if st.session_state.show_new_client_form:
        profile = client_form()
        if profile:
            new_client = create_client_record(user_id, profile)
            if new_client:
                st.session_state.clients = load_clients(user_id)
                st.session_state.show_new_client_form = False
                select_client(new_client)
                st.rerun()

    # ── Edit client form ───────────────────────────────────────────
    if st.session_state.show_edit_client_form and selected:
        profile = client_form(existing=selected)
        if profile:
            if update_client_record(selected["id"], user_id, profile):
                st.session_state.clients = load_clients(user_id)
                updated = next((c for c in st.session_state.clients if c["id"] == selected["id"]), None)
                if updated:
                    st.session_state.selected_client = updated
                st.session_state.show_edit_client_form = False
                st.rerun()

    st.divider()

    # ── Admin section ──────────────────────────────────────────────
    with st.expander("⚙️ Admin — Knowledge Base"):

        admin_tab1, admin_tab2, admin_tab3 = st.tabs(["➕ Add", "✏️ Edit", "🗑️ Delete"])

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
                "Document type", options=["core", "supplementary"], index=1,
                format_func=lambda x: "📜 Core" if x == "core" else "📎 Supplementary",
                key="admin_doc_type", horizontal=True,
            )
            parent_reg = st.selectbox("Related regulation", options=ALL_REGULATION_OPTIONS, key="admin_parent_reg")
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
                                text=admin_text, source=source_name,
                                language=admin_lang, country=admin_country,
                                doc_type=doc_type, parent_regulation=parent_reg,
                            )
                            st.success(f"✅ {count} chunks ingested from '{source_name}'")
                        except Exception as e:
                            st.error(f"Ingestion failed: {e}")
                elif not source_name:
                    st.warning("Please enter a source name.")
                else:
                    st.warning("No content found to ingest.")

        with admin_tab2:
            st.caption("Update metadata for an existing document.")
            try:
                kb = get_knowledge_base_summary()
                source_names = [item["source"] for item in kb]
                if source_names:
                    selected_source = st.selectbox("Select document", options=source_names, key="edit_source")
                    meta = next((i for i in kb if i["source"] == selected_source), {})
                    st.caption(f"{meta.get('chunks','?')} chunks · {meta.get('language','?').upper()} · {meta.get('country','?').upper()} · {meta.get('doc_type','?')}")

                    new_name = st.text_input("New source name (optional)", key="edit_name")
                    new_country = st.selectbox("Country scope", options=list(COUNTRY_OPTIONS.keys()), format_func=lambda x: COUNTRY_OPTIONS[x], key="edit_country")
                    new_lang = st.selectbox("Language", options=["en", "fr", "nl"], format_func=lambda x: LANG_LABELS[x], key="edit_lang")
                    new_doc_type = st.radio("Document type", options=["core", "supplementary"], format_func=lambda x: "📜 Core" if x == "core" else "📎 Supplementary", key="edit_doc_type", horizontal=True)
                    new_parent_reg = st.selectbox("Related regulation", options=ALL_REGULATION_OPTIONS, key="edit_parent_reg")

                    if st.button("Save changes", type="primary", key="btn_edit"):
                        with st.spinner("Updating..."):
                            count = update_source_metadata(
                                old_source=selected_source,
                                new_source=new_name if new_name else None,
                                new_country=new_country, new_language=new_lang,
                                new_doc_type=new_doc_type, new_parent_regulation=new_parent_reg,
                            )
                            st.success(f"✅ Updated {count} chunks for '{selected_source}'")
                else:
                    st.caption("No documents in knowledge base.")
            except Exception as e:
                st.error(f"Could not load documents: {e}")

        with admin_tab3:
            st.caption("Permanently remove a document from the knowledge base.")
            try:
                kb = get_knowledge_base_summary()
                source_names = [item["source"] for item in kb]
                if source_names:
                    del_source = st.selectbox("Select document to delete", options=source_names, key="del_source")
                    del_meta = next((i for i in kb if i["source"] == del_source), {})
                    st.caption(f"{del_meta.get('chunks','?')} chunks will be removed.")
                    if st.button("🗑️ Delete permanently", type="secondary", key="btn_delete"):
                        with st.spinner("Deleting..."):
                            count = delete_source(del_source)
                            st.success(f"✅ Deleted {count} chunks for '{del_source}'")
                else:
                    st.caption("No documents in knowledge base.")
            except Exception as e:
                st.error(f"Could not load documents: {e}")

    st.divider()

    # ── Knowledge base summary ─────────────────────────────────────
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
                    st.caption(f"{lang} [{item['country'].upper()}] {item['source']} — {item['chunks']} chunks")
            else:
                st.caption("No documents found.")
        except Exception as e:
            st.caption(f"Could not load knowledge base: {e}")

    st.divider()

    # ── Query settings ─────────────────────────────────────────────
    st.markdown("**Query settings**")
    selected_country = st.selectbox(
        "Country context", options=list(QUERY_COUNTRY_OPTIONS.keys()),
        format_func=lambda x: QUERY_COUNTRY_OPTIONS[x], key="country_selector",
    )
    st.session_state.selected_country = selected_country

    selected_language = st.selectbox(
        "Language", options=["en", "fr", "nl"],
        format_func=lambda x: LANG_LABELS[x], key="language_selector",
    )
    st.session_state.selected_language = selected_language

    top_k = st.slider("Chunks to retrieve per query", min_value=2, max_value=20, value=6)

    st.divider()

    # ── Company documents ──────────────────────────────────────────
    st.header("Company Documents")
    st.caption("Upload documents to check them for compliance.")

    uploaded_files = st.file_uploader(
        "Upload company documents", type=["txt", "pdf", "docx"], accept_multiple_files=True
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
        st.markdown(f"**{len(st.session_state.documents)} document(s) loaded**")
        st.caption(f"{len(st.session_state.all_chunks)} total chunks")
        for name in list(st.session_state.documents.keys()):
            col1, col2 = st.columns([5, 1])
            col1.caption(f"📄 {name}")
            if col2.button("✕", key=f"remove_{name}"):
                del st.session_state.documents[name]
                rebuild_index()
                st.rerun()
        if st.button("Clear all", use_container_width=True):
            st.session_state.documents = {}
            st.session_state.messages = []
            rebuild_index()
            st.rerun()

    # ── Recent queries ─────────────────────────────────────────────
    if st.session_state.recent_queries:
        st.divider()
        st.markdown("**Recent queries**")
        for q in reversed(st.session_state.recent_queries[-8:]):
            if st.button(f"↩ {q[:45]}{'...' if len(q) > 45 else ''}", key=f"rq_{q[:45]}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": q})
                st.rerun()


# ── Main area ─────────────────────────────────────────────────────────────────

st.title("COMPLAI ⚖️")
st.caption("AI-powered compliance assistant for GDPR, NIS2, and the EU AI Act.")

selected_client = st.session_state.selected_client

if not selected_client:
    st.info("👈 Select a client from the sidebar or create a new one to start.")
    st.stop()

# Client header
regs = selected_client.get("regulations") or []
reg_str = " · ".join(regs) if isinstance(regs, list) else str(regs)
st.markdown(f"### {selected_client['company_name']}")
st.caption(
    f"{COUNTRY_OPTIONS.get(selected_client.get('country','BE'), '')}  ·  "
    f"{selected_client.get('sector','')}  ·  "
    f"{selected_client.get('company_size','')} FTE  ·  {reg_str}"
)

# Clear history button
if st.session_state.messages:
    if st.button("🗑️ Clear chat history", key="btn_clear_history"):
        clear_chat_history(selected_client["id"], user_id)
        st.session_state.messages = []
        st.rerun()

st.divider()

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask a compliance question..."):
    if prompt not in st.session_state.recent_queries:
        st.session_state.recent_queries.append(prompt)

    # Save and display user message
    save_message(selected_client["id"], user_id, "user", prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate and display answer
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
            client_context = build_client_context(selected_client)
            history = st.session_state.messages[:-1]
            answer = answer_question(prompt, context_chunks, history, client_context)

        st.markdown(answer)

        with st.expander("Sources used"):
            for i, chunk in enumerate(context_chunks, 1):
                st.markdown(f"**{i}. {chunk.source}**")
                st.text(chunk.text[:400] + ("..." if len(chunk.text) > 400 else ""))

    # Save and store assistant message
    save_message(selected_client["id"], user_id, "assistant", answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})
