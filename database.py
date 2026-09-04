import os
import uuid
from datetime import datetime, timezone
from supabase import create_client, Client

# Lazy Streamlit import — only available in Streamlit UI context.
# GitHub Actions cron scripts must not trigger this import.
def _st():
    import streamlit as st
    return st

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    client = create_client(url, key)
    # Pass the user's session token so RLS policies are applied correctly
    token = _st().session_state.get("access_token")
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
        _st().error(f"Could not load clients: {e}")
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
        _st().error(f"Could not create client: {e}")
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
        _st().error(f"Could not update client: {e}")
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
        _st().error(f"Could not delete client: {e}")
        return False


# ── Chat history ──────────────────────────────────────────────────────────────

def load_chat_history(client_id: str, user_id: str,
                      session_id: str | None = None) -> list[dict]:
    """Load chat history for a client, ordered chronologically.

    If session_id is given, only that conversation is returned.
    Otherwise all messages for the client are returned (legacy behaviour).

    Each returned dict has: role, content, sources (list, possibly empty).
    """
    try:
        supabase = get_supabase()
        query = supabase.table("chat_history") \
            .select("id, role, content, sources, session_id, created_at") \
            .eq("client_id", client_id) \
            .eq("user_id", user_id)
        if session_id:
            query = query.eq("session_id", session_id)
        res = query.order("created_at").execute()

        rows = res.data or []
        # Normalise sources to a list so callers never have to null-check.
        for r in rows:
            if not isinstance(r.get("sources"), list):
                r["sources"] = []
        return rows
    except Exception as e:
        _st().error(f"Could not load chat history: {e}")
        return []


def load_chat_sessions(client_id: str, user_id: str) -> list[dict]:
    """Return one summary row per conversation, most recent first.

    Shape: session_id, title, message_count, started_at, last_at.

    Aggregation happens in Python rather than SQL: PostgREST has no GROUP BY,
    and per-client message volumes are small enough that fetching and folding
    is cheaper than maintaining an RPC.
    """
    try:
        supabase = get_supabase()
        res = supabase.table("chat_history") \
            .select("session_id, role, content, created_at") \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .order("created_at") \
            .execute()

        rows = res.data or []
        sessions: dict[str, dict] = {}

        for r in rows:
            sid = r.get("session_id")
            if not sid:
                continue
            s = sessions.get(sid)
            if s is None:
                s = {
                    "session_id":    sid,
                    "title":         None,
                    "message_count": 0,
                    "started_at":    r.get("created_at"),
                    "last_at":       r.get("created_at"),
                }
                sessions[sid] = s

            s["message_count"] += 1
            s["last_at"] = r.get("created_at")
            # Title = first user message in the conversation.
            if s["title"] is None and r.get("role") == "user":
                content = (r.get("content") or "").strip()
                s["title"] = content or "Untitled conversation"

        result = list(sessions.values())
        for s in result:
            if not s["title"]:
                s["title"] = "Untitled conversation"

        result.sort(key=lambda s: s["last_at"] or "", reverse=True)
        return result
    except Exception as e:
        _st().error(f"Could not load conversations: {e}")
        return []


def save_message(client_id: str, user_id: str, role: str, content: str,
                 session_id: str | None = None,
                 sources: list[dict] | None = None) -> str | None:
    """Save a single message to chat history. Returns the new row id.

    Returns the id (not a bool) so callers can attach per-answer feedback to
    a message that has just been generated, not only to reloaded history.
    The return value is still truthy/falsy-compatible with the old contract.

    session_id is required by the schema (NOT NULL). It defaults to None here
    so that any caller not yet updated fails soft — a fresh uuid is minted
    rather than raising — but callers should always pass the active session.
    """
    try:
        supabase = get_supabase()
        res = supabase.table("chat_history").insert({
            "client_id":  client_id,
            "user_id":    user_id,
            "role":       role,
            "content":    content,
            "session_id": session_id or str(uuid.uuid4()),
            "sources":    sources or [],
        }).execute()
        rows = res.data or []
        return rows[0].get("id") if rows else None
    except Exception as e:
        _st().error(f"Could not save message: {e}")
        return None


def delete_chat_session(client_id: str, user_id: str, session_id: str) -> bool:
    """Delete a single conversation."""
    try:
        supabase = get_supabase()
        supabase.table("chat_history") \
            .delete() \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .eq("session_id", session_id) \
            .execute()
        return True
    except Exception as e:
        _st().error(f"Could not delete conversation: {e}")
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
        _st().error(f"Could not clear chat history: {e}")
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
        _st().warning(f"Could not upload file to storage: {e}")
        return None


def delete_file(bucket: str, path: str) -> bool:
    """Remove one object from Supabase Storage.

    Service role, like upload_file: storage policies are written for uploads
    from the app, and a delete that silently no-ops leaves the file behind
    while the caller believes it is gone.
    """
    try:
        get_supabase_admin().storage.from_(bucket).remove([path])
        return True
    except Exception as e:
        print(f"Could not delete {bucket}/{path}: {e}")
        return False


def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str | None:
    """Get a temporary signed URL for a private file."""
    try:
        supabase = get_supabase_admin()
        res = supabase.storage.from_(bucket).create_signed_url(path, expires_in)
        return res.get("signedURL") or res.get("signed_url")
    except Exception as e:
        _st().warning(f"Could not get signed URL: {e}")
        return None


def update_document_paths(doc_id: str, user_id: str,
                           file_path_docx: str | None,
                           file_path_pdf: str | None,
                           file_path_odt: str | None = None,
                           file_path_xlsx: str | None = None) -> bool:
    """Save storage paths back to documents table.

    S26 adds xlsx. One documents row can carry several representations of the
    SAME record (D-29) — never one row per format, or S27 tracks two adoption
    states for one document.

    Keyword-safe: xlsx is last and optional, so existing positional callers are
    unaffected.
    """
    try:
        supabase = get_supabase()
        update = {}
        if file_path_docx:
            update["file_path_docx"] = file_path_docx
        if file_path_pdf:
            update["file_path_pdf"] = file_path_pdf
        if file_path_odt:
            update["file_path_odt"] = file_path_odt
        if file_path_xlsx:
            update["file_path_xlsx"] = file_path_xlsx
        if not update:
            return False
        supabase.table("documents") \
            .update(update) \
            .eq("id", doc_id) \
            .eq("user_id", user_id) \
            .execute()
        return True
    except Exception as e:
        _st().warning(f"Could not update document paths: {e}")
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
        _st().warning(f"Could not update audit path: {e}")
        return False


def load_document_files(user_id: str, client_id: str | None) -> list[dict]:
    """Load document records with file paths for history display."""
    try:
        supabase = get_supabase()
        q = supabase.table("documents") \
            .select("id, document_type, language, company_name, generated_at, "
                    "file_path_docx, file_path_pdf, file_path_odt, "
                    "file_path_xlsx, outstanding_fields, document_group_id") \
            .eq("user_id", user_id) \
            .order("generated_at", desc=True) \
            .limit(20)
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception as e:
        _st().warning(f"Could not load document history: {e}")
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

def get_current_client_documents(
    client_id: str, user_id: str, language: str | None = None,
) -> dict:
    """In-force document per doc_type for a client. Shape unchanged.

    S27 added language to the register key, so a doc_type can now have several
    in-force rows — one per language. This still returns one per doc_type,
    because gap scoring and the dashboard both assume that shape and changing
    it is a separate migration.

    Which one: the requested language if present, else whichever came back
    first. A gap assessment scores the CONTENT of a policy, and the French and
    English versions of the same adopted policy say the same thing — so for
    scoring purposes the choice is not material. For the per-language dashboard
    rollup, use get_register_status() instead, which returns all of them.
    """
    try:
        rows = (get_supabase().table("client_documents").select("*")
                .eq("client_id", client_id).eq("user_id", user_id)
                .eq("status", "in_force").execute().data or [])
        out: dict = {}
        for r in rows:
            dt = r["document_type"]
            if dt not in out or (language and r.get("language") == language):
                out[dt] = r
        return out
    except Exception:
        return {}


def get_register_status(client_id: str, user_id: str) -> dict:
    """Every register row grouped as {doc_type: {language: row}}.

    The per-language view the dashboard rollup needs: "Privacy Policy — in
    force (FR), outdated (EN), not available (NL)". Includes drafts, so a
    generated-but-not-adopted document shows as present-and-not-adopted rather
    than missing — the distinction that stops the S27 adoption step reading as
    a score regression.
    """
    try:
        rows = (get_supabase().table("client_documents").select("*")
                .eq("client_id", client_id).eq("user_id", user_id)
                .in_("status", ["draft", "in_force"])
                .order("uploaded_at", desc=True).execute().data or [])
        out: dict = {}
        for r in rows:
            per_lang = out.setdefault(r["document_type"], {})
            existing = per_lang.get(r["language"])
            # in_force beats draft; otherwise the most recent draft wins.
            if existing is None or (
                existing["status"] == "draft" and r["status"] == "in_force"
            ):
                per_lang[r["language"]] = r
        return out
    except Exception:
        return {}


def get_client_document_history(
    client_id: str, user_id: str, document_type: str,
    language: str | None = None,
) -> list[dict]:
    """Full history for a doc_type, newest first.

    Ordered by uploaded_at, not version: drafts carry no version number (S27),
    and ordering by a NULL column drops them or scatters them depending on the
    backend. The history view is also where a client sees their drafts.
    """
    try:
        q = (get_supabase().table("client_documents").select("*")
             .eq("client_id", client_id).eq("user_id", user_id)
             .eq("document_type", document_type))
        if language:
            q = q.eq("language", language)
        return q.order("uploaded_at", desc=True).execute().data or []
    except Exception:
        return []


# Document source values written to client_documents.source.
#
# APPEND-ONLY, same rule as the reference vocabularies: client rows hold these
# as plain text, so a renamed value orphans every row that carries it.
# "complai_generated" was written by every generation before S26 and is
# deliberately NOT backfilled — it is the honest record of what produced those
# documents.
DOCUMENT_SOURCES = {
    "recosa_generated": "Generated by RECOSA",
    "complai_generated": "Generated by RECOSA (recorded under the former name)",
    "client_upload": "Uploaded by the client",
    "client_modified": "Generated by RECOSA, then modified by the client",
    "client_supplied": "Supplied by the client",
}


def document_source_label(source: str | None) -> str:
    """Readable label for a source value, live or historical."""
    if not source:
        return "Unknown"
    return DOCUMENT_SOURCES.get(source, source)


# ── S27: register statuses ────────────────────────────────────────────────
#
# APPEND-ONLY, same rule as DOCUMENT_SOURCES above.
#
# 'withdrawn' was considered and rejected: an abandoned draft is deleted, and a
# status that only ever applies to documents nobody used adds a state to every
# query for no benefit.
DOCUMENT_STATUSES = {
    "draft":      "Draft — not yet adopted",
    "in_force":   "In force",
    "superseded": "Superseded",
    "archived":   "Archived — no longer applicable",
}

# Retention of superseded versions, in years after they cease to apply.
#
# NOT A STATUTORY PERIOD. There is no GDPR rule stating how long a superseded
# transparency notice must be kept; the requirement is Art. 5(2) accountability
# — the client must be able to demonstrate what information it provided at the
# time the processing took place. Five years is a risk-management working
# figure, shown to the client with its reasoning rather than asserted as law
# (D-50, D-51), and configurable per deployment.
#
# VERIFY BEFORE BETA: the Belgian DPA is reported to expect previous cookie
# policy versions to be retained, dated and version-numbered. Confirm against
# the primary source before this figure is presented to a client as guidance.
SUPERSEDED_RETENTION_YEARS = int(
    os.environ.get("SUPERSEDED_RETENTION_YEARS", "5")
)


def register_client_document(
    user_id: str,
    client_id: str,
    document_type: str,
    file_path: str,
    source: str = "client_upload",
    change_comment: str = "",
    language: str = "en",
    document_id: str | None = None,
    template_version_id: str | None = None,
    source_revision: int | None = None,
) -> str | None:
    """Record a document as a DRAFT. Returns the new row id, or None.

    S27: this no longer adopts. Generating a document is not the same event as
    beginning to operate under it — a DPA nobody has signed is not in force,
    and the register asserting otherwise from the moment of generation was
    simply false.

    It also no longer assigns a version. Version numbers are public facts that
    appear on the document, and three discarded drafts consuming v4, v5 and v6
    leave a published sequence reading v3 -> v7 with no explanation for the
    gap. Numbering happens in adopt_client_document().

    Callers that want the old behaviour — generate and immediately operate
    under it — call adopt_client_document() straight after. That is a decision
    they now have to make explicitly, which is the point.
    """
    try:
        res = get_supabase().table("client_documents").insert({
            "user_id": user_id,
            "client_id": client_id,
            "document_type": document_type,
            "language": language,
            "status": "draft",
            "version": None,
            "file_path": file_path,
            "source": source,
            "change_comment": change_comment,
            "document_id": document_id,
            "template_version_id": template_version_id,
            "source_revision": source_revision,
        }).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as e:
        print(f"Could not register document draft: {e}")
        return None


def adopt_client_document(
    document_row_id: str,
    user_id: str,
    effective_from: "date | None" = None,
    published_at: "date | None" = None,
    change_comment: str | None = None,
) -> dict | None:
    """Move a draft to in_force, superseding whatever it replaces.

    Explicit supersede-then-insert, NEVER an upsert: the one-in-force rule is a
    partial unique index, and partial indexes cannot serve as ON CONFLICT
    arbiters (42P10).

    Order matters. The predecessor is superseded FIRST, because the index
    rejects two in_force rows for the same key — doing it the other way round
    fails on every adoption after the first.

    Not atomic. PostgREST has no transaction across calls, so a failure between
    the two writes leaves a key with no in_force document: visible, wrong, and
    fixable by re-adopting. The alternative is a Postgres function, which is
    the right answer if this ever runs concurrently for one client — noted
    rather than built, because today it does not.
    """
    from datetime import date as _date
    try:
        supabase = get_supabase()

        row = (supabase.table("client_documents").select("*")
               .eq("id", document_row_id).eq("user_id", user_id)
               .execute().data or [None])[0]
        if not row:
            return None
        if row["status"] != "draft":
            # Already adopted, or superseded. Not an error worth raising — the
            # client pressed a button twice — but not a second adoption either.
            return row

        effective = effective_from or _date.today()

        # The predecessor, if any.
        prev = (supabase.table("client_documents").select("id, version")
                .eq("client_id", row["client_id"])
                .eq("document_type", row["document_type"])
                .eq("language", row["language"])
                .eq("status", "in_force")
                .execute().data or [None])[0]

        if prev:
            # superseded_on equals the successor's effective_from rather than
            # being set independently: two dates set by hand produce gaps or
            # overlaps in the timeline, and both are wrong when an auditor asks
            # what applied in March.
            retain_until = _date(
                effective.year + SUPERSEDED_RETENTION_YEARS,
                effective.month, effective.day,
            )
            supabase.table("client_documents").update({
                "status": "superseded",
                "superseded_on": effective.isoformat(),
                "superseded_by": document_row_id,
                "retain_until": retain_until.isoformat(),
            }).eq("id", prev["id"]).execute()

        # Dense sequence: the highest version ever issued for this key, not the
        # count of rows, so a deleted draft cannot renumber anything.
        highest = (supabase.table("client_documents").select("version")
                   .eq("client_id", row["client_id"])
                   .eq("document_type", row["document_type"])
                   .eq("language", row["language"])
                   .not_.is_("version", "null")
                   .order("version", desc=True).limit(1)
                   .execute().data or [{}])
        next_version = (highest[0].get("version") or 0) + 1 if highest else 1

        patch = {
            "status": "in_force",
            "version": next_version,
            "adopted_at": datetime.utcnow().isoformat(),
            "effective_from": effective.isoformat(),
        }
        if published_at:
            patch["published_at"] = published_at.isoformat()
        if change_comment is not None:
            patch["change_comment"] = change_comment

        updated = (supabase.table("client_documents").update(patch)
                   .eq("id", document_row_id).execute().data or [None])[0]

        log_audit_event(
            company_id=row["client_id"],
            user_id=user_id,
            event_type="document",
            event_subtype="adopted",
            resource_id=document_row_id,
            summary=(
                f"{row['document_type']} v{next_version} "
                f"({row['language'].upper()}) in force from "
                f"{effective.isoformat()}"
            ),
            metadata={
                "document_type": row["document_type"],
                "language": row["language"],
                "version": next_version,
                "source": row.get("source"),
                "source_revision": row.get("source_revision"),
                "supersedes_version": (prev or {}).get("version"),
            },
        )
        return updated
    except Exception as e:
        print(f"Could not adopt document: {e}")
        return None


def archive_client_document(
    document_row_id: str, user_id: str, reason: str = "",
) -> bool:
    """Retire an in-force document that nothing replaces.

    Distinct from supersession. A client who stops processing on another
    controller's behalf retires their DPA: nothing takes its place, the
    obligation simply ended. Without this the only way to express it is a
    supersession chain pointing at nothing.
    """
    from datetime import date as _date
    try:
        supabase = get_supabase()
        row = (supabase.table("client_documents").select("*")
               .eq("id", document_row_id).eq("user_id", user_id)
               .execute().data or [None])[0]
        if not row or row["status"] != "in_force":
            return False
        today = _date.today()
        supabase.table("client_documents").update({
            "status": "archived",
            "superseded_on": today.isoformat(),
            "retain_until": _date(
                today.year + SUPERSEDED_RETENTION_YEARS, today.month, today.day
            ).isoformat(),
            "change_comment": reason or row.get("change_comment") or "",
        }).eq("id", document_row_id).execute()

        log_audit_event(
            company_id=row["client_id"], user_id=user_id,
            event_type="document", event_subtype="archived",
            resource_id=document_row_id,
            summary=(f"{row['document_type']} v{row.get('version')} "
                     f"({row['language'].upper()}) archived"),
            metadata={"reason": reason},
        )
        return True
    except Exception as e:
        print(f"Could not archive document: {e}")
        return False


def get_template_languages() -> dict[str, set]:
    """{doc_type: {languages}} for which an in-force template exists.

    Lets the product tell its own gap apart from the client's. "Not available
    in NL" and "you have not adopted the NL version" look identical on a
    dashboard and are opposite findings: one is RECOSA's work, the other is
    the client's. Showing the second when the first is true blames a client
    for a template that was never written.

    documents.py currently infers this by subtracting generated languages from
    the client's list, which is a guess. This is the fact.
    """
    try:
        rows = (get_supabase().table("document_template_versions")
                .select("language, status, document_templates(doc_type)")
                .eq("status", "in_force").execute().data or [])
        out: dict[str, set] = {}
        for r in rows:
            dt = ((r.get("document_templates") or {}) or {}).get("doc_type")
            if dt and r.get("language"):
                out.setdefault(dt, set()).add(r["language"].lower())
        return out
    except Exception as e:
        print(f"Could not read template languages: {e}")
        return {}


def get_latest_draft(
    client_id: str, user_id: str, document_type: str, language: str,
) -> dict | None:
    """The most recent unadopted draft for one key, or None.

    Generation writes a draft and returns nothing to the page, so the adoption
    control has to find it. Newest first: a client who regenerates twice before
    adopting means the second one.
    """
    try:
        rows = (get_supabase().table("client_documents").select("*")
                .eq("client_id", client_id).eq("user_id", user_id)
                .eq("document_type", document_type)
                .eq("language", language).eq("status", "draft")
                .order("uploaded_at", desc=True).limit(1)
                .execute().data or [])
        return rows[0] if rows else None
    except Exception:
        return None


def delete_draft_document(document_row_id: str, user_id: str) -> bool:
    """Delete an unadopted draft and its file. Refuses anything else.

    A draft carries no version and nothing points at it, so removing one
    leaves no gap in the published sequence and breaks no supersession chain.
    That is the whole reason version numbers are assigned at adoption rather
    than at generation.

    THE STATUS GUARD IS HERE, NOT IN THE UI. An in_force or superseded row is
    the accountability record — the answer to "what were we operating under in
    March" — and the retention and legal-hold work in this sprint exists
    precisely to stop those disappearing. pages/gap.py already writes to this
    table outside the store layer, so a check that lives only in a page is a
    check that can be walked around.

    The storage object goes too. Deleting the row alone would orphan the file:
    invisible in the product, still stored, and still the client's personal
    data. The `documents` generation-log row is deliberately KEPT — that a
    generation happened is true regardless of whether its output was kept.
    """
    try:
        supabase = get_supabase()
        row = (supabase.table("client_documents").select("*")
               .eq("id", document_row_id).eq("user_id", user_id)
               .execute().data or [None])[0]
        if not row:
            return False
        if row.get("status") != "draft":
            print(
                f"Refusing to delete {document_row_id}: status is "
                f"{row.get('status')!r}, not draft."
            )
            return False

        if row.get("file_path"):
            delete_file("compliance-files", row["file_path"])

        supabase.table("client_documents").delete() \
            .eq("id", document_row_id).eq("user_id", user_id).execute()

        # A discarded draft is still something that happened, and the event
        # costs nothing. It is also the only remaining trace once the row and
        # the file are gone.
        log_audit_event(
            company_id=row["client_id"],
            user_id=user_id,
            event_type="document",
            event_subtype="draft_deleted",
            resource_id=document_row_id,
            summary=(
                f"{row['document_type']} draft ({row['language'].upper()}) "
                "deleted before adoption"
            ),
            metadata={
                "document_type": row["document_type"],
                "language": row["language"],
                "source": row.get("source"),
            },
        )
        return True
    except Exception as e:
        print(f"Could not delete draft: {e}")
        return False


def set_document_comment(
    document_row_id: str, user_id: str, comment: str,
) -> bool:
    """Set the change note on one register row.

    Keyed on the row id. pages/gap.py previously updated this by matching
    file_path, which is not a stable key: re-uploading to the same path would
    rewrite the note on the superseded version as well as the current one.
    """
    try:
        get_supabase().table("client_documents") \
            .update({"change_comment": comment}) \
            .eq("id", document_row_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"Could not save change comment: {e}")
        return False


def set_legal_hold(
    document_row_id: str, user_id: str, on: bool, reason: str = "",
) -> bool:
    """Suspend deletion for a document relevant to a live matter.

    Without this, a retention rule deletes the evidence during the proceeding
    that needs it.

    hold_set_on is stamped on set and CLEARED on release, so a hold set again
    later ages from its own start rather than from the first one ever placed.
    S57 reads it to ask, thirty days on, whether the hold is still necessary —
    a hold that outlives its proceeding means retaining personal data past the
    client's own retention period, which is an Art. 5(1)(e) problem rather than
    an untidy one.
    """
    from datetime import datetime as _dt
    try:
        supabase = get_supabase()

        # Read first: the audit event needs what the row looked like BEFORE the
        # change, and hold_set_on is cleared on release — so the duration it
        # was held for exists only in this moment. Without capturing it here, a
        # document that spent two years under hold becomes indistinguishable
        # from one that never was.
        row = (supabase.table("client_documents")
               .select("client_id, document_type, language, version, "
                       "hold_set_on, hold_reason")
               .eq("id", document_row_id).eq("user_id", user_id)
               .execute().data or [None])[0]
        if not row:
            return False

        supabase.table("client_documents").update({
            "legal_hold": on,
            "hold_reason": reason if on else None,
            "hold_set_on": _dt.utcnow().isoformat() if on else None,
        }).eq("id", document_row_id).eq("user_id", user_id).execute()

        # A hold is a statement about live litigation or an investigation, and
        # RELEASING one is what allows the document to be deleted. If that
        # decision is ever questioned, the absence of a record is the problem:
        # nobody can show who decided, when, or on what basis.
        #
        # Adoption, archiving and draft deletion already write events. This was
        # the gap, and it is the one where the trail matters most.
        held_days = None
        if not on and row.get("hold_set_on"):
            try:
                started = _dt.fromisoformat(
                    str(row["hold_set_on"]).replace("Z", "+00:00"))
                held_days = (_dt.now(started.tzinfo) - started).days
            except (ValueError, TypeError):
                held_days = None

        _label = (
            f"{row['document_type']} v{row.get('version') or '—'} "
            f"({(row.get('language') or '').upper()})"
        )
        log_audit_event(
            company_id=row["client_id"],
            user_id=user_id,
            event_type="document",
            event_subtype="hold_set" if on else "hold_released",
            resource_id=document_row_id,
            summary=(
                f"Legal hold placed on {_label}" if on else
                f"Legal hold released on {_label}"
                + (f" after {held_days} day(s)" if held_days is not None else "")
            ),
            metadata={
                "document_type": row["document_type"],
                "language": row.get("language"),
                "version": row.get("version"),
                # Optional on both sides — friction on a control used during a
                # live matter is friction at the worst possible moment — but
                # recorded whenever given, and the reason the hold was
                # originally placed is carried into the release event so the
                # two are readable together.
                "reason": reason or None,
                "hold_reason_at_release": row.get("hold_reason") if not on else None,
                "held_days": held_days,
                "hold_set_on": row.get("hold_set_on"),
            },
        )
        return True
    except Exception as e:
        print(f"Could not set legal hold: {e}")
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
    """Log a Mistral API call's token usage to usage_logs.
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

# ── S21: Audit trail ──────────────────────────────────────────────────────────

def log_audit_event(
    company_id: str,
    event_type: str,
    summary: str,
    user_id: str | None = None,
    event_subtype: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> bool:
    """Write a row to audit_log. Uses service role to bypass RLS on insert,
    since audit_log intentionally has no insert policy for anon/authenticated."""
    try:
        supabase = get_supabase_admin()
        supabase.table("audit_log").insert({
            "company_id": company_id,
            "user_id": user_id,
            "event_type": event_type,
            "event_subtype": event_subtype,
            "resource_id": resource_id,
            "summary": summary,
            "metadata": metadata or {},
        }).execute()
        return True
    except Exception as e:
        print(f"Could not log audit event: {e}")
        return False


# ── S22: Answer feedback ──────────────────────────────────────────────────────

# Beta collects rating + reason codes + comment. Commercial collects rating
# only (plus a separate general suggestion form). One table, two UI depths —
# switched by FEEDBACK_MODE, same pattern as the annual-billing toggle.
FEEDBACK_MODE = os.environ.get("FEEDBACK_MODE", "beta")  # "beta" | "standard"

FEEDBACK_REASONS = [
    ("inaccurate",     "Factually wrong"),
    ("outdated",       "Out of date"),
    ("wrong_reg",      "Cited the wrong regulation"),
    ("incomplete",     "Incomplete answer"),
    ("not_grounded",   "Not supported by the sources"),
    ("unclear",        "Hard to understand"),
    ("wrong_language", "Wrong language"),
]


def save_answer_feedback(
    user_id: str,
    rating: str,
    client_id: str | None = None,
    session_id: str | None = None,
    message_id: str | None = None,
    reason_codes: list[str] | None = None,
    comment: str | None = None,
    question: str | None = None,
    answer: str | None = None,
    sources: list[dict] | None = None,
) -> bool:
    """Record feedback on a single answer.

    question/answer/sources are snapshotted rather than referenced: clients
    can delete conversations, and the quality signal must outlive that.
    Upserts on (message_id, user_id) so changing a rating replaces it.
    """
    try:
        supabase = get_supabase()
        payload = {
            "user_id":      user_id,
            "client_id":    client_id,
            "session_id":   session_id,
            "message_id":   message_id,
            "rating":       rating,
            "reason_codes": reason_codes or [],
            "comment":      (comment or "").strip() or None,
            "question":     question,
            "answer":       answer,
            "sources":      sources or [],
        }
        if message_id:
            supabase.table("answer_feedback") \
                .upsert(payload, on_conflict="message_id,user_id") \
                .execute()
        else:
            supabase.table("answer_feedback").insert(payload).execute()
        return True
    except Exception as e:
        _st().error(f"Could not save feedback: {e}")
        return False


def load_feedback_for_session(user_id: str, session_id: str) -> dict[str, dict]:
    """Existing feedback for a conversation, keyed by message_id.

    Used to re-render thumbs state when a conversation is reloaded.
    """
    try:
        supabase = get_supabase()
        res = supabase.table("answer_feedback") \
            .select("message_id, rating, reason_codes, comment") \
            .eq("user_id", user_id) \
            .eq("session_id", session_id) \
            .execute()
        return {r["message_id"]: r for r in (res.data or []) if r.get("message_id")}
    except Exception:
        return {}


def load_all_feedback(rating: str | None = None, limit: int = 200) -> list[dict]:
    """Admin: feedback across all clients, newest first."""
    try:
        supabase = get_supabase()
        query = supabase.table("answer_feedback").select("*")
        if rating:
            query = query.eq("rating", rating)
        res = query.order("created_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        _st().error(f"Could not load feedback: {e}")
        return []


def get_feedback_summary() -> dict:
    """Admin: aggregate counts for the feedback dashboard.

    Aggregated in Python for the same reason as load_chat_sessions —
    PostgREST has no GROUP BY. Move to an RPC if volume grows.
    """
    try:
        supabase = get_supabase()
        res = supabase.table("answer_feedback") \
            .select("rating, reason_codes, created_at") \
            .execute()
        rows = res.data or []
        up = sum(1 for r in rows if r.get("rating") == "up")
        down = sum(1 for r in rows if r.get("rating") == "down")
        reasons: dict[str, int] = {}
        for r in rows:
            for code in (r.get("reason_codes") or []):
                reasons[code] = reasons.get(code, 0) + 1
        total = up + down
        return {
            "total":         total,
            "up":            up,
            "down":          down,
            "positive_rate": round(100 * up / total, 1) if total else None,
            "reasons":       dict(sorted(reasons.items(),
                                         key=lambda kv: kv[1], reverse=True)),
        }
    except Exception:
        return {"total": 0, "up": 0, "down": 0, "positive_rate": None, "reasons": {}}


# ── S22: Support ticketing ────────────────────────────────────────────────────

TICKET_CATEGORIES = [
    ("bug",               "Something's broken"),
    ("question",          "How do I…"),
    ("feature_request",   "Suggestion / feature request"),
    ("compliance_answer", "A compliance answer was wrong or outdated"),
    ("billing",           "Billing & account"),
    ("data_request",      "Data & privacy request"),
]

TICKET_SEVERITIES = [
    ("critical", "Critical — platform unusable, or compliance data at risk"),
    ("high",     "High — a core feature is blocked, workaround is painful"),
    ("normal",   "Normal — degraded but workable"),
    ("low",      "Low — cosmetic, or a question"),
]

TICKET_STATUSES = [
    "open", "in_progress", "waiting_on_client", "resolved", "closed",
]

TICKET_PRIORITIES = ["urgent", "high", "normal", "low"]


def create_ticket(
    user_id: str,
    subject: str,
    body: str,
    category: str = "question",
    context: str = "other",
    context_ref: str | None = None,
    reported_severity: str = "normal",
    client_id: str | None = None,
) -> str | None:
    """Create a thread, a ticket pointing at it, and the opening message.

    Returns the ticket id. Not transactional across the three inserts —
    PostgREST has no multi-statement transaction — so the thread is created
    first and orphaned only if a later step fails, which is recoverable.

    severity is seeded from reported_severity; admin can override it later
    while reported_severity keeps what the client originally claimed.
    """
    try:
        supabase = get_supabase()

        thread_res = supabase.table("message_threads").insert({
            "thread_type": "ticket",
        }).execute()
        thread_rows = thread_res.data or []
        if not thread_rows:
            _st().error("Could not open a support thread.")
            return None
        thread_id = thread_rows[0]["id"]

        ticket_res = supabase.table("support_tickets").insert({
            "user_id":           user_id,
            "client_id":         client_id,
            "thread_id":         thread_id,
            "subject":           subject.strip()[:200],
            "category":          category,
            "context":           context,
            "context_ref":       context_ref,
            "reported_severity": reported_severity,
            "severity":          reported_severity,
            "status":            "open",
        }).execute()
        ticket_rows = ticket_res.data or []
        if not ticket_rows:
            _st().error("Could not create the ticket.")
            return None
        ticket_id = ticket_rows[0]["id"]

        post_thread_message(thread_id, user_id, "client", body)

        log_audit_event(
            company_id=client_id,
            user_id=user_id,
            event_type="support_ticket_created",
            event_subtype=category,
            resource_id=ticket_id,
            summary=f"Opened support ticket: {subject.strip()[:80]}",
            metadata={"context": context, "reported_severity": reported_severity},
        )
        return ticket_id
    except Exception as e:
        _st().error(f"Could not create ticket: {e}")
        return None


def post_thread_message(thread_id: str, author_id: str | None,
                        author_role: str, body: str) -> str | None:
    """Add a message to a thread. Returns the new message id."""
    try:
        supabase = get_supabase()
        res = supabase.table("messages").insert({
            "thread_id":   thread_id,
            "author_id":   author_id,
            "author_role": author_role,
            "body":        body.strip(),
        }).execute()
        rows = res.data or []
        return rows[0].get("id") if rows else None
    except Exception as e:
        _st().error(f"Could not post message: {e}")
        return None


def load_thread_messages(thread_id: str) -> list[dict]:
    """All messages in a thread, oldest first."""
    try:
        supabase = get_supabase()
        res = supabase.table("messages") \
            .select("*") \
            .eq("thread_id", thread_id) \
            .order("created_at") \
            .execute()
        return res.data or []
    except Exception as e:
        _st().error(f"Could not load conversation: {e}")
        return []


def load_my_tickets(user_id: str) -> list[dict]:
    """Client-facing: this user's tickets, newest activity first."""
    try:
        supabase = get_supabase()
        res = supabase.table("support_tickets") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("updated_at", desc=True) \
            .execute()
        return res.data or []
    except Exception as e:
        _st().error(f"Could not load your requests: {e}")
        return []


def load_all_tickets(status: str | None = None,
                     category: str | None = None,
                     limit: int = 200) -> list[dict]:
    """Admin: all tickets, optionally filtered."""
    try:
        supabase = get_supabase()
        query = supabase.table("support_tickets").select("*")
        if status:
            query = query.eq("status", status)
        if category:
            query = query.eq("category", category)
        res = query.order("updated_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        _st().error(f"Could not load tickets: {e}")
        return []


def get_ticket(ticket_id: str) -> dict | None:
    """Load a single ticket. RLS decides whether the caller may see it."""
    try:
        supabase = get_supabase()
        res = supabase.table("support_tickets") \
            .select("*") \
            .eq("id", ticket_id) \
            .limit(1) \
            .execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        _st().error(f"Could not load ticket: {e}")
        return None


def update_ticket(ticket_id: str, updates: dict,
                  actor_id: str | None = None) -> bool:
    """Update ticket fields (status, severity, priority, assignment).

    Status transitions are written to the S21 audit trail — the same
    infrastructure S40 will use for document workflow transitions.
    """
    try:
        supabase = get_supabase()
        payload = dict(updates)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        if payload.get("status") in ("resolved", "closed"):
            payload.setdefault("resolved_at",
                               datetime.now(timezone.utc).isoformat())

        supabase.table("support_tickets") \
            .update(payload) \
            .eq("id", ticket_id) \
            .execute()

        if "status" in updates:
            ticket = get_ticket(ticket_id)
            log_audit_event(
                company_id=(ticket or {}).get("client_id"),
                user_id=actor_id,
                event_type="support_ticket_status_changed",
                event_subtype=updates["status"],
                resource_id=ticket_id,
                summary=f"Ticket moved to {updates['status'].replace('_', ' ')}",
                metadata={k: v for k, v in updates.items() if k != "status"},
            )
        return True
    except Exception as e:
        _st().error(f"Could not update ticket: {e}")
        return False


def mark_thread_read(thread_id: str, reader_role: str) -> bool:
    """Mark messages from the other party as read.

    reader_role is who is doing the reading, so a client marks admin
    messages read and vice versa.
    """
    try:
        other = "admin" if reader_role == "client" else "client"
        supabase = get_supabase()
        supabase.table("messages") \
            .update({"read_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("thread_id", thread_id) \
            .eq("author_role", other) \
            .is_("read_at", "null") \
            .execute()
        return True
    except Exception:
        return False


def count_unread_replies(user_id: str) -> int:
    """Client-facing badge: unread admin replies across this user's tickets."""
    try:
        supabase = get_supabase()
        tickets = supabase.table("support_tickets") \
            .select("thread_id") \
            .eq("user_id", user_id) \
            .not_.in_("status", ["closed"]) \
            .execute()
        thread_ids = [t["thread_id"] for t in (tickets.data or [])]
        if not thread_ids:
            return 0
        res = supabase.table("messages") \
            .select("id", count="exact") \
            .in_("thread_id", thread_ids) \
            .eq("author_role", "admin") \
            .is_("read_at", "null") \
            .execute()
        return res.count or 0
    except Exception:
        return 0


def count_open_tickets() -> int:
    """Admin nav badge: tickets needing attention.

    Uses a count-only query rather than fetching rows — this runs on every
    admin page load.
    """
    try:
        supabase = get_supabase()
        res = supabase.table("support_tickets") \
            .select("id", count="exact") \
            .in_("status", ["open", "in_progress"]) \
            .execute()
        return res.count or 0
    except Exception:
        return 0


def get_ticket_owner_email(ticket_id: str) -> str | None:
    """Email of the client who owns a ticket, for reply notifications.

    Service role: an admin replying needs to read another user's profile
    row, which the session client cannot do under RLS.
    """
    try:
        supabase = get_supabase_admin()
        t = supabase.table("support_tickets") \
            .select("user_id") \
            .eq("id", ticket_id) \
            .limit(1) \
            .execute()
        rows = t.data or []
        if not rows or not rows[0].get("user_id"):
            return None

        p = supabase.table("profiles") \
            .select("email") \
            .eq("id", rows[0]["user_id"]) \
            .limit(1) \
            .execute()
        prows = p.data or []
        return (prows[0].get("email") if prows else None) or None
    except Exception as e:
        print(f"Could not resolve ticket owner email: {e}")
        return None


def thread_has_unread_admin_message(thread_id: str) -> bool:
    """True if an earlier admin reply in this thread is still unread.

    Used to throttle notifications to the 0 -> 1 unread transition: posting
    three replies in a row while working a ticket should produce one nudge,
    not three. Read state lives per-message on messages.read_at, and
    mark_thread_read('client') clears it when the client opens the thread —
    so the next reply after they read is a fresh 0 -> 1 and does notify.
    """
    try:
        supabase = get_supabase_admin()
        res = supabase.table("messages") \
            .select("id", count="exact") \
            .eq("thread_id", thread_id) \
            .eq("author_role", "admin") \
            .is_("read_at", "null") \
            .execute()
        return (res.count or 0) > 0
    except Exception as e:
        print(f"Could not check unread admin messages: {e}")
        return True  # fail closed: skip the email rather than risk a burst


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
    """Log the start of a monitoring run.
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
