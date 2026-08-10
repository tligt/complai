"""
inventory.py — runtime access to the S24 reference data.

Everything here reads from Postgres. The authored content lives in
inventory_seed.py and is applied through a generated SQL file; this module
never defines a vocabulary term or a vendor, because two definitions of the
same list is exactly the drift obligations.py exists to prevent.

── Caching ───────────────────────────────────────────────────────────────
Reference data changes when Fabrice deploys a seed, not when a client clicks
something, so it is cached in-process for CACHE_TTL seconds. A plain module
cache rather than st.cache_data: this module is imported by scripts and by the
admin back-office as well as the client app, and importing streamlit at module
level to get a cache would make it unusable outside Streamlit.

The cost is that a seed change takes up to CACHE_TTL to appear in a running
app. Call clear_cache() after seeding, or reboot; both are cheap and neither
happens while a client is mid-form.

── Language fallback ─────────────────────────────────────────────────────
NL and DE labels are NULL pending the open language-scope decision. Every
label lookup falls back to English rather than returning None, so a partial
translation degrades to a working dropdown in the wrong language instead of a
blank one. That is the right failure: a Dutch client seeing "Health data"
can still complete a RoPA.

── Scope ─────────────────────────────────────────────────────────────────
Every read takes a scope argument and passes it through, even though every
reference row is global today. This is deliberate: when S45 adds per-workspace
vocabularies, the filtering already exists at every call site, and the failure
mode being avoided — one unscoped query showing a client another client's
custom category — is the kind that gets found by a client rather than a test.
"""

from __future__ import annotations

import time
from typing import Any

from database import get_supabase


CACHE_TTL = 600  # seconds

_cache: dict[str, tuple[float, Any]] = {}

LANGUAGES = ("en", "fr", "nl", "de")


# ── Cache plumbing ────────────────────────────────────────────────────────

def _cached(key: str, loader):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]
    value = loader()
    _cache[key] = (time.time(), value)
    return value


def clear_cache() -> None:
    """Drop the reference cache. Call after re-seeding."""
    _cache.clear()


# ── Vocabularies ──────────────────────────────────────────────────────────

def get_vocabulary(value_type: str, scope: str | None = None) -> list[dict]:
    """
    All active values of a type, ordered, global plus any scoped to `scope`.

    Returns rows as dicts, so callers get labels in every language and the
    metadata flags without a second query.
    """
    key = f"vocab:{value_type}:{scope or 'global'}"

    def load():
        try:
            q = (
                get_supabase()
                .table("reference_values")
                .select("code, label_en, label_fr, label_nl, label_de, "
                        "note_en, note_fr, note_nl, note_de, metadata, sort_order")
                .eq("value_type", value_type)
                .eq("active", True)
                .order("sort_order")
            )
            rows = q.execute().data or []
        except Exception:
            # A reference lookup failing should not take down a page. An
            # empty vocabulary renders an empty dropdown, which is visibly
            # broken and safe; a raised exception loses whatever the client
            # had already typed into the form.
            return []

        if scope:
            rows = [
                r for r in rows
                if r.get("workspace_id") in (None, scope)
            ]
        return rows

    return _cached(key, load)


def label_for(value_type: str, code: str, lang: str = "en",
              scope: str | None = None) -> str:
    """Human label for a code, falling back to English then to the code."""
    if lang not in LANGUAGES:
        lang = "en"
    for row in get_vocabulary(value_type, scope):
        if row["code"] == code:
            return row.get(f"label_{lang}") or row.get("label_en") or code
    # An unrecognised code means client data holding a retired term. Show the
    # raw code rather than blanking the field — a visible oddity prompts a
    # question, a blank cell does not.
    return code


def note_for(value_type: str, code: str, lang: str = "en",
             scope: str | None = None) -> str | None:
    if lang not in LANGUAGES:
        lang = "en"
    for row in get_vocabulary(value_type, scope):
        if row["code"] == code:
            return row.get(f"note_{lang}") or row.get("note_en")
    return None


def options_for(value_type: str, lang: str = "en",
                scope: str | None = None) -> tuple[list[str], dict[str, str]]:
    """
    Return (codes, code -> label) ready for a Streamlit selectbox or
    multiselect: pass `codes` as options and use the map in format_func, so
    the widget stores codes while the client sees labels.
    """
    rows = get_vocabulary(value_type, scope)
    codes = [r["code"] for r in rows]
    labels = {
        r["code"]: (r.get(f"label_{lang}") or r.get("label_en") or r["code"])
        for r in rows
    }
    return codes, labels


def metadata_for(value_type: str, code: str, scope: str | None = None) -> dict:
    for row in get_vocabulary(value_type, scope):
        if row["code"] == code:
            return row.get("metadata") or {}
    return {}


# ── Vendor catalogue ──────────────────────────────────────────────────────

def get_catalogue() -> list[dict]:
    """Active catalogue vendors, ordered, with their suggested activities."""

    def load():
        try:
            sb = get_supabase()
            vendors = (
                sb.table("vendor_catalogue")
                .select("*")
                .eq("active", True)
                .order("sort_order")
                .execute()
                .data or []
            )
            if not vendors:
                return []

            ids = [v["id"] for v in vendors]
            acts = (
                sb.table("vendor_catalogue_activities")
                .select("*")
                .in_("catalogue_id", ids)
                .order("sort_order")
                .execute()
                .data or []
            )
        except Exception:
            return []

        # Grouped in Python: PostgREST has no GROUP BY, and at catalogue
        # scale (tens of vendors) a second round trip beats an RPC.
        by_vendor: dict[str, list[dict]] = {}
        for a in acts:
            by_vendor.setdefault(a["catalogue_id"], []).append(a)

        for v in vendors:
            v["activities"] = by_vendor.get(v["id"], [])
        return vendors

    return _cached("catalogue", load)


def get_catalogue_entry(key: str) -> dict | None:
    for v in get_catalogue():
        if v["key"] == key:
            return v
    return None


# ── Catalogue principles ──────────────────────────────────────────────────
# The rules behind the defaults, surfaced in the app rather than buried in
# code comments. RLS restricts this table to audience='client' rows, so the
# internal reasoning is not merely unrendered — it is unreadable from here.

def get_principles() -> list[dict]:
    def load():
        try:
            return (
                get_supabase().table("catalogue_principles")
                .select("*").eq("active", True).order("sort_order")
                .execute().data or []
            )
        except Exception:
            return []

    return _cached("principles", load)


def principle(key: str, lang: str = "en") -> dict | None:
    """One principle with title and body resolved to a language."""
    if lang not in LANGUAGES:
        lang = "en"
    for p in get_principles():
        if p["key"] == key:
            return {
                "key": p["key"],
                "title": p.get(f"title_{lang}") or p.get("title_en"),
                "body": p.get(f"body_{lang}") or p.get("body_en"),
            }
    return None


def principles_for_display(lang: str = "en") -> list[dict]:
    if lang not in LANGUAGES:
        lang = "en"
    return [
        {
            "key": p["key"],
            "title": p.get(f"title_{lang}") or p.get("title_en"),
            "body": p.get(f"body_{lang}") or p.get("body_en"),
        }
        for p in get_principles()
    ]


def seed_rows_for(catalogue_key: str, lang: str = "en") -> tuple[dict, list[dict]] | None:
    """
    Return (system_row, [activity_rows]) pre-filled from the catalogue.

    Nothing here is written directly — the intake form renders these as
    defaults for the client to confirm, amend or reject. user_id and
    client_id are added by the caller.
    """
    entry = get_catalogue_entry(catalogue_key)
    if entry is None:
        return None

    suffix = lang if lang in LANGUAGES else "en"

    def pick(row: dict, base: str) -> Any:
        return row.get(f"{base}_{suffix}") or row.get(f"{base}_en")

    system_row = {
        "catalogue_key": entry["key"],
        "name": entry["name"],
        "vendor_legal_name": entry.get("vendor_legal_name"),
        "category": entry.get("category"),
        "processing_country": entry.get("processing_country"),
        "transfer_mechanism": entry.get("transfer_mechanism") or "unknown",
        "dpa_status": entry.get("dpa_status") or "unknown",
        "dpa_url": entry.get("dpa_url"),
        "privacy_policy_url": entry.get("privacy_policy_url"),
        "sets_cookies": entry.get("sets_cookies", False),
        "criticality": entry.get("default_criticality") or "medium",
        # Conditional AI vendors default to 'none' until the client confirms
        # the feature is enabled. Assuming Copilot is on would attach AI Act
        # duties to a tenant that has never touched it, and an over-broad
        # compliance obligation is still a wrong answer.
        "ai_role": "none" if entry.get("ai_conditional") else (entry.get("ai_role") or "none"),
    }

    activity_rows = []
    for a in entry.get("activities", []):
        activity_rows.append({
            "name": pick(a, "name"),
            "purpose": pick(a, "purpose"),
            "legal_basis": a.get("legal_basis"),
            "data_subject_categories": list(a.get("data_subject_categories") or []),
            "data_categories": list(a.get("data_categories") or []),
            "special_categories": list(a.get("special_categories") or []),
            "art9_condition": a.get("art9_condition"),
            # Blank wherever the vendor does not determine the period. The
            # client must supply it — validate_activity requires it — and
            # _retention_is_statutory tells the caller which message to show.
            "retention_period": pick(a, "retention_period"),
            "controller_role": "controller",
            "_system_role": a.get("system_role") or entry.get("default_system_role") or "processor",
            "_retention_is_statutory": a.get("retention_is_statutory", False),
        })

    return system_row, activity_rows


# ── Validation ────────────────────────────────────────────────────────────
# The database enforces membership via triggers, so these functions exist for
# UX, not safety: they turn a would-be 23514 into a field-level message before
# the write, and they cover the rules the schema cannot express — a balancing
# test for legitimate interests, a transfer claim that contradicts the
# processing country.

def validate_system(row: dict, scope: str | None = None) -> list[str]:
    errors: list[str] = []

    if not (row.get("name") or "").strip():
        errors.append("System name is required.")

    for field, vtype, label in (
        ("category", "system_category", "category"),
        ("transfer_mechanism", "transfer_mechanism", "transfer mechanism"),
        ("dpa_status", "dpa_status", "DPA status"),
        ("criticality", "criticality", "criticality"),
        ("ai_role", "ai_role", "AI role"),
    ):
        value = row.get(field)
        if value and value not in {r["code"] for r in get_vocabulary(vtype, scope)}:
            errors.append(f"Unknown {label}: {value!r}")

    if row.get("dpa_signed_on") and row.get("dpa_status") != "signed":
        errors.append("A DPA signature date requires the status to be 'signed'.")

    # Leaving the mechanism at 'unknown' is allowed — that is a gap, and the
    # completeness score is where gaps belong. Claiming no transfer while
    # naming a non-EEA country is different: it is a contradiction the RoPA
    # would carry into a filed document.
    country = (row.get("processing_country") or "").upper()
    non_eea = {"US", "GB", "UK", "IN", "CN", "CA", "AU", "JP", "BR", "SG"}
    if row.get("transfer_mechanism") == "none_eea" and country in non_eea:
        errors.append(
            f"Transfer mechanism says no transfer outside the EEA, but the "
            f"processing country is {country}."
        )

    return errors


def validate_activity(row: dict, scope: str | None = None) -> list[str]:
    errors: list[str] = []

    if not (row.get("name") or "").strip():
        errors.append("Activity name is required.")

    basis = row.get("legal_basis")
    if not basis or basis not in {r["code"] for r in get_vocabulary("legal_basis", scope)}:
        errors.append("A valid Art. 6 legal basis is required.")

    for field, vtype, label in (
        ("data_subject_categories", "data_subject_category", "data subject category"),
        ("data_categories", "data_category", "data category"),
        ("special_categories", "special_category", "special category"),
        ("criminal_data", "criminal_data", "criminal data category"),
        ("security_measures", "security_measure", "security measure"),
    ):
        known = {r["code"] for r in get_vocabulary(vtype, scope)}
        for value in row.get(field) or []:
            if value not in known:
                errors.append(f"Unknown {label}: {value!r}")

    # Art. 9(1) processing without an Art. 9(2) condition is unlawful, so this
    # blocks rather than warns. A RoPA asserting health data with no stated
    # condition is worse than no RoPA — it documents the breach.
    if row.get("special_categories"):
        known = {r["code"] for r in get_vocabulary("art9_condition", scope)}
        if row.get("art9_condition") not in known:
            errors.append("Special category data requires an Art. 9(2) condition.")

    # Driven by the metadata flag rather than a hardcoded basis name, so the
    # rule follows the vocabulary if it changes.
    if basis and metadata_for("legal_basis", basis, scope).get("requires_balancing_test"):
        if not (row.get("legitimate_interest_note") or "").strip():
            errors.append("Legitimate interests requires a recorded balancing test.")

    if not (row.get("retention_period") or "").strip():
        errors.append("A retention period is required (Art. 30(1)(f)).")

    return errors
