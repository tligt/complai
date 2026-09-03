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

import re as _re
import uuid
from dataclasses import dataclass
from datetime import date as _date
from typing import Any, Mapping, Sequence

from template_renderer import (
    Block,
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
        .select("id, name, vendor_legal_name, category, purpose, "
                # S26C: legacy purpose stays selected as the fallback for rows
                # not yet revisited through the form.
                "purpose_i18n, translation_status")
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
            # S26C part 2. A published cookie policy is the most exposed place
            # client free text appears — no one has to ask for it to read it.
            "purpose": _i18n(s, "purpose", language),
            "unreviewed": _is_unreviewed(s, "purpose", language),
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
# RoPA loaders — S26
# ---------------------------------------------------------------------------
# Unlike _load_vendor_rows these are NOT filtered on sets_cookies: a RoPA lists
# every system supporting an activity, which is most of the inventory.
#
# Labels are resolved here, not in the renderer, for the same reason the cookie
# table's are: inventory.py owns translation and the English fallback, and a
# pure renderer must not reach into Postgres.


def _load_inventory(client_id: str) -> dict[str, Any]:
    """One pass over everything both registers need.

    Four queries rather than four per activity. PostgREST has no GROUP BY, so
    the joining is done in Python — the same pattern inventory.get_catalogue()
    uses, and at SME scale (15-60 activities) it is well under a round trip.
    """
    sb = _get_client()

    def _fetch(table: str, cols: str) -> list[dict[str, Any]]:
        try:
            return (
                sb.table(table).select(cols).eq("client_id", client_id)
                .execute().data or []
            )
        except Exception:
            return []

    return {
        "activities": _fetch(
            "processing_activities",
            "id, name, purpose, legal_basis, controller_role, "
            "data_subject_categories, data_categories, special_categories, "
            "art9_condition, criminal_data, retention_period, retention_basis, "
            "security_measures, counterparty_register_note, updated_at, "
            # S26C. The legacy name/purpose/retention_* columns above are still
            # selected: they are the fallback for every row not yet revisited
            # through the new form, and D-48 declined to backfill retention.
            "name_i18n, purpose_i18n, translation_status, "
            "retention_value, retention_unit, retention_basis_code, "
            "retention_archive_value, retention_archive_unit, "
            "retention_archive_basis_code",
        ),
        "systems": _fetch(
            "systems",
            "id, name, vendor_legal_name, category, processing_country, "
            "transfer_mechanism, updated_at",
        ),
        "links": _fetch("activity_systems", "activity_id, system_id, role"),
        "counterparties": _fetch(
            "processing_counterparties",
            "id, legal_name, trading_name, contact_name, contact_email, "
            "registered_address, country, updated_at",
        ),
        "cp_links": _fetch("activity_counterparties", "activity_id, counterparty_id"),
    }


# ---------------------------------------------------------------------------
# S26C — per-language text and structured retention
# ---------------------------------------------------------------------------

def _i18n(row: Mapping[str, Any], field: str, language: str) -> str | None:
    """Client free text in `language`, falling back to the legacy column.

    Resolution order: the requested language, then English, then the legacy
    single-language column. English is the middle step because it is what the
    S26C backfill assumed for text recorded before the split (D-48) — so a row
    that has never been through the new form resolves through the fallback,
    not to a blank cell.

    A blank cell would be the worse failure. Art. 30(1)(b) asks for the
    purpose; text in the wrong language answers it awkwardly, and no text does
    not answer it at all.
    """
    blob = row.get(f"{field}_i18n") or {}
    if isinstance(blob, Mapping):
        for lang in (language, "en"):
            val = blob.get(lang)
            if val and str(val).strip():
                return str(val).strip()
    legacy = row.get(field)
    return str(legacy).strip() if legacy and str(legacy).strip() else None


def _is_unreviewed(row: Mapping[str, Any], field: str, language: str) -> bool:
    """True when the text `_i18n` just returned is machine output nobody read.

    Only true for the language actually rendered. A French document carrying
    an unreviewed French purpose is a problem; an unreviewed German one sitting
    unused in the same row is not.
    """
    status = row.get("translation_status") or {}
    if not isinstance(status, Mapping):
        return False
    blob = row.get(f"{field}_i18n") or {}
    resolved = language if (isinstance(blob, Mapping) and blob.get(language)) else "en"
    return (status.get(field) or {}).get(resolved) == "machine_unreviewed"


# Units carry singular and plural per language rather than living in
# reference_values, because one label column cannot express "1 an" / "2 ans".
# Closed set: the CHECK constraint on processing_activities.retention_unit
# enforces the same four, and a client must never be able to add one.
_RETENTION_UNITS: dict[str, dict[str, tuple[str, str]]] = {
    "en": {"days": ("day", "days"), "months": ("month", "months"),
           "years": ("year", "years")},
    "fr": {"days": ("jour", "jours"), "months": ("mois", "mois"),
           "years": ("an", "ans")},
    "nl": {"days": ("dag", "dagen"), "months": ("maand", "maanden"),
           "years": ("jaar", "jaar")},
    "de": {"days": ("Tag", "Tage"), "months": ("Monat", "Monate"),
           "years": ("Jahr", "Jahre")},
}

_RETENTION_INDEFINITE = {
    "en": "No fixed end date",
    "fr": "Sans terme fixe",
    "nl": "Geen vaste einddatum",
    "de": "Kein festes Enddatum",
}

# Phase labels, used ONLY when an activity has both phases. A single-phase
# activity renders bare, so the common case reads exactly as it did before
# S26C and the labels appear where they carry information.
_RETENTION_PHASES = {
    "en": ("In active use", "Then archived"),
    "fr": ("En base active", "Puis archivage"),
    "nl": ("In actief gebruik", "Daarna gearchiveerd"),
    "de": ("Aktive Nutzung", "Danach archiviert"),
}


def format_retention(value: int | None, unit: str | None, language: str) -> str | None:
    """One retention phase as text. Shaped like format_notice_period()."""
    if not unit:
        return None
    lang = language if language in _RETENTION_UNITS else "en"
    if unit == "indefinite":
        return _RETENTION_INDEFINITE.get(lang, _RETENTION_INDEFINITE["en"])
    if value is None:
        return None
    forms = _RETENTION_UNITS[lang].get(unit)
    if not forms:
        # A unit the CHECK constraint allows but this table does not know.
        # Says so rather than dropping the period silently: a missing
        # retention period in a filed register is a finding.
        return f"{value} {unit}"
    return f"{value} {forms[0] if value == 1 else forms[1]}"


def _basis_label(code: str | None, free_text: str | None, language: str) -> str | None:
    """A retention basis, preferring the coded vocabulary over free text."""
    if code:
        from inventory import label_for  # noqa: PLC0415
        label = label_for("retention_basis", code, language)
        if code == "other" and free_text:
            # 'other' is the escape hatch, and its whole value is the text the
            # client wrote. Rendering the label alone would file "Other" as a
            # legal basis, which is not one.
            return f"{label}: {_clean_retention_basis(free_text)}" if _clean_retention_basis(free_text) else label
        return label
    return _clean_retention_basis(free_text)


def build_retention_cells(
    row: Mapping[str, Any], language: str
) -> tuple[str | None, str | None]:
    """(period, basis) for an activity, covering both phases.

    D-49: retention has an active phase and an optional archive phase, with
    different durations AND different bases. Both cells label the phases only
    when there are two, so a single-phase activity reads as it always did.

    Falls back whole to the legacy free text when nothing structured has been
    recorded. D-48 deliberately did not backfill, so mixed rows are the
    expected state for as long as it takes clients to revisit their activities
    — not a transient to be coded around.
    """
    lang = language if language in _RETENTION_PHASES else "en"

    active = format_retention(row.get("retention_value"), row.get("retention_unit"), lang)
    archive = format_retention(
        row.get("retention_archive_value"), row.get("retention_archive_unit"), lang)

    if active is None and archive is None:
        return (
            (str(row["retention_period"]).strip()
             if row.get("retention_period") else None),
            _clean_retention_basis(row.get("retention_basis")),
        )

    active_basis = _basis_label(
        row.get("retention_basis_code"), row.get("retention_basis"), lang)
    archive_basis = _basis_label(
        row.get("retention_archive_basis_code"), None, lang)

    if archive is None:
        return active, active_basis

    a_label, b_label = _RETENTION_PHASES[lang]
    period = f"{a_label}: {active or '—'}; {b_label.lower()}: {archive}"
    basis = "; ".join(
        f"{lbl.lower() if i else lbl}: {val}"
        for i, (lbl, val) in enumerate(
            ((a_label, active_basis), (b_label, archive_basis)))
        if val
    ) or None
    return period, basis


# Guidance strings a pre-S26 catalogue seed wrote into retention_basis. They
# are prompts to the client, not legal bases, and must never reach a filed
# register. Matched rather than migrated: the rows are the client's and a
# migration that rewrote their text would be editing their record for them.
_RETENTION_GUIDANCE_PREFIXES = (
    "To be set by your own retention policy",
    "Set by national law",
    "Retention: to be set by",
    "Retention: set by national law",
)


def _clean_retention_basis(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    for prefix in _RETENTION_GUIDANCE_PREFIXES:
        if stripped.lower().startswith(prefix.lower()):
            return None
    return stripped


def _labels(value_type: str, codes: Sequence[str] | None, language: str) -> str | None:
    from inventory import label_for  # noqa: PLC0415
    if not codes:
        return None
    return ", ".join(label_for(value_type, c, language) for c in codes)


def _recipient_cell(sysrow: Mapping[str, Any], role: str | None, language: str) -> str:
    """One recipient, as vendor — product type (role).

    Art. 30(1)(d) asks for CATEGORIES of recipients. Naming the vendor as well
    exceeds that and is what an auditor actually wants; the category satisfies
    the Article, the name makes the record useful.

    The legal entity is preferred over the trade name — "Microsoft Ireland
    Operations Limited" is who the data goes to — with a fallback so a client
    who never filled it in still gets a readable row.
    """
    from inventory import label_for  # noqa: PLC0415

    name = sysrow.get("vendor_legal_name") or sysrow.get("name")
    bits = [name]
    if sysrow.get("category"):
        bits.append(f"— {label_for('system_category', sysrow['category'], language)}")
    if role:
        bits.append(f"({label_for('system_role', role, language)})")
    return " ".join(b for b in bits if b)


def _transfer_cell(sysrow: Mapping[str, Any], language: str) -> str | None:
    """Art. 30(1)(e). None when the processing stays inside the EEA."""
    from inventory import is_third_country, label_for  # noqa: PLC0415

    country = (sysrow.get("processing_country") or "").upper()
    if not is_third_country(country):
        return None
    mech = sysrow.get("transfer_mechanism") or "unknown"
    return (
        f"{country} via {sysrow.get('vendor_legal_name') or sysrow.get('name')} "
        f"— {label_for('transfer_mechanism', mech, language)}"
    )


def build_ropa_controller_rows(
    inv: Mapping[str, Any], language: str
) -> list[dict[str, Any]]:
    """Art. 30(1) rows: one per activity the client controls."""
    systems_by_id = {s["id"]: s for s in inv["systems"]}
    links_by_activity: dict[str, list[dict]] = {}
    for l in inv["links"]:
        links_by_activity.setdefault(l["activity_id"], []).append(l)

    rows: list[dict[str, Any]] = []
    for a in sorted(
        inv["activities"], key=lambda r: (_i18n(r, "name", language) or "")
    ):
        if a.get("controller_role") == "processor":
            continue

        recipients: list[str] = []
        transfers: list[str] = []
        for l in links_by_activity.get(a["id"], []):
            sysrow = systems_by_id.get(l["system_id"])
            if not sysrow:
                continue
            # A client's own server is not a recipient. Printing "internal" in
            # the recipients column asserts a disclosure that never happened.
            if (l.get("role") or "") not in _NON_RECIPIENT_ROLES:
                recipients.append(_recipient_cell(sysrow, l.get("role"), language))
            t = _transfer_cell(sysrow, language)
            if t and t not in transfers:
                transfers.append(t)

        specials = _labels("special_category", a.get("special_categories"), language)
        criminal = _labels("criminal_data", a.get("criminal_data"), language)

        _period, _basis = build_retention_cells(a, language)
        rows.append({
            "name": _i18n(a, "name", language),
            "purpose": _i18n(a, "purpose", language),
            # Surfaced per row so a caller can tell the reader that some text
            # in front of them is machine output nobody has confirmed. Not yet
            # rendered by any template body — wiring it in needs a re-seed, and
            # until then the flag travels with the data rather than being
            # recomputed somewhere else later.
            "unreviewed": (
                _is_unreviewed(a, "name", language)
                or _is_unreviewed(a, "purpose", language)
            ),
            "data_subjects": _labels(
                "data_subject_category", a.get("data_subject_categories"), language),
            "data_categories": ", ".join(
                x for x in (
                    _labels("data_category", a.get("data_categories"), language),
                    criminal,
                ) if x
            ) or None,
            "special_categories": specials,
            "art9_condition": (
                _labels("art9_condition", [a["art9_condition"]], language)
                if specials and a.get("art9_condition") else None
            ),
            "recipients": "; ".join(recipients) or None,
            "transfers": "; ".join(transfers) or None,
            "retention_period": _period,
            "retention_basis": _basis,
            "security_measures": _labels(
                "security_measure", a.get("security_measures"), language),
        })
    return rows


def build_ropa_processor_groups(
    inv: Mapping[str, Any], language: str
) -> tuple[list[dict[str, Any]], str | None]:
    """Art. 30(2) groups: one per CONTROLLER, plus the register caption.

    Pivoted by controller rather than activity. Art. 30(2)(b) permits the
    categories of PROCESSING to be described in categories; the controllers
    themselves are named. Grouping this way is what makes that shape visible.

    Activities carrying only a register note contribute to the caption instead
    of a row — a maintained customer list identified by reference, which is
    what processors with fluctuating rosters actually keep.
    """
    processor_acts = [
        a for a in inv["activities"] if a.get("controller_role") == "processor"
    ]
    if not processor_acts:
        return [], None

    by_activity = {a["id"]: a for a in processor_acts}
    cp_by_id = {c["id"]: c for c in inv["counterparties"]}
    systems_by_id = {s["id"]: s for s in inv["systems"]}

    links_by_activity: dict[str, list[dict]] = {}
    for l in inv["links"]:
        links_by_activity.setdefault(l["activity_id"], []).append(l)

    grouped: dict[str, list[dict]] = {}
    for l in inv["cp_links"]:
        if l["activity_id"] in by_activity:
            grouped.setdefault(l["counterparty_id"], []).append(
                by_activity[l["activity_id"]])

    groups: list[dict[str, Any]] = []
    for cp_id, acts in sorted(
        grouped.items(),
        key=lambda kv: (cp_by_id.get(kv[0], {}).get("legal_name") or ""),
    ):
        cp = cp_by_id.get(cp_id)
        if not cp:
            continue

        transfers: list[str] = []
        measures: set[str] = set()
        for a in acts:
            for code in a.get("security_measures") or []:
                measures.add(code)
            for l in links_by_activity.get(a["id"], []):
                sysrow = systems_by_id.get(l["system_id"])
                if not sysrow:
                    continue
                t = _transfer_cell(sysrow, language)
                if t and t not in transfers:
                    transfers.append(t)

        groups.append({
            "controller_name": cp.get("legal_name"),
            "contact_name": cp.get("contact_name"),
            "contact_email": cp.get("contact_email"),
            # Art. 30(2)(b) categories of processing, which are the activity
            # names. Resolved per language: these reach the processor register
            # and are the same text Annex II of a DPA carries.
            "processing_categories": "; ".join(
                sorted({_i18n(a, "name", language) or "" for a in acts} - {""})
            ) or None,
            "transfers": "; ".join(transfers) or None,
            "security_measures": _labels(
                "security_measure", sorted(measures), language),
        })

    notes = sorted({
        (a.get("counterparty_register_note") or "").strip()
        for a in processor_acts
        if (a.get("counterparty_register_note") or "").strip()
    })
    caption = None
    if notes:
        lead = _REGISTER_CAPTION.get(language, _REGISTER_CAPTION["en"])
        caption = lead + " " + " ".join(notes)

    return groups, caption


_NON_RECIPIENT_ROLES = frozenset({"internal"})

_REGISTER_CAPTION = {
    "en": "_Controllers not named individually above are recorded in a maintained "
          "list, producible on request:_",
    "fr": "_Les responsables du traitement non nommés ci-dessus figurent dans une "
          "liste tenue à jour, communicable sur demande :_",
    "nl": "_Verwerkingsverantwoordelijken die hierboven niet afzonderlijk worden "
          "genoemd, staan in een bijgehouden lijst, op verzoek beschikbaar:_",
    "de": "_Oben nicht einzeln genannte Verantwortliche sind in einer gepflegten "
          "Liste erfasst, die auf Anfrage vorgelegt werden kann:_",
}


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

# S26. Deliberately NOT sharing _JURISDICTION_FIELDS: the ePrivacy numbers are
# cookie-policy content and have no place in an Art. 30 record. A register does
# name a supervisory authority only where the client has a representative or a
# DPO to point at, which is handled by the common fields.
_ROPA_FIELDS = [
    FieldSpec("record_type", "Which register this is", required=True),
    FieldSpec("record_as_at", "Record produced as at", required=True),
    FieldSpec("record_last_updated", "Inventory last changed"),
    FieldSpec("has_rows", "Register has at least one row", flag=True),
    FieldSpec("has_dpo_section", "Has a DPO to name", flag=True),
    # Guards for the optional identity fields. Without these the header of a
    # filed record reads "Company registration number: [[ TO COMPLETE ]]",
    # which is worse than omitting the line: it draws an auditor's eye to a
    # gap that may not be one — a sole trader has no enterprise number.
    FieldSpec("has_legal_form", "Legal form recorded", flag=True),
    FieldSpec("has_enterprise_number", "Registration number recorded", flag=True),
    FieldSpec("has_last_updated", "Inventory change date known", flag=True),
    # Art. 30(2) only. True when at least one processor activity identifies its
    # controllers by reference to a maintained list rather than naming them.
    #
    # Without this, a register that names every controller directly still
    # carries a paragraph explaining what a register reference means — a
    # filed record describing a mechanism it does not use, which invites the
    # question "which list, and where?"
    FieldSpec("has_register_reference", "Uses a maintained controller list", flag=True),
]

FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "cookie_policy": _COMMON_CLIENT_FIELDS + _JURISDICTION_FIELDS + _META_FIELDS,
    "ropa_controller": _COMMON_CLIENT_FIELDS + _ROPA_FIELDS,
    "ropa_processor": _COMMON_CLIENT_FIELDS + _ROPA_FIELDS,
    # S26A adds "dpa" at the end of this file.
}

# Which block each document type expects. Used to build only the context a
# render actually needs — a controller register must not run the counterparty
# queries, and vice versa.
DOC_BLOCKS = {
    "cookie_policy": ("cookie_table",),
    "ropa_controller": ("ropa_controller_table",),
    "ropa_processor": ("ropa_processor_table",),
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


_ISO_DATE_RE = _re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def format_date(value, language: str) -> str:
    """Render a date in the document's language.

    A string that is already prose passes through untouched, so a caller that
    has formatted one is not second-guessed.

    An ISO-8601 date string is NOT prose and is parsed. S25 passed every string
    straight through on the reasoning that a string means "already formatted",
    which is true of "18 août 2026" and false of "2026-08-18" — and a caller
    handing over an ISO string is the common case, because that is what comes
    back from Postgres and what st.date_input().isoformat() produces. The
    result was the same failure the month table was written to fix, reachable
    through a different door: a French document dated 2026-08-18.
    """
    if isinstance(value, str):
        m = _ISO_DATE_RE.match(value.strip())
        if not m:
            return value
        value = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    months = _MONTHS.get(language, _MONTHS["en"])
    name = months[value.month - 1]
    if language == "de":
        return f"{value.day}. {name} {value.year}"
    return f"{value.day} {name} {value.year}"


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

_RECORD_TYPE_LABEL = {
    "ropa_controller": {
        "en": "Record of processing activities — as controller (Art. 30(1) GDPR)",
        "fr": "Registre des activités de traitement — en qualité de responsable "
              "du traitement (art. 30(1) RGPD)",
        "nl": "Register van verwerkingsactiviteiten — als verwerkingsverantwoordelijke "
              "(art. 30(1) AVG)",
        "de": "Verzeichnis von Verarbeitungstätigkeiten — als Verantwortlicher "
              "(Art. 30(1) DSGVO)",
    },
    "ropa_processor": {
        "en": "Record of processing activities — as processor (Art. 30(2) GDPR)",
        "fr": "Registre des activités de traitement — en qualité de sous-traitant "
              "(art. 30(2) RGPD)",
        "nl": "Register van verwerkingsactiviteiten — als verwerker (art. 30(2) AVG)",
        "de": "Verzeichnis von Verarbeitungstätigkeiten — als Auftragsverarbeiter "
              "(Art. 30(2) DSGVO)",
    },
}


def build_values(
    client: Mapping[str, Any],
    jurisdictions: Mapping[str, Mapping[str, Any]],
    *,
    language: str,
    generation_date: str,
    vendors: Sequence[Mapping[str, Any]] = (),
    doc_type: str = "cookie_policy",
    block_context: Mapping[str, Any] | None = None,
    last_updated: str | None = None,
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

    # --- Art. 30 register fields ------------------------------------------
    if doc_type in _RECORD_TYPE_LABEL:
        ctx = block_context or {}
        rows = (
            ctx.get("ropa_controller_rows")
            if doc_type == "ropa_controller"
            else ctx.get("ropa_processor_groups")
        ) or []

        values["record_type"] = _RECORD_TYPE_LABEL[doc_type].get(
            language, _RECORD_TYPE_LABEL[doc_type]["en"])
        # D-28: a RoPA is a live view, so an export is a point-in-time
        # snapshot and must say so on its face rather than implying currency
        # it cannot have.
        values["record_as_at"] = format_date(generation_date, language)
        values["record_last_updated"] = (
            format_date(last_updated, language) if last_updated else None
        )
        values["has_rows"] = len(rows) > 0
        values["has_dpo_section"] = values["has_dpo"]
        values["has_legal_form"] = bool((client.get("legal_form") or "").strip())
        values["has_enterprise_number"] = bool(
            (client.get("enterprise_number") or "").strip())
        values["has_last_updated"] = bool(values.get("record_last_updated"))
        values["has_register_reference"] = bool(
            (block_context or {}).get("ropa_processor_caption"))

    # --- Art. 28 processor clauses ----------------------------------------
    # Runs AFTER the common block, because apply_dpa_values reads has_dpo and
    # overwrites has_enterprise_number with its own flag-guard reasoning: in a
    # signed contract a visible placeholder points the counterparty at a gap
    # that may not be one.
    if doc_type == "dpa":
        from template_dpa import apply_dpa_values  # noqa: PLC0415
        apply_dpa_values(values, client, block_context, language)

    return values, resolution.codes_applied


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def build_block_context(
    doc_type: str, client_id: str, language: str
) -> tuple[dict[str, Any], str | None]:
    """The block data one document type needs, and the inventory's last change.

    Dispatched on doc_type so a controller register never runs the counterparty
    queries and a Cookie Policy never loads the whole inventory.
    """
    if doc_type == "cookie_policy":
        return {"vendors": _load_vendor_rows(client_id, language)}, None

    if doc_type == "dpa":
        # Reuses _load_inventory, but scopes every table to activities the
        # client carries out AS PROCESSOR. See the scoping rule in
        # template_dpa: naming a vendor that never touches this customer's
        # data asserts a disclosure that never happened.
        from template_dpa import build_dpa_block_context  # noqa: PLC0415
        return build_dpa_block_context(client_id, language)

    if doc_type not in ("ropa_controller", "ropa_processor"):
        return {}, None

    inv = _load_inventory(client_id)

    stamps = [
        r.get("updated_at")
        for key in ("activities", "systems", "counterparties")
        for r in inv[key]
        if r.get("updated_at")
    ]
    last_updated = max(stamps)[:10] if stamps else None

    if doc_type == "ropa_controller":
        return {"ropa_controller_rows": build_ropa_controller_rows(inv, language)}, last_updated

    groups, caption = build_ropa_processor_groups(inv, language)
    return {
        "ropa_processor_groups": groups,
        "ropa_processor_caption": caption,
    }, last_updated


@dataclass
class GeneratedDocument:
    language: str
    result: RenderResult
    template_version_id: str | None
    source_revision: int | None
    document_group_id: str
    jurisdictions_applied: list[str]
    skipped_reason: str | None = None
    # The document's own title, in its own language. obligations.DOCUMENT_TYPES
    # is English-only, so anything building a filename, a sheet title or a
    # subject line from it puts an English heading on a French document.
    title: str | None = None


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

        block_context, last_updated = build_block_context(doc_type, client_id, lang)
        values, codes = build_values(
            client, jurisdictions,
            language=lang,
            generation_date=generation_date,
            vendors=block_context.get("vendors") or (),
            doc_type=doc_type,
            block_context=block_context,
            last_updated=last_updated,
        )

        result = render_template(
            version.body_md,
            values=values,
            specs=specs,
            language=lang,
            block_renderers=DEFAULT_BLOCK_RENDERERS,
            block_context=block_context,
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
            title=values.get("record_type"),
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

# ---------------------------------------------------------------------------
# S26A — DPA (Art. 28 processor clauses, Decision (EU) 2021/915)
# ---------------------------------------------------------------------------
# At the END of the file, not beside the FIELD_SPECS literal: template_dpa
# imports from template_store at call time, so importing it before FIELD_SPECS
# exists would be circular.
#
# DEFAULT_BLOCK_RENDERERS is registered HERE rather than in template_renderer
# for the same reason in the other direction. template_dpa imports Block and
# FieldSpec from template_renderer at module level, so template_renderer
# importing template_dpa would close the cycle. This module already imports
# both, and the dict is the same object, so mutating it here is visible to
# every caller including generate() below.
#
# doc_type is "dpa", and it means the PROCESSOR-side agreement the client
# offers its own customers — the only thing it can mean since D-40 made
# gdpr_05 operational with doc_type None. The vendor side of Art. 28 is
# discharged by holding the vendor's DPA and recording it against the system,
# not by authoring one, so there is no second direction for this code to be
# confused with. D-40 considered and rejected a second doc_type here: two
# codes differing only in direction is the "rop"/"ropa" shape.
from template_dpa import (  # noqa: E402
    DPA_BLOCKS,
    DPA_BLOCK_RENDERERS,
    DPA_FIELDS,
)

FIELD_SPECS["dpa"] = DPA_FIELDS
DOC_BLOCKS["dpa"] = DPA_BLOCKS
DEFAULT_BLOCK_RENDERERS.update(DPA_BLOCK_RENDERERS)
