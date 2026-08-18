"""
template_store.py — S25

Database layer for template rendering. Fetches template versions and reference
data, builds the merge-field context, and orchestrates multi-language
generation.

Split from template_renderer.py so the renderer stays pure and testable
offline. This module talks to Supabase; the renderer never does.

---------------------------------------------------------------------------
ADAPTER SECTION — ONE THING LEFT TO VERIFY
---------------------------------------------------------------------------
Repo-specific access is isolated in the two functions below.

  1. get_supabase() / get_supabase_admin() from database — confirmed, this is
     what inventory.py uses.
  2. inventory.label_for(value_type, code, lang) — confirmed.
  3. STILL UNVERIFIED: the role column name on activity_systems. S24 put role
     on the join table rather than on systems, but the column may be `role` or
     `system_role`. _load_vendor_rows assumes `role`. If the select 400s, that
     is why.

Note that inventory.py holds REFERENCE data only — vocabularies and the vendor
catalogue. A client's own systems are not in it, which is why this module
queries the systems / activity_systems / processing_activities tables directly
rather than calling an inventory loader.

Reads use the client-session client so RLS scopes them. Templates are
SELECT-only for authenticated users and filtered to status='in_force' by
policy, so a client physically cannot render a draft — the RLS policy is the
enforcement, not this code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from template_renderer import (
    DEFAULT_BLOCK_RENDERERS,
    FieldSpec,
    RenderResult,
    render_template,
    resolve_jurisdictions,
)

# ---------------------------------------------------------------------------
# _ADAPTERS — the only place repo-specific names appear
# ---------------------------------------------------------------------------

def _get_client(admin: bool = False):
    from database import get_supabase, get_supabase_admin  # noqa: PLC0415
    return get_supabase_admin() if admin else get_supabase()


def _load_vendor_rows(client_id: str, language: str) -> list[dict[str, Any]]:
    """Cookie-setting systems for one client, labels resolved to `language`.

    ------------------------------------------------------------------
    FILTERED ON sets_cookies — this is the whole point
    ------------------------------------------------------------------
    A Cookie Policy lists the vendors that actually set cookies, not every
    system in the inventory. Payroll and accounting tools belong in the RoPA
    (S26); putting them in a cookie policy is a false statement about what the
    site does.

    Per the S24 principle, cookies are recorded at VENDOR level until the S42
    scanner exists. So this lists vendors, not individual cookie names, and the
    template must not promise a per-cookie table it cannot fill.

    ------------------------------------------------------------------
    Purpose comes from the system; role comes from the join
    ------------------------------------------------------------------
    `systems.purpose` is client-authored free text ("What you use it for" in
    pages/inventory.py) and is read directly.

    `role` is NOT on the system — it sits on activity_systems, because a vendor
    can be processor for one activity and joint controller for another (S24,
    Fashion ID C-40/17). A vendor with two activities can therefore carry two
    roles, and both are kept. Collapsing to the first would render Meta Pixel
    as a plain processor and discard the joint-controller finding the catalogue
    exists to surface.

    Note that pages/inventory.py has no UI for role — it is set only by
    seed_from_catalogue. So today the role is whatever the catalogue asserted,
    which is exactly the value worth printing, but it also means a client who
    added a vendor by hand has no role at all and gets an em dash.

    Aggregated in Python because PostgREST has no GROUP BY — the same pattern
    inventory.get_catalogue() uses.
    """
    from inventory import label_for  # noqa: PLC0415

    sb = _get_client()

    systems = (
        sb.table("systems")
        .select("id, name, vendor_legal_name, category, purpose")
        .eq("client_id", client_id)
        .eq("sets_cookies", True)
        .order("name")
        .execute()
        .data or []
    )
    if not systems:
        return []

    links = (
        sb.table("activity_systems")
        .select("system_id, role")
        .in_("system_id", [s["id"] for s in systems])
        .execute()
        .data or []
    )

    roles_by_system: dict[str, list[str]] = {}
    for l in links:
        bucket = roles_by_system.setdefault(l["system_id"], [])
        r = l.get("role")
        if r and r not in bucket:
            bucket.append(r)

    out: list[dict[str, Any]] = []
    for s in systems:
        roles = roles_by_system.get(s["id"], [])
        out.append({
            # The legal entity is what a cookie policy should name — "Meta
            # Platforms Ireland Limited", not "Meta Pixel" — but the trade name
            # is what a reader recognises, so fall back rather than blanking.
            "vendor_name": s.get("vendor_legal_name") or s.get("name"),
            "purpose": s.get("purpose"),
            "category_label": (
                label_for("system_category", s["category"], language)
                if s.get("category") else None
            ),
            "role_label": "; ".join(
                label_for("system_role", r, language) for r in roles
            ) or None,
        })
    return out


# ---------------------------------------------------------------------------
# Field specifications, per document type
# ---------------------------------------------------------------------------
# These are the renderer's contract with the template. They live in code, in
# git, next to obligations.py — not in Postgres — because changing whether a
# field blocks generation is a behavioural change that should show up in a
# diff and be reviewable, not a row someone edits in a table.
#
# required=True is reserved for fields whose absence makes the document WRONG
# rather than incomplete. See FieldSpec's docstring.

_COMMON_CLIENT_FIELDS = [
    FieldSpec("legal_name", "Legal name of the company", required=True),
    FieldSpec("legal_form", "Legal form (SRL, SA, SAS…)"),
    FieldSpec("registered_address", "Registered address", required=True),
    FieldSpec("enterprise_number", "Company registration number"),
    FieldSpec("contact_email", "Contact email for privacy requests", required=True),
    FieldSpec("website_url", "Website address", required=True),
    FieldSpec("dpo_name", "Data Protection Officer name"),
    FieldSpec("dpo_email", "Data Protection Officer email"),
    FieldSpec("has_dpo", "Has a DPO", flag=True),
]

_JURISDICTION_FIELDS = [
    FieldSpec("authority_name", "Supervisory authority", required=True),
    FieldSpec("authority_url", "Supervisory authority website", required=True),
    FieldSpec("cookie_max_lifetime_months", "Maximum cookie lifetime"),
    FieldSpec("cookie_data_retention_months", "Cookie data retention period"),
    FieldSpec("consent_renewal_months", "Consent renewal period"),
    FieldSpec("has_cookie_lifetime_cap", "National cookie lifetime cap exists", flag=True),
    FieldSpec("has_data_retention_cap", "National retention cap exists", flag=True),
    FieldSpec("has_consent_renewal_period", "Consent renewal period published", flag=True),
    FieldSpec("reject_parity_required", "Reject-all parity required", flag=True),
    FieldSpec("cookie_walls_prohibited", "Cookie walls prohibited", flag=True),
    FieldSpec("is_multi_market", "Serves more than one market", flag=True),
]

_META_FIELDS = [
    FieldSpec("generation_date", "Generation date", required=True),
    FieldSpec("has_vendors", "Has recorded third-party systems", flag=True),
]

FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "cookie_policy": _COMMON_CLIENT_FIELDS + _JURISDICTION_FIELDS + _META_FIELDS,
    # S26 adds ropa and dpa here.
}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@dataclass
class TemplateVersion:
    id: str
    template_id: str
    doc_type: str
    language: str
    version_no: int
    source_revision: int
    body_md: str
    materiality: str
    effective_from: str | None


def load_jurisdiction_map() -> dict[str, dict[str, Any]]:
    """Active jurisdictions keyed by code, metadata flattened."""
    sb = _get_client()
    res = (
        sb.table("reference_values")
        .select("code, metadata")
        .eq("value_type", "jurisdiction")
        .eq("active", True)
        .execute()
    )
    return {r["code"]: (r.get("metadata") or {}) for r in (res.data or [])}


def load_template_version(doc_type: str, language: str) -> TemplateVersion | None:
    """The in-force version for (doc_type, language), or None.

    Returns None rather than raising when a language has no in-force body —
    that is the normal mid-translation state, not an error. The caller decides
    whether to fall back or skip.
    """
    sb = _get_client()
    res = (
        sb.table("document_template_versions")
        .select(
            "id, template_id, language, version_no, source_revision, body_md, "
            "materiality, effective_from, document_templates!inner(doc_type, active)"
        )
        .eq("language", language)
        .eq("status", "in_force")
        .eq("document_templates.doc_type", doc_type)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None

    # dtv_one_in_force_per_language guarantees at most one. If more arrive,
    # the index is missing — fail loudly rather than pick arbitrarily.
    if len(rows) > 1:
        raise RuntimeError(
            f"{len(rows)} in-force versions for {doc_type}/{language}. "
            "dtv_one_in_force_per_language is missing or was dropped."
        )

    r = rows[0]
    return TemplateVersion(
        id=r["id"],
        template_id=r["template_id"],
        doc_type=doc_type,
        language=language,
        version_no=r["version_no"],
        source_revision=r["source_revision"],
        body_md=r["body_md"],
        materiality=r["materiality"],
        effective_from=r.get("effective_from"),
    )


def load_client(client_id: str) -> dict[str, Any] | None:
    sb = _get_client()
    res = sb.table("clients").select("*").eq("id", client_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Date formatting
# ---------------------------------------------------------------------------
# Month names in a table rather than via locale.setlocale().
#
# Two reasons. Locale support depends on which locales are INSTALLED in the
# container — Streamlit Cloud has no guarantee of fr_FR or nl_NL, so
# setlocale() raises or silently falls back to English. And setlocale() is
# process-global and not thread-safe, so one document rendering in French
# would change the date format of a concurrent request.
#
# Caught by the first real generated document, which read
# "Dernière mise à jour : 18 August 2026".

_MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"),
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"),
    "nl": ("januari", "februari", "maart", "april", "mei", "juni", "juli",
           "augustus", "september", "oktober", "november", "december"),
    "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"),
}


def format_date(value, language: str) -> str:
    """Render a date in the document's language.

    A plain string passes through untouched, so a caller that has already
    formatted one is not second-guessed.
    """
    if isinstance(value, str):
        return value
    months = _MONTHS.get(language, _MONTHS["en"])
    name = months[value.month - 1]
    if language == "de":
        return f"{value.day}. {name} {value.year}"
    return f"{value.day} {name} {value.year}"


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

def build_values(
    client: Mapping[str, Any],
    jurisdictions: Mapping[str, Mapping[str, Any]],
    *,
    language: str,
    generation_date: str,
    vendors: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Assemble the merge-field values. Returns (values, jurisdiction_codes)."""
    resolution = resolve_jurisdictions(
        client.get("target_markets") or [],
        jurisdictions,
        establishment_code=(client.get("country") or "").upper() or None,
    )

    # The address is client-authored free text and usually multi-line. Markdown
    # ignores a single newline, so each line gets a hard break — otherwise a
    # three-line address renders as one run-on line in the document header.
    _address = client.get("registered_address")
    if _address:
        _address = "  \n".join(
            line.strip() for line in str(_address).splitlines() if line.strip()
        )

    values: dict[str, Any] = {
        "legal_name": client.get("legal_name"),
        "legal_form": client.get("legal_form"),
        "registered_address": _address,
        "enterprise_number": client.get("enterprise_number"),
        "contact_email": client.get("contact_email"),
        "website_url": client.get("website_url"),
        "dpo_name": client.get("dpo_name"),
        "dpo_email": client.get("dpo_email"),
        "generation_date": format_date(generation_date, language),
    }

    # A DPO exists only if BOTH name and email are present. A name with no
    # contact route is not a usable DPO section in a document whose purpose is
    # to tell people how to reach one.
    values["has_dpo"] = bool(
        (client.get("dpo_name") or "").strip()
        and (client.get("dpo_email") or "").strip()
    )

    values.update(resolution.rules)

    auth = jurisdictions.get(resolution.authority_code or "", {})
    values["authority_name"] = (
        auth.get(f"supervisory_authority_{language}")
        or auth.get("supervisory_authority_en")
        or auth.get("supervisory_authority_short")
    )
    values["authority_url"] = auth.get("supervisory_authority_url")

    values["has_vendors"] = len(vendors) > 0

    return values, resolution.codes_applied


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@dataclass
class GeneratedDocument:
    language: str
    result: RenderResult
    template_version_id: str | None
    source_revision: int | None
    document_group_id: str
    jurisdictions_applied: list[str]
    skipped_reason: str | None = None


def generate(
    client_id: str,
    doc_type: str,
    *,
    generation_date: str,
    languages: Sequence[str] | None = None,
    theme: str | None = None,
) -> list[GeneratedDocument]:
    """Render one document in every language the client issues documents in.

    Returns one GeneratedDocument per language, all sharing a
    document_group_id. Persistence is the caller's job — this function does not
    write, so it can be exercised from a script without creating rows.

    The siblings are the SAME document in different languages, not different
    documents (S27 adoption applies to the group). Note that a group can
    legitimately span two source_revisions during a translation window: if FR
    is at revision 4 and NL still at 3, both render and both are stamped
    honestly. The register surfaces the divergence; it is not suppressed here.
    """
    client = load_client(client_id)
    if client is None:
        raise ValueError(f"No client {client_id}")

    langs = list(languages or client.get("document_languages") or ["en"])
    if not langs:
        langs = ["en"]

    specs = FIELD_SPECS.get(doc_type)
    if specs is None:
        raise ValueError(f"No field specification for doc_type '{doc_type}'")

    jurisdictions = load_jurisdiction_map()
    group_id = str(uuid.uuid4())
    out: list[GeneratedDocument] = []

    for lang in langs:
        version = load_template_version(doc_type, lang)
        if version is None:
            # Mid-translation or never authored. Recorded, not silently
            # dropped — a client expecting a Dutch policy must be told it is
            # unavailable rather than shown two documents and left to notice.
            out.append(GeneratedDocument(
                language=lang,
                result=RenderResult(body=None, blocked=True),
                template_version_id=None,
                source_revision=None,
                document_group_id=group_id,
                jurisdictions_applied=[],
                skipped_reason=f"No in-force {doc_type} template in '{lang}'.",
            ))
            continue

        vendors = _load_vendor_rows(client_id, lang)
        values, codes = build_values(
            client, jurisdictions,
            language=lang,
            generation_date=generation_date,
            vendors=vendors,
        )

        result = render_template(
            version.body_md,
            values=values,
            specs=specs,
            language=lang,
            block_renderers=DEFAULT_BLOCK_RENDERERS,
            block_context={"vendors": vendors},
            theme=theme,
        )
        result.jurisdictions_applied = codes

        out.append(GeneratedDocument(
            language=lang,
            result=result,
            template_version_id=version.id,
            source_revision=version.source_revision,
            document_group_id=group_id,
            jurisdictions_applied=codes,
        ))

    return out


def group_summary(docs: Sequence[GeneratedDocument]) -> dict[str, Any]:
    """Aggregate state across the language siblings of one generation.

    Outstanding placeholders are PER LANGUAGE — a French body can carry one its
    Dutch sibling does not — so the dashboard must sum across the group. Show
    only one language's count and a client resolves the French gap, still sees
    the badge, and has no way to tell why.
    """
    outstanding: list[dict[str, str]] = []
    for d in docs:
        outstanding.extend(d.result.outstanding_fields)

    blocked = [d for d in docs if d.result.blocked]
    missing_required = sorted({
        f for d in docs for f in d.result.missing_required
    })
    revisions = sorted({d.source_revision for d in docs if d.source_revision})

    return {
        "document_group_id": docs[0].document_group_id if docs else None,
        "languages": [d.language for d in docs],
        "blocked_languages": [d.language for d in blocked],
        "any_blocked": bool(blocked),
        "missing_required": missing_required,
        "outstanding_total": len(outstanding),
        "outstanding_by_language": {
            d.language: len(d.result.outstanding_fields) for d in docs
        },
        "source_revisions": revisions,
        "revision_split": len(revisions) > 1,
    }
