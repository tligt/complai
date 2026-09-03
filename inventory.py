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

── S26 additions ─────────────────────────────────────────────────────────
validate_counterparty() for the Art. 30(2) controller identities, and
controller_role is now validated (it drives which register an activity lands
in, so an unrecognised value silently drops the row out of both).
"""

from __future__ import annotations

import time
from typing import Any

from database import get_supabase


CACHE_TTL = 600  # seconds

_cache: dict[str, tuple[float, Any]] = {}

LANGUAGES = ("en", "fr", "nl", "de")

# Hoisted out of validate_system in S26 so validate_activity and readiness()
# can apply the same test when deciding whether an activity involves a
# third-country transfer.
#
# This is a stopgap. EEA membership is reference data and belongs in
# reference_values as a jurisdiction property — the list is short, stable and
# rarely wrong, but it is still a fact about the world living in Python, which
# is the thing this module exists to prevent. Move it when the jurisdiction
# vocabulary grows past BE and FR.
NON_EEA_COUNTRIES = frozenset({
    "US", "GB", "UK", "IN", "CN", "CA", "AU", "JP", "BR", "SG",
    "CH", "IL", "KR", "NZ", "ZA", "MX", "AE", "RU", "TR", "UA",
})

# Codes that mean "inside the EEA, no transfer" rather than a country.
EEA_SENTINELS = frozenset({"EU", "EEA", "EER"})


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

    KNOWN NO-OP: the scope filter below reads workspace_id, which is not in
    the select list, so r.get("workspace_id") is always None and every row
    passes. Harmless while every reference row is global; it becomes a real
    leak the moment S46 adds per-workspace vocabularies. Fix by adding the
    column to the select — deliberately left visible rather than silently
    removed, so the S46 work has something to trip over.
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


def codes_for(value_type: str, scope: str | None = None) -> set[str]:
    """Just the active codes. Used by every validator below."""
    return {r["code"] for r in get_vocabulary(value_type, scope)}


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


# ── Transfer helpers ──────────────────────────────────────────────────────

def country_error(country: str | None, field: str = "Country") -> str | None:
    """Reject anything that is not a two-letter ISO code (or an EEA sentinel).

    Not cosmetic. is_third_country() matches against ISO-2, so a client who
    types "United States" instead of "US" is silently treated as EEA-internal:
    the transfer-safeguard check in readiness() never fires and an unsafeguarded
    third-country transfer reaches a generated Art. 30 record.

    The help text alone did not hold — the first real controller entered was
    "BELGIUM". A silent wrong answer is the failure this blocks.
    """
    code = (country or "").strip()
    if not code:
        return None  # absence is a gap, reported by readiness(), not an error
    code = code.upper()
    if code in EEA_SENTINELS:
        return None
    if len(code) != 2 or not code.isalpha():
        return (
            f"{field} must be a two-letter ISO country code "
            f"(BE, FR, DE, US…), not {country!r}."
        )
    return None


def is_third_country(country: str | None) -> bool:
    """True when a processing country is outside the EEA.

    Unknown or blank returns False: absence of a country is a completeness
    gap, reported by readiness(), not a transfer finding. Asserting a transfer
    the client never described would put a false statement in the RoPA, which
    is the direction that matters (D-20).
    """
    code = (country or "").strip().upper()
    if not code or code in EEA_SENTINELS:
        return False
    return code in NON_EEA_COUNTRIES


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

    def every(row: dict, base: str) -> dict[str, str]:
        """Every language the catalogue holds for this field.

        S26C. pick() chose ONE language and that single string was what landed
        in processing_activities, so a Belgian client seeding Microsoft 365 in
        English permanently lost the French purpose the catalogue was already
        carrying. The translations existed; the write threw them away.

        No review state is recorded because none is needed: this text is
        RECOSA-authored and reviewed, and absent from translation_status means
        human (see the S26C migration). Only machine output has to declare
        itself.

        Languages the catalogue has no text for are simply absent, rather than
        present and empty — _i18n() falls back on a missing key, but an empty
        string would render as a blank cell in a filed register.
        """
        out = {}
        for code in LANGUAGES:
            val = row.get(f"{base}_{code}")
            if val and str(val).strip():
                out[code] = str(val).strip()
        return out

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
            # Legacy columns stay populated: validate_activity() reads name,
            # and they remain the fallback for any language the catalogue does
            # not cover (today NL and DE — S53).
            "name": pick(a, "name"),
            "purpose": pick(a, "purpose"),
            "name_i18n": every(a, "name"),
            "purpose_i18n": every(a, "purpose"),
            "legal_basis": a.get("legal_basis"),
            "data_subject_categories": list(a.get("data_subject_categories") or []),
            "data_categories": list(a.get("data_categories") or []),
            "special_categories": list(a.get("special_categories") or []),
            "art9_condition": a.get("art9_condition"),
            # Blank wherever the vendor does not determine the period. The
            # client must supply it — validate_activity requires it — and
            # _retention_is_statutory tells the caller which message to show.
            #
            # S26C: structured, and no basis code. The catalogue may know how
            # long a tool keeps data; it never knows why the client chose to.
            "retention_value": a.get("retention_value"),
            "retention_unit": a.get("retention_unit"),
            # Catalogue activities describe what the CLIENT does with a tool,
            # so the client is the controller. A processor-side activity is
            # something the client does for its own customers and has no
            # catalogue equivalent — it is always authored by hand.
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
        if value and value not in codes_for(vtype, scope):
            errors.append(f"Unknown {label}: {value!r}")

    if row.get("dpa_signed_on") and row.get("dpa_status") != "signed":
        errors.append("A DPA signature date requires the status to be 'signed'.")

    cerr = country_error(row.get("processing_country"), "Processing country")
    if cerr:
        errors.append(cerr)

    # Leaving the mechanism at 'unknown' is allowed — that is a gap, and the
    # completeness score is where gaps belong. Claiming no transfer while
    # naming a non-EEA country is different: it is a contradiction the RoPA
    # would carry into a filed document.
    if row.get("transfer_mechanism") == "none_eea" and is_third_country(row.get("processing_country")):
        errors.append(
            f"Transfer mechanism says no transfer outside the EEA, but the "
            f"processing country is {(row.get('processing_country') or '').upper()}."
        )

    return errors


def validate_activity(row: dict, scope: str | None = None) -> list[str]:
    errors: list[str] = []

    if not (row.get("name") or "").strip():
        errors.append("Activity name is required.")

    basis = row.get("legal_basis")
    if not basis or basis not in codes_for("legal_basis", scope):
        errors.append("A valid Art. 6 legal basis is required.")

    # S26: controller_role decides which register the activity lands in —
    # Art. 30(1) or Art. 30(2). An unrecognised value would drop the row out
    # of both without anything being visibly wrong, so it is validated rather
    # than trusted to the UI.
    role = row.get("controller_role")
    if role and role not in codes_for("controller_role", scope):
        errors.append(f"Unknown role: {role!r}")

    for field, vtype, label in (
        ("data_subject_categories", "data_subject_category", "data subject category"),
        ("data_categories", "data_category", "data category"),
        ("special_categories", "special_category", "special category"),
        ("criminal_data", "criminal_data", "criminal data category"),
        ("security_measures", "security_measure", "security measure"),
    ):
        known = codes_for(vtype, scope)
        for value in row.get(field) or []:
            if value not in known:
                errors.append(f"Unknown {label}: {value!r}")

    # Art. 9(1) processing without an Art. 9(2) condition is unlawful, so this
    # blocks rather than warns. A RoPA asserting health data with no stated
    # condition is worse than no RoPA — it documents the breach.
    if row.get("special_categories"):
        if row.get("art9_condition") not in codes_for("art9_condition", scope):
            errors.append("Special category data requires an Art. 9(2) condition.")

    # NOT VALIDATED HERE, deliberately: the balancing test (Art. 6(1)(f)) and
    # the retention period (Art. 30(1)(f)).
    #
    # Both used to block the write. Combined with seed_from_catalogue — which
    # inserts rows that fail validation on purpose, so a client is not blocked
    # at the tick — that made every seeded activity UNEDITABLE: changing an
    # activity's role or linking a controller failed on a field the client was
    # not touching. The people it hit were the ones doing the right thing.
    #
    # Both are still enforced, by readiness(), which is the pre-generation gate
    # and the correct place for it. This function decides whether a row can be
    # RECORDED; readiness() decides whether it can be PUBLISHED. Recording an
    # incomplete fact is how a client makes progress; publishing one is how a
    # record becomes wrong.
    #
    # The Art. 9(2) condition above stays blocking because the database CHECK
    # enforces it regardless — letting it through here would only turn a
    # field-level message into a raw 23514.

    return errors


def needs_balancing_test(legal_basis: str | None, scope: str | None = None) -> bool:
    """Whether this Art. 6 basis requires a recorded balancing test.

    Driven by the vocabulary metadata flag rather than a hardcoded basis name,
    so the rule follows the vocabulary if the code is ever retired or renamed.
    """
    if not legal_basis:
        return False
    return bool(
        metadata_for("legal_basis", legal_basis, scope).get("requires_balancing_test")
    )


def validate_counterparty(row: dict, scope: str | None = None) -> list[str]:
    """A controller on whose behalf the client processes — Art. 30(2)(a).

    Deliberately thin. A counterparty is a client fact with no catalogue
    equivalent, and the only thing the Regulation insists on is a name and a
    contact route. Requiring an address or a country here would block a client
    recording a customer they genuinely only know by name and email, which is
    a worse outcome than an incomplete row that readiness() reports.
    """
    errors: list[str] = []

    if not (row.get("legal_name") or "").strip():
        errors.append("The controller's legal name is required (Art. 30(2)(a)).")

    status = row.get("dpa_status")
    if status and status not in codes_for("dpa_status", scope):
        errors.append(f"Unknown DPA status: {status!r}")

    if row.get("dpa_signed_on") and status != "signed":
        errors.append("A DPA signature date requires the status to be 'signed'.")

    cerr = country_error(row.get("country"))
    if cerr:
        errors.append(cerr)

    email = (row.get("contact_email") or "").strip()
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        errors.append(f"That does not look like an email address: {email!r}")

    return errors
