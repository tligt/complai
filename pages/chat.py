"""
RECOSA — AI Compliance Chat
Clean chat interface. Starts fresh each session.
Previous conversations accessible via the History panel.
"""

import io
import os
import requests
from datetime import date
import streamlit as st
from pypdf import PdfReader
from auth import get_user_id
from database import (
    get_supabase, get_supabase_admin,
    load_clients, create_client_record, update_client_record, delete_client_record,
    load_chat_history, save_message, clear_chat_history, build_client_context,
    log_token_usage,
)
from rag import retrieve, get_knowledge_base_summary

# ── Constants ─────────────────────────────────────────────────
COUNTRY_OPTIONS = {
    "EU": "🇪🇺 EU only",
    "BE": "🇧🇪 Belgium",
    "FR": "🇫🇷 France",
    "nl": "🇳🇱 Netherlands",
    "de": "🇩🇪 Germany",
    "lu": "🇱🇺 Luxembourg",
}
LANG_LABELS = {"en": "EN — English", "fr": "FR — French", "nl": "NL — Dutch"}
SECTOR_OPTIONS = [
    "SaaS / Technology", "Professional services", "Healthcare / Medtech",
    "Manufacturing", "Finance / Fintech", "Logistics / Transport",
    "Retail / E-commerce", "Education", "Other",
]
SIZE_OPTIONS = ["1-10", "11-50", "51-150", "150+"]
REGULATION_OPTIONS = ["GDPR", "NIS2", "EU_AI_ACT"]


# ── Helpers ───────────────────────────────────────────────────

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
            st.error("python-docx not installed.")
            return ""
    return uploaded_file.read().decode("utf-8", errors="replace")


def answer_question(
    question: str,
    context_chunks: list,
    history: list[dict],
    client_context: str = "",
    user_id: str | None = None,
    client_id: str | None = None,
) -> str:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not found")

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
        "You also have access to the conversation history — use it to understand follow-up questions. "
        f"{client_section}"
        "When a client profile is provided, tailor your answer to their specific situation: "
        "their country, sector, size, and which regulations apply to them. "
        "Structure your answers clearly: identify the relevant regulation, explain the obligation, "
        "and where possible indicate the specific article or section. "
        f"Today's date is {today}. "
        "For EU AI Act questions, always indicate whether the obligation is currently in force or upcoming: "
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
    _resp  = response.json()
    _usage = _resp.get("usage", {})
    try:
        log_token_usage(
            user_id=user_id,
            feature="chat",
            client_id=client_id,
            input_tokens=_usage.get("prompt_tokens", 0),
            output_tokens=_usage.get("completion_tokens", 0),
        )
    except Exception:
        pass
    return _resp["choices"][0]["message"]["content"]


# ── Session state init ────────────────────────────────────────

def init_session():
    defaults = {
        "messages":         [],
        "selected_client":  None,
        "chat_country":     "EU",
        "chat_language":    "en",
        "chat_top_k":       6,
        "show_history":     False,
        "history_loaded":   False,
        "company_docs":     {},
        "confirm_delete":   False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()
user_id = get_user_id()

# Chat-specific CSS
st.markdown("""
<style>
[data-testid="stChatInput"] {
    border-radius: 12px !important;
    border: 1.5px solid #E2E8F0 !important;
}
</style>
""", unsafe_allow_html=True)

# Account menu top right
user_email = ""
try:
    user_email = st.session_state.get("user", {}).email or ""
except Exception:
    pass

st.markdown(f"""
<style>
.account-menu {{
    position: fixed;
    top: 0.75rem;
    right: 1rem;
    z-index: 9999;
}}
</style>
<div class="account-menu">
    <details>
        <summary style="cursor:pointer;list-style:none;background:#003366;color:white;
            border-radius:50%;width:36px;height:36px;display:flex;align-items:center;
            justify-content:center;font-size:1rem;font-weight:700;user-select:none;">
            {user_email[0].upper() if user_email else "U"}
        </summary>
        <div style="position:absolute;right:0;top:44px;background:white;border:1px solid #E2E8F0;
            border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.1);min-width:180px;padding:0.5rem 0;">
            <div style="padding:0.5rem 1rem;font-size:0.8rem;color:#64748B;border-bottom:1px solid #F1F5F9;">
                {user_email}
            </div>
            <a href="?logout=1" style="display:block;padding:0.5rem 1rem;font-size:0.875rem;
                color:#1A202C;text-decoration:none;" onmouseover="this.style.background='#F8FAFC'"
                onmouseout="this.style.background='transparent'">
                Log out
            </a>
        </div>
    </details>
</div>
""", unsafe_allow_html=True)

# Handle logout via query param
if st.query_params.get("logout"):
    from auth import logout
    logout()

# ── Sidebar — client selector + settings ──────────────────────
with st.sidebar:
    st.markdown("**My clients**")

    # Load clients
    try:
        clients = load_clients(user_id)
    except Exception:
        clients = []

    client_options = {c["company_name"]: c for c in clients}

    # Client selector
    selected_name = st.selectbox(
        "Active client",
        options=["— Select client —"] + list(client_options.keys()),
        key="client_selector",
        label_visibility="collapsed",
    )

    if selected_name != "— Select client —":
        selected = client_options[selected_name]
        if st.session_state.selected_client != selected:
            st.session_state.selected_client = selected
            st.session_state.messages = []
            st.session_state.history_loaded = False

    # Chat tools under client selector
    if st.session_state.selected_client:
        st.markdown("<div style='font-size:0.75rem;color:#64748B;text-transform:uppercase;letter-spacing:0.05em;margin-top:0.5rem;'>💬 Chat</div>", unsafe_allow_html=True)
        col_h, col_n = st.columns(2)
        with col_h:
            if st.button("📋 History", key="btn_history", use_container_width=True):
                st.session_state.show_history = not st.session_state.show_history
        with col_n:
            if st.button("✚ New chat", key="btn_new_chat", use_container_width=True):
                st.session_state.messages = []
                st.session_state.show_history = False
                st.rerun()

    # Add new client
    with st.expander("➕ New client"):
        nc_name = st.text_input("Company name", key="nc_name")
        nc_sector = st.selectbox("Sector", SECTOR_OPTIONS, key="nc_sector")
        nc_country = st.selectbox("Country", list(COUNTRY_OPTIONS.keys()),
                                   format_func=lambda x: COUNTRY_OPTIONS[x], key="nc_country")
        nc_size = st.selectbox("Size", SIZE_OPTIONS, key="nc_size")
        nc_regs = st.multiselect("Regulations", REGULATION_OPTIONS,
                                  default=["GDPR"], key="nc_regs")
        if st.button("Create client", type="primary", use_container_width=True, key="btn_nc"):
            if nc_name.strip():
                result = create_client_record(user_id, {
                    "company_name": nc_name.strip(),
                    "sector": nc_sector,
                    "country": nc_country,
                    "company_size": nc_size,
                    "regulations": nc_regs,
                })
                if result:
                    st.success(f"✅ {nc_name} created")
                    st.rerun()

    st.divider()

    # Query settings
    st.markdown("**Query settings**")
    st.session_state.chat_country = st.selectbox(
        "Country context",
        options=list(COUNTRY_OPTIONS.keys()),
        format_func=lambda x: COUNTRY_OPTIONS[x],
        key="country_sel",
    )
    st.session_state.chat_language = st.selectbox(
        "Language",
        options=["en", "fr", "nl"],
        format_func=lambda x: LANG_LABELS[x],
        key="lang_sel",
    )
    st.session_state.chat_top_k = st.slider(
        "Context depth", min_value=2, max_value=20, value=6, key="topk_sel"
    )

    st.divider()

    # Company document upload
    st.markdown("**Company documents**")
    st.caption("Upload documents to check for compliance.")
    uploaded_files = st.file_uploader(
        "Upload", type=["txt", "pdf", "docx"],
        accept_multiple_files=True, label_visibility="collapsed",
    )
    if uploaded_files:
        from rag import chunk_text, Chunk, build_index
        for f in uploaded_files:
            if f.name not in st.session_state.company_docs:
                with st.spinner(f"Processing {f.name}..."):
                    text = extract_text(f)
                    if text.strip():
                        chunks = [Chunk(text=c, source=f.name) for c in chunk_text(text)]
                        st.session_state.company_docs[f.name] = chunks
                        st.success(f"✅ {f.name}")

    if st.session_state.company_docs:
        for name in list(st.session_state.company_docs.keys()):
            col_n, col_x = st.columns([4, 1])
            col_n.caption(f"📄 {name[:25]}")
            if col_x.button("✕", key=f"rm_{name}"):
                del st.session_state.company_docs[name]
                st.rerun()


# ── Main area ─────────────────────────────────────────────────
selected_client = st.session_state.selected_client

# ── No client selected ────────────────────────────────────────
if not selected_client:
    st.markdown("""
    <div class="empty-chat-wrapper">
        <div style="font-size:2.5rem;margin-bottom:1rem;">🛡️</div>
        <h2 style="color:#003366;font-weight:700;margin-bottom:0.5rem;">RECOSA Compliance Chat</h2>
        <p style="color:#64748B;max-width:400px;">Select a client from the sidebar to start a compliance conversation about GDPR, NIS2, or the EU AI Act.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Client header ─────────────────────────────────────────────
regs = selected_client.get("regulations") or []
reg_str = " · ".join(regs) if isinstance(regs, list) else str(regs)
st.caption(
    f"{COUNTRY_OPTIONS.get(selected_client.get('country','BE'), '')} · "
    f"{selected_client.get('sector','')} · "
    f"{selected_client.get('company_size','')} FTE · {reg_str}"
)

# ── History panel ─────────────────────────────────────────────
if st.session_state.show_history:
    with st.expander("📋 Conversation history", expanded=True):
        try:
            history = load_chat_history(selected_client["id"], user_id)
            if not history:
                st.caption("No saved conversations for this client.")
            else:
                # Group into user messages for preview
                user_msgs = [m for m in history if m["role"] == "user"]
                st.caption(f"{len(history)} messages · {len(user_msgs)} questions asked")

                col_load, col_delete = st.columns(2)
                with col_load:
                    if st.button("📂 Load conversation", type="primary",
                                  key="btn_load_hist", use_container_width=True):
                        st.session_state.messages = history
                        st.session_state.show_history = False
                        st.rerun()
                with col_delete:
                    if st.button("🗑️ Delete history", key="btn_del_hist",
                                  use_container_width=True):
                        st.session_state.confirm_delete = True

                if st.session_state.get("confirm_delete"):
                    st.warning("This will permanently delete all saved messages for this client.")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("Yes, delete", type="primary", key="btn_confirm_del",
                                      use_container_width=True):
                            clear_chat_history(selected_client["id"], user_id)
                            st.session_state.messages = []
                            st.session_state.confirm_delete = False
                            st.session_state.show_history = False
                            st.rerun()
                    with col_no:
                        if st.button("Cancel", key="btn_cancel_del",
                                      use_container_width=True):
                            st.session_state.confirm_delete = False
                            st.rerun()

                # Preview recent exchanges
                st.markdown("**Recent questions:**")
                for msg in reversed(user_msgs[-5:]):
                    preview = msg["content"][:80] + ("…" if len(msg["content"]) > 80 else "")
                    st.caption(f"👤 {preview}")
        except Exception as e:
            st.error(f"Could not load history: {e}")
# ── Answer helper ─────────────────────────────────────────────
def handle_prompt(prompt: str):
    """Process a user prompt and generate an answer."""
    save_message(selected_client["id"], user_id, "user", prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            from rag import Chunk, build_index
            company_chunks = []
            for chunks in st.session_state.company_docs.values():
                company_chunks.extend(chunks)

            embeddings = build_index(company_chunks) if company_chunks else None

            context_chunks = retrieve(
                prompt,
                company_chunks,
                embeddings,
                top_k=st.session_state.chat_top_k,
                language=st.session_state.chat_language,
                country=st.session_state.chat_country,
            )

            client_context = build_client_context(selected_client)
            history_for_llm = st.session_state.messages[:-1]

            answer = answer_question(
                prompt,
                context_chunks,
                history_for_llm,
                client_context,
                user_id=user_id,
                client_id=selected_client.get("id"),
            )

        st.markdown(answer)

        if context_chunks:
            with st.expander("Sources used"):
                for i, chunk in enumerate(context_chunks, 1):
                    st.markdown(f"**{i}. {chunk.source}**")
                    st.text(chunk.text[:400] + ("..." if len(chunk.text) > 400 else ""))

    save_message(selected_client["id"], user_id, "assistant", answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})


# ── Chat messages ─────────────────────────────────────────────
if not st.session_state.messages:
    # ── HERO STATE — input centered on page ───────────────────
    st.markdown("<div style='height:18vh'></div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        # Title
        st.markdown(f"""
        <div style="text-align:center;margin-bottom:1.5rem;">
            <div style="font-size:1.75rem;margin-bottom:0.5rem;">💬</div>
            <h3 style="color:#003366;font-weight:700;margin-bottom:0.25rem;">{selected_client['company_name']}</h3>
            <p style="color:#64748B;font-size:0.9rem;margin-bottom:1.5rem;">Ask any compliance question about GDPR, NIS2, or the EU AI Act.</p>
        </div>
        """, unsafe_allow_html=True)

        # Hero input — styled to look like a chat input
        st.markdown("""
        <style>
        div[data-testid="stTextInput"] input {
            border-radius: 24px !important;
            border: 1.5px solid #E2E8F0 !important;
            padding: 0.75rem 1.25rem !important;
            font-size: 1rem !important;
            box-shadow: 0 2px 12px rgba(0,51,102,0.08) !important;
        }
        div[data-testid="stTextInput"] input:focus {
            border-color: #14C7D5 !important;
            box-shadow: 0 2px 16px rgba(20,199,213,0.15) !important;
        }
        </style>
        """, unsafe_allow_html=True)

        hero_input = st.text_input(
            "hero_input",
            placeholder="Ask a compliance question…",
            label_visibility="collapsed",
            key="hero_question",
        )

        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn2:
            hero_submit = st.button("Ask →", type="primary", use_container_width=True, key="hero_submit")

        if hero_submit and hero_input.strip():
            handle_prompt(hero_input.strip())
            st.rerun()

        # Suggested questions
        st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
        suggestions = [
            "What does GDPR say about data retention?",
            "Are we subject to NIS2?",
            "What is a DPIA and when is it required?",
        ]
        for s in suggestions:
            if st.button(s, key=f"suggest_{s[:20]}", use_container_width=True):
                handle_prompt(s)
                st.rerun()

else:
    # ── CONVERSATION STATE — messages + native chat input ─────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask a compliance question…"):
        handle_prompt(prompt)
        st.rerun()
