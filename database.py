import os
import uuid
from datetime import datetime, timezone
from supabase import create_client, Client

# ── Supabase clients ──────────────────────────────────────────────────────────

def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)

def get_supabase_admin() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


# ── Profiles & roles ──────────────────────────────────────────────────────────

def get_user_profile(user_id: str) -> dict:
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
    profile = get_user_profile(user_id)
    return profile.get("role") == "admin"

def get_all_profiles() -> list[dict]:
    try:
        supabase = get_supabase_admin()
        res = supabase.table("profiles") \
            .select("*") \
            .order("created_at", desc=True) \
            .execute()
        return res.data or []
    except Exception:
        return []


# ── Clients ───────────────────────────────────────────────────────────────────

def get_client(user_id: str) -> dict:
    try:
        supabase = get_supabase_admin()
        res = supabase.table("clients") \
            .select("*") \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        return res.data or {}
    except Exception:
        return {}

def upsert_client(user_id: str, data: dict) -> bool:
    try:
        supabase = get_supabase_admin()
        supabase.table("clients") \
            .upsert({"user_id": user_id, **data}) \
            .execute()
        return True
    except Exception:
        return False


# ── Chat history ──────────────────────────────────────────────────────────────

def save_chat_message(user_id: str, role: str, content: str) -> bool:
    try:
        supabase = get_supabase_admin()
        supabase.table("chat_history").insert({
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception:
        return False

def load_chat_history(user_id: str, limit: int = 50) -> list[dict]:
    try:
        supabase = get_supabase_admin()
        res = supabase.table("chat_history") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=False) \
            .limit(limit) \
            .execute()
        return res.data or []
    except Exception:
        return []


# ── Client documents ──────────────────────────────────────────────────────────

def save_client_document(user_id: str, doc: dict) -> str | None:
    try:
        supabase = get_supabase_admin()
        # Mark all existing current docs of same type as not current
        supabase.table("client_documents") \
            .update({"is_current": False}) \
            .eq("user_id", user_id) \
            .eq("doc_type", doc["doc_type"]) \
            .execute()
        res = supabase.table("client_documents").insert({
            "user_id": user_id,
            "is_current": True,
            **doc,
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        print(f"Could not save document: {e}")
        return None

def load_client_documents(user_id: str, current_only: bool = True) -> list[dict]:
    try:
        supabase = get_supabase_admin()
        q = supabase.table("client_documents") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True)
        if current_only:
            q = q.eq("is_current", True)
        return q.execute().data or []
    except Exception:
        return []


# ── Regulatory updates ────────────────────────────────────────────────────────

def save_regulatory_update(update: dict) -> str | None:
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
    try:
        supabase = get_supabase_admin()
        supabase.table("regulatory_updates") \
            .update({"status": "rejected"}) \
            .eq("id", update_id) \
            .execute()
        return True
    except Exception:
        return False


# ── Client alerts ─────────────────────────────────────────────────────────────

def create_client_alerts(update_id: str, update: dict) -> int:
    """Create alerts for all clients whose regulations match this update.
    Returns number of alerts created."""
    try:
        supabase = get_supabase_admin()
        clients_res = supabase.table("clients").select("user_id, regulations").execute()
        clients = clients_res.data or []

        update_regulation = update.get("regulation", "").upper()
        created = 0
        for client in clients:
            client_regs = [r.upper() for r in (client.get("regulations") or [])]
            if not client_regs or update_regulation in client_regs or update_regulation == "GENERAL":
                supabase.table("client_alerts").insert({
                    "user_id": client["user_id"],
                    "update_id": update_id,
                    "is_read": False,
                    "created_at": datetime.utcnow().isoformat(),
                }).execute()
                created += 1
        return created
    except Exception as e:
        print(f"Could not create client alerts: {e}")
        return 0

def load_client_alerts(user_id: str) -> list[dict]:
    try:
        supabase = get_supabase_admin()
        res = supabase.table("client_alerts") \
            .select("*, regulatory_updates(*)") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .execute()
        return res.data or []
    except Exception:
        return []

def mark_alert_read(alert_id: str) -> bool:
    try:
        supabase = get_supabase_admin()
        supabase.table("client_alerts") \
            .update({"is_read": True}) \
            .eq("id", alert_id) \
            .execute()
        return True
    except Exception:
        return False

def get_unread_alert_count(user_id: str) -> int:
    try:
        supabase = get_supabase_admin()
        res = supabase.table("client_alerts") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .eq("is_read", False) \
            .execute()
        return res.count or 0
    except Exception:
        return 0


# ── Sprint 12: Qdrant ingestion of approved alerts ────────────────────────────

def _fetch_article_text(url: str, timeout: int = 10) -> str | None:
    """
    Attempt to fetch full article text from a URL.
    Returns cleaned text or None if fetch fails / is blocked.
    EUR-Lex and some other sources block bots — we catch those gracefully.
    """
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

        # Remove nav, footer, scripts, styles
        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()

        # Try common article content selectors
        for selector in ["article", "main", ".content", "#content", ".document-content"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 300:
                    return text

        # Fallback: full body text
        text = soup.get_text(separator="\n", strip=True)
        return text if len(text) > 300 else None

    except Exception as e:
        print(f"Could not fetch article text from {url}: {e}")
        return None


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks by word count.
    chunk_size: target words per chunk
    overlap: words shared between consecutive chunks
    """
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
    """
    Embed a list of texts using Mistral mistral-embed.
    Returns list of embedding vectors or None on failure.
    """
    try:
        import requests

        api_key = os.environ["MISTRAL_API_KEY"]
        resp = requests.post(
            "https://api.mistral.ai/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": "mistral-embed", "input": texts},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]
    except Exception as e:
        print(f"Embedding failed: {e}")
        return None


def _upsert_to_qdrant(points: list[dict]) -> bool:
    """
    Upsert a list of points into Qdrant.
    Each point: {id, vector, payload}
    """
    try:
        import requests

        qdrant_url  = os.environ["QDRANT_URL"]
        qdrant_key  = os.environ["QDRANT_API_KEY"]
        collection  = os.environ.get("QDRANT_COLLECTION", "complai_kb")

        resp = requests.put(
            f"{qdrant_url}/collections/{collection}/points",
            headers={
                "api-key": qdrant_key,
                "Content-Type": "application/json",
            },
            json={"points": points},
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"Qdrant upsert failed: {e}")
        return False


def ingest_alert_to_qdrant(update: dict) -> dict:
    """
    Ingest an approved regulatory alert into Qdrant.

    Strategy (Option 3 with graceful fallback):
    1. Always embed the Mistral summary as a standalone high-signal chunk.
    2. Try to fetch full article text from update URL.
       - If successful: chunk + embed + upsert all chunks.
       - If blocked/failed: fall back to summary only.

    Returns a status dict:
    {
        "success": bool,
        "summary_ingested": bool,
        "full_text_ingested": bool,
        "chunks_ingested": int,
        "error": str | None,
    }
    """
    result = {
        "success": False,
        "summary_ingested": False,
        "full_text_ingested": False,
        "chunks_ingested": 0,
        "error": None,
    }

    update_id  = update.get("id", str(uuid.uuid4()))
    summary    = update.get("summary", "").strip()
    url        = update.get("url", "")
    source     = update.get("source", "")
    regulation = update.get("regulation", "general")
    country    = update.get("country", "EU")
    detected   = update.get("detected_at", datetime.utcnow().isoformat())
    title      = update.get("title", "Regulatory Update")

    # Normalise regulation to match existing KB metadata style
    reg_map = {
        "gdpr": "GDPR",
        "nis2": "NIS2",
        "eu ai act": "EU_AI_ACT",
        "eu_ai_act": "EU_AI_ACT",
        "general": "general",
    }
    regulation_norm = reg_map.get(regulation.lower(), regulation.upper())

    if not summary:
        result["error"] = "No summary available — cannot ingest"
        return result

    points = []

    # ── 1. Summary chunk (always) ─────────────────────────────────────────────
    summary_embedding = _embed_texts([summary])
    if not summary_embedding:
        result["error"] = "Embedding failed for summary"
        return result

    points.append({
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{update_id}:summary")),
        "vector": summary_embedding[0],
        "payload": {
            "text": summary,
            "source": source,
            "url": url,
            "title": title,
            "language": "en",
            "country": country,
            "doc_type": "supplementary",
            "parent_regulation": regulation_norm,
            "type": "regulatory_update",
            "alert_id": update_id,
            "detected_at": detected,
            "chunk_type": "summary",
        },
    })
    result["summary_ingested"] = True

    # ── 2. Full article text (best effort) ────────────────────────────────────
    if url:
        article_text = _fetch_article_text(url)
        if article_text:
            chunks = _chunk_text(article_text, chunk_size=500, overlap=50)

            # Embed in batches of 10 to stay within API limits
            batch_size = 10
            all_embeddings = []
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                embeddings = _embed_texts(batch)
                if embeddings:
                    all_embeddings.extend(embeddings)
                else:
                    # Partial failure — skip remaining batches
                    print(f"Embedding batch {i//batch_size + 1} failed, stopping")
                    break

            for idx, (chunk, vector) in enumerate(zip(chunks, all_embeddings)):
                points.append({
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{update_id}:chunk:{idx}")),
                    "vector": vector,
                    "payload": {
                        "text": chunk,
                        "source": source,
                        "url": url,
                        "title": title,
                        "language": "en",
                        "country": country,
                        "doc_type": "supplementary",
                        "parent_regulation": regulation_norm,
                        "type": "regulatory_update",
                        "alert_id": update_id,
                        "detected_at": detected,
                        "chunk_type": "full_text",
                        "chunk_index": idx,
                    },
                })
            result["full_text_ingested"] = len(all_embeddings) > 0
        else:
            print(f"Full article fetch failed for {url} — using summary only")

    # ── 3. Upsert all points to Qdrant ────────────────────────────────────────
    if points:
        success = _upsert_to_qdrant(points)
        if success:
            result["success"] = True
            result["chunks_ingested"] = len(points)
        else:
            result["error"] = "Qdrant upsert failed"
    else:
        result["error"] = "No points to upsert"

    return result


def mark_alert_ingested(update_id: str, chunks_count: int) -> bool:
    """
    Mark a regulatory update as ingested into Qdrant.
    Stores ingestion timestamp and chunk count for auditability.
    """
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
