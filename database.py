import os
import uuid
import streamlit as st
from datetime import datetime, timezone
from supabase import create_client, Client

# Sentinel UUID for system/monitoring processes (no authenticated user)
# user_id column in usage_logs must be nullable for this to work:
#   ALTER TABLE public.usage_logs ALTER COLUMN user_id DROP NOT NULL;
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


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
    """Get current version of each document type for a client."""
    try:
        supabase = get_supabase()
        res = supabase.table("client_documents") \
            .select("*") \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .eq("is_current", True) \
            .execute()
        return {r["document_type"]: r for r in (res.data or [])}
    except Exception:
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
        res = supabase.table("client_documents") \
            .select("version") \
            .eq("client_id", client_id) \
            .eq("document_type", document_type) \
            .eq("is_current", True) \
            .execute()
        current_version = res.data[0]["version"] if res.data else 0
        new_version = current_version + 1
        if current_version > 0:
            supabase.table("client_documents") \
                .update({"is_current": False}) \
                .eq("client_id", client_id) \
                .eq("user_id", user_id) \
                .eq("document_type", document_type) \
                .execute()
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
    except Exception:
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


# ── Qdrant ingestion ──────────────────────────────────────────────────────────

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
        rdata = resp.json()
        _usage = rdata.get("usage", {})
        try:
            log_token_usage(
                user_id=SYSTEM_USER_ID,
                feature="embedding",
                client_id=None,
                input_tokens=_usage.get("prompt_tokens", 0),
                output_tokens=0,
                model="mistral-embed",
            )
        except Exception:
            pass
        return [item["embedding"] for item in rdata["data"]]
    except Exception as e:
        print(f"Embedding failed: {e}")
        return None


def _upsert_to_qdrant(points: list[dict]) -> tuple[bool, str | None]:
    """Upsert points into Qdrant collection."""
    try:
        import requests as req
        qdrant_url = os.environ["QDRANT_URL"]
        qdrant_key = os.environ["QDRANT_API_KEY"]
        collection = os.environ.get("QDRANT_COLLECTION", "regulations")
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
    """Ingest an approved regulatory alert into Qdrant."""
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


# ── Token usage logging ───────────────────────────────────────────────────────

_MISTRAL_INPUT_COST_PER_M  = 2.00
_MISTRAL_OUTPUT_COST_PER_M = 6.00


def log_token_usage(
    user_id: str | None,
    feature: str,
    input_tokens: int,
    output_tokens: int,
    client_id: str | None = None,
    model: str = "mistral-large-latest",
) -> bool:
    """
    Log a Mistral API call's token usage to usage_logs.
    Pass user_id=SYSTEM_USER_ID for monitoring/cron calls.
    Pass user_id=None for truly anonymous calls (inserts without user_id).
    """
    try:
        total = input_tokens + output_tokens
        if total == 0:
            return True
        if model == "mistral-embed":
            cost = (input_tokens / 1_000_000) * 0.10
        else:
            cost = (
                (input_tokens  / 1_000_000) * _MISTRAL_INPUT_COST_PER_M +
                (output_tokens / 1_000_000) * _MISTRAL_OUTPUT_COST_PER_M
            )
        row = {
            "feature":       feature,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  total,
            "cost_usd":      round(cost, 6),
        }
        # Only set user_id if it's a valid non-system value
        # SYSTEM_USER_ID is a valid UUID sentinel for monitoring processes
        if user_id and user_id not in ("system",):
            row["user_id"] = user_id
        if client_id:
            row["client_id"] = client_id
        supabase = get_supabase_admin()
        supabase.table("usage_logs").insert(row).execute()
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
    """Aggregate token usage per client."""
    try:
        rows = load_token_usage(since=since)
        summary: dict[str, dict] = {}
        for row in rows:
            key = row.get("client_id") or row.get("user_id", "unknown")
            if key not in summary:
                summary[key] = {
                    "user_id":        row.get("user_id"),
                    "client_id":      row.get("client_id"),
                    "total_tokens":   0,
                    "total_cost_usd": 0.0,
                    "call_count":     0,
                    "by_feature":     {},
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


# ── S17: Monitoring sources (dynamic, from DB) ────────────────────────────────

def load_monitoring_sources(monitor_type: str | None = None) -> list[dict]:
    """
    Load active monitoring sources from the monitoring_sources table.
    monitor_type: 'regulatory' | 'marketing' | None (all)
    Returns list of source dicts ready for use in monitor scripts.
    """
    try:
        supabase = get_supabase_admin()
        q = supabase.table("monitoring_sources") \
            .select("*") \
            .eq("active", True) \
            .order("name")
        if monitor_type:
            q = q.eq("monitor_type", monitor_type)
        return q.execute().data or []
    except Exception as e:
        print(f"Could not load monitoring sources: {e}")
        return []


def save_monitoring_source(source: dict) -> str | None:
    """Create a new monitoring source. Returns id on success."""
    try:
        supabase = get_supabase_admin()
        res = supabase.table("monitoring_sources").insert({
            "name":             source["name"],
            "url":              source.get("url"),
            "fetch_type":       source.get("fetch_type", "rss"),
            "monitor_type":     source.get("monitor_type", "regulatory"),
            "category":         source.get("category", ""),
            "query":            source.get("query"),
            "regulations":      source.get("regulations", []),
            "countries":        source.get("countries", []),
            "filter_keywords":  source.get("filter_keywords", []),
            "active":           source.get("active", True),
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        print(f"Could not save monitoring source: {e}")
        return None


def update_monitoring_source(source_id: str, updates: dict) -> bool:
    """Update a monitoring source."""
    try:
        supabase = get_supabase_admin()
        supabase.table("monitoring_sources") \
            .update(updates) \
            .eq("id", source_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Could not update monitoring source: {e}")
        return False


def delete_monitoring_source(source_id: str) -> bool:
    """Delete a monitoring source."""
    try:
        supabase = get_supabase_admin()
        supabase.table("monitoring_sources") \
            .delete() \
            .eq("id", source_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Could not delete monitoring source: {e}")
        return False


# ── S17: Marketing updates ────────────────────────────────────────────────────

def save_marketing_update(update: dict) -> str | None:
    """Save a new marketing update. Returns id if saved, None if duplicate."""
    try:
        supabase = get_supabase_admin()
        # Deduplication handled by url_hash unique constraint in DB
        res = supabase.table("marketing_updates") \
            .insert(update) \
            .execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        err_str = str(e)
        if "unique" in err_str.lower() or "duplicate" in err_str.lower():
            return None  # Duplicate — silently skip
        print(f"Could not save marketing update: {e}")
        return None


def load_marketing_updates(status: str | None = None,
                            category: str | None = None) -> list[dict]:
    """Load marketing updates, optionally filtered by status and/or category."""
    try:
        supabase = get_supabase_admin()
        q = supabase.table("marketing_updates") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(100)
        if status:
            q = q.eq("status", status)
        if category:
            q = q.eq("category", category)
        return q.execute().data or []
    except Exception:
        return []


def approve_marketing_update(update_id: str, publish_to_pulse: bool = False) -> bool:
    """Approve a marketing update, optionally publishing to Compliance Pulse."""
    try:
        supabase = get_supabase_admin()
        supabase.table("marketing_updates") \
            .update({
                "status": "approved",
                "published_to_pulse": publish_to_pulse,
            }) \
            .eq("id", update_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Could not approve marketing update: {e}")
        return False


def reject_marketing_update(update_id: str) -> bool:
    """Reject a marketing update."""
    try:
        supabase = get_supabase_admin()
        supabase.table("marketing_updates") \
            .update({"status": "rejected"}) \
            .eq("id", update_id) \
            .execute()
        return True
    except Exception:
        return False


def save_linkedin_draft(update_id: str, draft: str,
                         table: str = "marketing_updates") -> bool:
    """Save a LinkedIn draft to a marketing or regulatory update."""
    try:
        supabase = get_supabase_admin()
        supabase.table(table) \
            .update({"linkedin_draft": draft}) \
            .eq("id", update_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Could not save LinkedIn draft: {e}")
        return False


# ── S17: Monitor runs ─────────────────────────────────────────────────────────

def start_monitor_run(monitor_type: str, triggered_by: str = "manual") -> str | None:
    """
    Log the start of a monitoring run.
    Returns run_id to pass to complete_monitor_run().
    """
    try:
        supabase = get_supabase_admin()
        res = supabase.table("monitor_runs").insert({
            "monitor_type": monitor_type,
            "triggered_by": triggered_by,
            "status":       "running",
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        print(f"Could not start monitor run: {e}")
        return None


def complete_monitor_run(
    run_id: str,
    total_fetched: int,
    total_saved: int,
    total_skipped: int,
    total_errors: int,
    source_stats: list,
    token_usage: dict,
    status: str = "completed",
    error_message: str | None = None,
) -> bool:
    """Log the completion of a monitoring run."""
    try:
        supabase = get_supabase_admin()
        completed_at = datetime.now(timezone.utc).isoformat()

        # Compute duration by fetching started_at
        run = supabase.table("monitor_runs") \
            .select("started_at") \
            .eq("id", run_id) \
            .single() \
            .execute()
        duration = None
        if run.data:
            started = datetime.fromisoformat(run.data["started_at"])
            completed = datetime.fromisoformat(completed_at)
            duration = int((completed - started).total_seconds())

        supabase.table("monitor_runs").update({
            "completed_at":    completed_at,
            "duration_seconds": duration,
            "total_fetched":   total_fetched,
            "total_saved":     total_saved,
            "total_skipped":   total_skipped,
            "total_errors":    total_errors,
            "source_stats":    source_stats,
            "token_usage":     token_usage,
            "status":          status,
            "error_message":   error_message,
        }).eq("id", run_id).execute()
        return True
    except Exception as e:
        print(f"Could not complete monitor run: {e}")
        return False


def load_monitor_runs(monitor_type: str | None = None, limit: int = 20) -> list[dict]:
    """Load recent monitor runs for admin BO display."""
    try:
        supabase = get_supabase_admin()
        q = supabase.table("monitor_runs") \
            .select("*") \
            .order("started_at", desc=True) \
            .limit(limit)
        if monitor_type:
            q = q.eq("monitor_type", monitor_type)
        return q.execute().data or []
    except Exception:
        return []
