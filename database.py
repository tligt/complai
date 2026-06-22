import os
import uuid
import streamlit as st
from datetime import datetime, timezone
from supabase import create_client, Client


def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    client = create_client(url, key)
    # Pass the user's session token so RLS policies are applied correctly
    token = st.session_state.get("access_token")
    if token:
        client.postgrest.auth(token)
    return client


# ── Clients ───────────────────────────────────────────────────────────────────

def load_clients(user_id: str) -> list[dict]:
    """Load all clients for the logged-in user."""
    try:
        supabase = get_supabase()
        res = supabase.table("clients") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("company_name") \
            .execute()
        return res.data or []
    except Exception as e:
        st.error(f"Could not load clients: {e}")
        return []


def create_client_record(user_id: str, profile: dict) -> dict | None:
    """Create a new client profile. Returns the created record."""
    try:
        supabase = get_supabase()
        res = supabase.table("clients").insert({
            "user_id": user_id,
            "company_name": profile["company_name"],
            "sector": profile.get("sector", ""),
            "country": profile.get("country", "BE"),
            "company_size": profile.get("company_size", ""),
            "regulations": profile.get("regulations", ["GDPR"]),
        }).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Could not create client: {e}")
        return None


def update_client_record(client_id: str, user_id: str, profile: dict) -> bool:
    """Update an existing client profile."""
    try:
        supabase = get_supabase()
        supabase.table("clients").update({
            "company_name": profile["company_name"],
            "sector": profile.get("sector", ""),
            "country": profile.get("country", "BE"),
            "company_size": profile.get("company_size", ""),
            "regulations": profile.get("regulations", ["GDPR"]),
        }).eq("id", client_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        st.error(f"Could not update client: {e}")
        return False


def delete_client_record(client_id: str, user_id: str) -> bool:
    """Delete a client and all their chat history."""
    try:
        supabase = get_supabase()
        supabase.table("clients") \
            .delete() \
            .eq("id", client_id) \
            .eq("user_id", user_id) \
            .execute()
        return True
    except Exception as e:
        st.error(f"Could not delete client: {e}")
        return False


# ── Chat history ──────────────────────────────────────────────────────────────

def load_chat_history(client_id: str, user_id: str) -> list[dict]:
    """Load chat history for a client, ordered chronologically."""
    try:
        supabase = get_supabase()
        res = supabase.table("chat_history") \
            .select("role, content") \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .order("created_at") \
            .execute()
        return res.data or []
    except Exception as e:
        st.error(f"Could not load chat history: {e}")
        return []


def save_message(client_id: str, user_id: str, role: str, content: str) -> bool:
    """Save a single message to chat history."""
    try:
        supabase = get_supabase()
        supabase.table("chat_history").insert({
            "client_id": client_id,
            "user_id": user_id,
            "role": role,
            "content": content,
        }).execute()
        return True
    except Exception as e:
        st.error(f"Could not save message: {e}")
        return False


def clear_chat_history(client_id: str, user_id: str) -> bool:
    """Delete all chat history for a client."""
    try:
        supabase = get_supabase()
        supabase.table("chat_history") \
            .delete() \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .execute()
        return True
    except Exception as e:
        st.error(f"Could not clear chat history: {e}")
        return False


# ── Client profile → system prompt ───────────────────────────────────────────

def build_client_context(client: dict) -> str:
    """Convert a client profile into a context string for the system prompt."""
    if not client:
        return ""

    regulations = client.get("regulations") or ["GDPR"]
    if isinstance(regulations, list):
        reg_str = ", ".join(regulations)
    else:
        reg_str = str(regulations)

    size_map = {
        "1-10": "1 to 10 employees",
        "11-50": "11 to 50 employees",
        "51-150": "51 to 150 employees",
        "150+": "more than 150 employees",
    }
    size_str = size_map.get(client.get("company_size", ""), client.get("company_size", "unknown size"))

    country_map = {"BE": "Belgium", "FR": "France", "EU": "EU (no specific country)"}
    country_str = country_map.get(client.get("country", "BE"), client.get("country", "Belgium"))

    return (
        f"CLIENT PROFILE:\n"
        f"- Company: {client.get('company_name', 'Unknown')}\n"
        f"- Sector: {client.get('sector', 'Not specified')}\n"
        f"- Country: {country_str}\n"
        f"- Size: {size_str}\n"
        f"- Applicable regulations: {reg_str}\n"
    )


# ── Supabase Storage ──────────────────────────────────────────────────────────

def get_supabase_admin() -> Client:
    """Get Supabase client with service role for storage operations."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
    return create_client(url, key)


def upload_file(bucket: str, path: str, file_bytes: bytes,
                content_type: str = "application/octet-stream") -> str | None:
    """Upload file to Supabase Storage. Returns storage path on success."""
    try:
        supabase = get_supabase_admin()
        supabase.storage.from_(bucket).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return path
    except Exception as e:
        st.warning(f"Could not upload file to storage: {e}")
        return None


def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str | None:
    """Get a temporary signed URL for a private file."""
    try:
        supabase = get_supabase_admin()
        res = supabase.storage.from_(bucket).create_signed_url(path, expires_in)
        return res.get("signedURL") or res.get("signed_url")
    except Exception as e:
        st.warning(f"Could not get signed URL: {e}")
        return None


def update_document_paths(doc_id: str, user_id: str,
                           file_path_docx: str | None,
                           file_path_pdf: str | None,
                           file_path_odt: str | None = None) -> bool:
    """Save storage paths back to documents table."""
    try:
        supabase = get_supabase()
        update = {}
        if file_path_docx:
            update["file_path_docx"] = file_path_docx
        if file_path_pdf:
            update["file_path_pdf"] = file_path_pdf
        if file_path_odt:
            update["file_path_odt"] = file_path_odt
        if not update:
            return False
        supabase.table("documents") \
            .update(update) \
            .eq("id", doc_id) \
            .eq("user_id", user_id) \
            .execute()
        return True
    except Exception as e:
        st.warning(f"Could not update document paths: {e}")
        return False


def update_audit_path(audit_id: str, file_path_pdf: str) -> bool:
    """Save storage path back to audits table."""
    try:
        supabase = get_supabase_admin()
        supabase.table("audits") \
            .update({"file_path_pdf": file_path_pdf}) \
            .eq("id", audit_id) \
            .execute()
        return True
    except Exception as e:
        st.warning(f"Could not update audit path: {e}")
        return False


def load_document_files(user_id: str, client_id: str | None) -> list[dict]:
    """Load document records with file paths for history display."""
    try:
        supabase = get_supabase()
        q = supabase.table("documents") \
            .select("id, document_type, language, company_name, generated_at, file_path_docx, file_path_pdf, file_path_odt") \
            .eq("user_id", user_id) \
            .order("generated_at", desc=True) \
            .limit(20)
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception as e:
        st.warning(f"Could not load document history: {e}")
        return []


def load_audit_files(email_domain: str | None = None,
                     user_id: str | None = None) -> list[dict]:
    """Load audit records with file paths."""
    try:
        supabase = get_supabase_admin()
        q = supabase.table("audits") \
            .select("id, website_url, risk_level, created_at, file_path_pdf, email") \
            .order("created_at", desc=True) \
            .limit(10)
        if email_domain:
            q = q.eq("email_domain", email_domain)
        if user_id:
            q = q.eq("user_id", user_id)
        return q.execute().data or []
    except Exception:
        return []


# ── Client document repository ────────────────────────────────

def get_current_client_documents(client_id: str, user_id: str) -> dict:
    """Get current version of each document type for a client.
    Returns dict keyed by document_type."""
    try:
        supabase = get_supabase()
        res = supabase.table("client_documents") \
            .select("*") \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .eq("is_current", True) \
            .execute()
        return {r["document_type"]: r for r in (res.data or [])}
    except Exception as e:
        return {}


def get_client_document_history(client_id: str, user_id: str,
                                 document_type: str) -> list[dict]:
    """Get full version history for a specific document type."""
    try:
        supabase = get_supabase()
        res = supabase.table("client_documents") \
            .select("*") \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .eq("document_type", document_type) \
            .order("version", desc=True) \
            .execute()
        return res.data or []
    except Exception:
        return []


def register_client_document(
    user_id: str,
    client_id: str,
    document_type: str,
    file_path: str,
    source: str = "client_upload",
    change_comment: str = "",
) -> bool:
    """Register a new document version. Marks previous version as not current."""
    try:
        supabase = get_supabase()

        # Get current version number
        res = supabase.table("client_documents") \
            .select("version") \
            .eq("client_id", client_id) \
            .eq("document_type", document_type) \
            .eq("is_current", True) \
            .execute()

        current_version = res.data[0]["version"] if res.data else 0
        new_version = current_version + 1

        # Mark previous as not current
        if current_version > 0:
            supabase.table("client_documents") \
                .update({"is_current": False}) \
                .eq("client_id", client_id) \
                .eq("user_id", user_id) \
                .eq("document_type", document_type) \
                .execute()

        # Insert new version
        supabase.table("client_documents").insert({
            "user_id": user_id,
            "client_id": client_id,
            "document_type": document_type,
            "version": new_version,
            "file_path": file_path,
            "source": source,
            "change_comment": change_comment,
            "is_current": True,
        }).execute()
        return True
    except Exception as e:
        return False


# ── Profiles & roles ──────────────────────────────────────────

def get_user_profile(user_id: str) -> dict:
    """Get profile for a user including role."""
    try:
        supabase = get_supabase_admin()
        res = supabase.table("profiles") \
            .select("*") \
            .eq("id", user_id) \
            .single() \
            .execute()
        return res.data or {}
    except Exception:
        return {}


def is_admin(user_id: str) -> bool:
    """Check if a user has admin role."""
    profile = get_user_profile(user_id)
    return profile.get("role") == "admin"


def get_all_profiles() -> list[dict]:
    """Get all user profiles — admin only."""
    try:
        supabase = get_supabase_admin()
        res = supabase.table("profiles") \
            .select("*") \
            .order("created_at", desc=True) \
            .execute()
        return res.data or []
    except Exception:
        return []


# ── Regulatory updates ────────────────────────────────────────

def save_regulatory_update(update: dict) -> str | None:
    """Save a new regulatory update. Returns id if saved, None if duplicate."""
    try:
        supabase = get_supabase_admin()
        if update.get("url"):
            existing = supabase.table("regulatory_updates") \
                .select("id") \
                .eq("url", update["url"]) \
                .execute()
            if existing.data:
                return None
        res = supabase.table("regulatory_updates") \
            .insert(update) \
            .execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        print(f"Could not save regulatory update: {e}")
        return None


def load_regulatory_updates(status: str | None = None) -> list[dict]:
    """Load regulatory updates, optionally filtered by status."""
    try:
        supabase = get_supabase_admin()
        q = supabase.table("regulatory_updates") \
            .select("*") \
            .order("detected_at", desc=True) \
            .limit(100)
        if status:
            q = q.eq("status", status)
        return q.execute().data or []
    except Exception:
        return []


def approve_regulatory_update(
    update_id: str,
    approved_by: str,
    severity: str = "info",
    send_email: bool = False,
) -> bool:
    """Approve a regulatory update."""
    try:
        supabase = get_supabase_admin()
        supabase.table("regulatory_updates") \
            .update({
                "status": "approved",
                "approved_by": approved_by,
                "approved_at": datetime.utcnow().isoformat(),
                "severity": severity,
                "send_email": send_email,
            }) \
            .eq("id", update_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Could not approve update: {e}")
        return False


def reject_regulatory_update(update_id: str) -> bool:
    """Reject a regulatory update."""
    try:
        supabase = get_supabase_admin()
        supabase.table("regulatory_updates") \
            .update({"status": "rejected"}) \
            .eq("id", update_id) \
            .execute()
        return True
    except Exception:
        return False


def create_client_alerts(update_id: str, update: dict) -> int:
    """Create alerts for all clients whose regulations match this update."""
    try:
        supabase = get_supabase_admin()
        update_regs = set(update.get("regulations") or [])
        update_countries = set(update.get("countries") or ["EU"])

        clients_res = supabase.table("clients") \
            .select("id, user_id, regulations, country") \
            .execute()
        clients = clients_res.data or []

        alerts = []
        for client in clients:
            client_regs = set(client.get("regulations") or [])
            client_country = client.get("country", "EU")

            reg_match = bool(client_regs & update_regs) or not update_regs
            country_match = (
                "EU" in update_countries or
                client_country in update_countries
            )

            if reg_match and country_match:
                alerts.append({
                    "user_id": client["user_id"],
                    "client_id": client["id"],
                    "update_id": update_id,
                    "email_sent": False,
                })

        if alerts:
            supabase.table("client_alerts").insert(alerts).execute()

        return len(alerts)
    except Exception as e:
        print(f"Could not create client alerts: {e}")
        return 0


def load_client_alerts(user_id: str, unread_only: bool = False) -> list[dict]:
    """Load alerts for a client user."""
    try:
        supabase = get_supabase()
        q = supabase.table("client_alerts") \
            .select("*, regulatory_updates(*)") \
            .eq("user_id", user_id) \
            .order("notified_at", desc=True) \
            .limit(50)
        if unread_only:
            q = q.is_("read_at", "null")
        return q.execute().data or []
    except Exception:
        return []


def mark_alert_read(alert_id: str, user_id: str) -> bool:
    """Mark an alert as read."""
    try:
        supabase = get_supabase()
        supabase.table("client_alerts") \
            .update({"read_at": datetime.utcnow().isoformat()}) \
            .eq("id", alert_id) \
            .eq("user_id", user_id) \
            .execute()
        return True
    except Exception:
        return False


def count_unread_alerts(user_id: str) -> int:
    """Count unread alerts for a user."""
    try:
        supabase = get_supabase()
        res = supabase.table("client_alerts") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .is_("read_at", "null") \
            .execute()
        return res.count or 0
    except Exception:
        return 0


# ── Sprint 12: Qdrant ingestion of approved alerts ────────────────────────────

def _fetch_article_text(url: str, timeout: int = 10) -> str | None:
    """Fetch full article text from URL. Returns None if blocked or failed."""
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=timeout)

        # EUR-Lex returns 202 with empty body — treat as failure
        if resp.status_code != 200 or len(resp.text) < 500:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()

        for selector in ["article", "main", ".content", "#content", ".document-content"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 300:
                    return text

        text = soup.get_text(separator="\n", strip=True)
        return text if len(text) > 300 else None

    except Exception as e:
        print(f"Could not fetch article text from {url}: {e}")
        return None


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping word-count chunks."""
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        if end >= len(words):
            break
        start += chunk_size - overlap
    return chunks


def _embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed texts using Mistral mistral-embed."""
    try:
        import requests as req
        api_key = os.environ["MISTRAL_API_KEY"]
        resp = req.post(
            "https://api.mistral.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "mistral-embed", "input": texts},
            timeout=30,
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]
    except Exception as e:
        print(f"Embedding failed: {e}")
        return None


def _upsert_to_qdrant(points: list[dict]) -> tuple[bool, str | None]:
    """Upsert points into Qdrant collection."""
    try:
        import requests as req
        qdrant_url = os.environ["QDRANT_URL"]
        qdrant_key = os.environ["QDRANT_API_KEY"]
        collection = os.environ.get("QDRANT_COLLECTION", "complai_kb")
        resp = req.put(
            f"{qdrant_url}/collections/{collection}/points",
            headers={"api-key": qdrant_key, "Content-Type": "application/json"},
            json={"points": points},
            timeout=30,
        )
        if not resp.ok:
            error_msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
            print(f"Qdrant upsert failed: {error_msg}")
            return False, error_msg
        return True, None
    except Exception as e:
        msg = str(e)
        print(f"Qdrant upsert exception: {msg}")
        return False, msg


def ingest_alert_to_qdrant(update: dict) -> dict:
    """
    Ingest an approved regulatory alert into Qdrant.
    Option 3: always embed summary; also try full article text with fallback.
    Returns status dict with success, chunks_ingested, full_text_ingested, error.
    """
    result = {
        "success": False,
        "summary_ingested": False,
        "full_text_ingested": False,
        "chunks_ingested": 0,
        "error": None,
    }

    update_id = update.get("id", str(uuid.uuid4()))
    summary   = (update.get("summary") or "").strip()
    url       = update.get("url") or ""
    source    = update.get("source") or ""
    title     = update.get("title") or "Regulatory Update"
    detected  = update.get("detected_at") or datetime.utcnow().isoformat()

    # regulations and countries are arrays — take first for Qdrant metadata
    regulations = update.get("regulations") or []
    countries   = update.get("countries") or ["EU"]
    regulation  = regulations[0] if regulations else "general"
    country     = countries[0] if countries else "EU"

    reg_map = {"gdpr": "GDPR", "nis2": "NIS2", "eu_ai_act": "EU_AI_ACT", "general": "general"}
    regulation_norm = reg_map.get(regulation.lower(), regulation.upper())

    if not summary:
        result["error"] = "No summary — cannot ingest"
        return result

    points = []

    # 1. Summary chunk (always)
    emb = _embed_texts([summary])
    if not emb:
        result["error"] = "Embedding failed for summary"
        return result

    points.append({
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{update_id}:summary")),
        "vector": emb[0],
        "payload": {
            "text": summary, "source": source, "url": url, "title": title,
            "language": "en", "country": country, "doc_type": "supplementary",
            "parent_regulation": regulation_norm, "type": "regulatory_update",
            "alert_id": update_id, "detected_at": detected, "chunk_type": "summary",
        },
    })
    result["summary_ingested"] = True

    # 2. Full article text (best effort)
    if url:
        article_text = _fetch_article_text(url)
        if article_text:
            chunks = _chunk_text(article_text, chunk_size=500, overlap=50)
            all_embeddings = []
            for i in range(0, len(chunks), 10):
                batch_emb = _embed_texts(chunks[i:i+10])
                if batch_emb:
                    all_embeddings.extend(batch_emb)
                else:
                    break
            for idx, (chunk, vector) in enumerate(zip(chunks, all_embeddings)):
                points.append({
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{update_id}:chunk:{idx}")),
                    "vector": vector,
                    "payload": {
                        "text": chunk, "source": source, "url": url, "title": title,
                        "language": "en", "country": country, "doc_type": "supplementary",
                        "parent_regulation": regulation_norm, "type": "regulatory_update",
                        "alert_id": update_id, "detected_at": detected,
                        "chunk_type": "full_text", "chunk_index": idx,
                    },
                })
            result["full_text_ingested"] = len(all_embeddings) > 0

    # 3. Upsert to Qdrant
    if points:
        ok, err = _upsert_to_qdrant(points)
        if ok:
            result["success"] = True
            result["chunks_ingested"] = len(points)
        else:
            result["error"] = err or "Qdrant upsert failed"
    else:
        result["error"] = "No points to upsert"

    return result


def mark_alert_ingested(update_id: str, chunks_count: int) -> bool:
    """Mark a regulatory update as ingested into Qdrant."""
    try:
        supabase = get_supabase_admin()
        supabase.table("regulatory_updates") \
            .update({
                "kb_ingested": True,
                "kb_ingested_at": datetime.utcnow().isoformat(),
                "kb_chunks_count": chunks_count,
            }) \
            .eq("id", update_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Could not mark alert as ingested: {e}")
        return False


# ── Sprint 15: Token usage logging ───────────────────────────────────────────

# Mistral Large 2 pricing (USD per million tokens, June 2026)
_MISTRAL_INPUT_COST_PER_M  = 2.00
_MISTRAL_OUTPUT_COST_PER_M = 6.00


def log_token_usage(
    user_id: str,
    feature: str,
    input_tokens: int,
    output_tokens: int,
    client_id: str | None = None,
    model: str = "mistral-large-latest",
) -> bool:
    """
    Log a Mistral API call's token usage to usage_logs.
    feature: 'chat', 'docgen', 'docgen_suggest', 'gap_single', 'gap_full'
    """
    try:
        total = input_tokens + output_tokens
        cost = (
            (input_tokens  / 1_000_000) * _MISTRAL_INPUT_COST_PER_M +
            (output_tokens / 1_000_000) * _MISTRAL_OUTPUT_COST_PER_M
        )
        supabase = get_supabase_admin()
        supabase.table("usage_logs").insert({
            "user_id":       user_id,
            "client_id":     client_id,
            "feature":       feature,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  total,
            "cost_usd":      round(cost, 6),
        }).execute()
        return True
    except Exception as e:
        print(f"Could not log token usage: {e}")
        return False


def load_token_usage(
    since: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """Load usage_logs, optionally filtered by date and/or user."""
    try:
        supabase = get_supabase_admin()
        q = supabase.table("usage_logs") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(5000)
        if since:
            q = q.gte("created_at", since)
        if user_id:
            q = q.eq("user_id", user_id)
        return q.execute().data or []
    except Exception as e:
        print(f"Could not load token usage: {e}")
        return []


def get_token_summary_by_client(since: str | None = None) -> list[dict]:
    """
    Aggregate token usage per client.
    Returns list of dicts with user_id, client_id, total_tokens, total_cost_usd, call_count.
    """
    try:
        rows = load_token_usage(since=since)
        summary: dict[str, dict] = {}
        for row in rows:
            key = row.get("client_id") or row.get("user_id", "unknown")
            if key not in summary:
                summary[key] = {
                    "user_id":       row.get("user_id"),
                    "client_id":     row.get("client_id"),
                    "total_tokens":  0,
                    "total_cost_usd": 0.0,
                    "call_count":    0,
                    "by_feature":    {},
                }
            s = summary[key]
            s["total_tokens"]   += row.get("total_tokens", 0)
            s["total_cost_usd"] += float(row.get("cost_usd", 0))
            s["call_count"]     += 1
            feat = row.get("feature", "unknown")
            s["by_feature"][feat] = s["by_feature"].get(feat, 0) + row.get("total_tokens", 0)
        return list(summary.values())
    except Exception as e:
        print(f"Could not compute token summary: {e}")
        return []
