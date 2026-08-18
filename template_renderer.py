"""
template_renderer.py — S25

Pure rendering layer for RECOSA document templates.

DELIBERATELY IMPORTS NOTHING FROM streamlit OR supabase. This module is called
from the client app, the admin back-office viewer, and offline seed/test
scripts. Any Streamlit import here would break the latter two, which is the
same reason inventory.py uses a module-level TTL cache rather than
st.cache_data.

All data arrives as arguments. Fetching belongs in template_store.py.

---------------------------------------------------------------------------
TEMPLATE SYNTAX
---------------------------------------------------------------------------

    {{field_name}}                          scalar merge field
    {{#block:cookie_table}}                  block renderer, whole line
    {{#if:flag}} ... {{/if:flag}}            include when flag is truthy
    {{#ifnot:flag}} ... {{/ifnot:flag}}      include when flag is falsy

Conditionals do not nest. This is a constraint, not an oversight: nesting is
where template languages become programming languages, and these bodies are
reviewed by lawyers, not developers.

---------------------------------------------------------------------------
RESOLUTION ORDER — matters, do not reorder
---------------------------------------------------------------------------

1. Conditionals are resolved first.
2. Fields are then scanned and substituted.

Consequence: a field inside a conditional that evaluated false is NOT missing,
because it was never going to render. Scanning before resolving would block
generation on a DPO email for a client that has no DPO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------

_BLOCK_RE = re.compile(r"^[ \t]*\{\{#block:([a-z0-9_]+)\}\}[ \t]*$", re.MULTILINE)
_IF_RE = re.compile(r"\{\{#if:([a-z0-9_]+)\}\}(.*?)\{\{/if:\1\}\}", re.DOTALL)
_IFNOT_RE = re.compile(r"\{\{#ifnot:([a-z0-9_]+)\}\}(.*?)\{\{/ifnot:\1\}\}", re.DOTALL)
_FIELD_RE = re.compile(r"\{\{([a-z0-9_]+)\}\}")
_ANY_TAG_RE = re.compile(r"\{\{[^}]*\}\}")

PLACEHOLDER_FORMAT = "[[ TO COMPLETE: {label} ]]"


# ---------------------------------------------------------------------------
# Field specification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldSpec:
    """One merge field a template may reference.

    required=True  -> absent value blocks generation entirely
    required=False -> absent value renders a visible placeholder

    The distinction is legal, not technical. A cookie policy that cannot name
    its controller is not a draft, it is wrong; one missing a DPO contact is
    incomplete but still truthful. Blocking on the second would stop clients
    generating anything, and placeholdering the first would emit a document
    that looks finished and is not.
    """
    name: str
    label: str
    required: bool = False
    flag: bool = False  # consumed by conditionals only, never substituted


@dataclass
class RenderResult:
    body: str | None
    blocked: bool
    missing_required: list[str] = dc_field(default_factory=list)
    outstanding_fields: list[dict[str, str]] = dc_field(default_factory=list)
    unknown_tags: list[str] = dc_field(default_factory=list)
    jurisdictions_applied: list[str] = dc_field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.blocked and not self.outstanding_fields


# ---------------------------------------------------------------------------
# Jurisdiction resolution
# ---------------------------------------------------------------------------

# Numeric rules: lower is stricter.
_NUMERIC_RULES = (
    "cookie_max_lifetime_months",
    "cookie_data_retention_months",
    "consent_renewal_months",
)

# Boolean rules: True is stricter.
_BOOLEAN_RULES = (
    "reject_parity_required",
    "cookie_walls_prohibited",
)


@dataclass
class JurisdictionResolution:
    rules: dict[str, Any]
    codes_applied: list[str]
    authority_code: str | None
    provenance: dict[str, str]  # rule name -> code it came from


def resolve_jurisdictions(
    market_codes: Sequence[str],
    jurisdictions: Mapping[str, Mapping[str, Any]],
    *,
    establishment_code: str | None = None,
) -> JurisdictionResolution:
    """Resolve ePrivacy rules across the markets a client serves.

    Single market  -> that market's rules.
    Multiple       -> strictest wins, rule by rule.

    ------------------------------------------------------------------
    NULL HANDLING — the part most likely to be silently wrong
    ------------------------------------------------------------------
    A NULL numeric means "this Member State published no national numeric
    limit". It does NOT mean unlimited and it does NOT mean zero.

    Belgium is the live case: the APD requires a cookie's lifespan be limited
    to what is necessary for its purpose, with no unlimited lifespans — a
    qualitative test. So BE carries NULL where FR carries 13.

    Therefore:
      - NULLs are skipped when taking the minimum. min over [None, 13] is 13.
      - all-NULL resolves to None, which is a valid outcome, not an error.
      - a BE-only client resolves to None and the template must render its
        qualitative branch via {{#ifnot:has_cookie_lifetime_cap}}.

    Treating None as infinity gives a BE+FR client no cap at all. Treating it
    as zero blocks generation. Both fail in the client's favour, which is the
    wrong direction for a compliance document.

    ------------------------------------------------------------------
    Note that "strictest wins" is a conservative reading rather than settled
    law, and it is the most load-bearing interpretation in the product. It is
    flagged for counsel in seed_s25_jurisdictions.sql.
    """
    known = [c for c in market_codes if c in jurisdictions]

    rules: dict[str, Any] = {}
    provenance: dict[str, str] = {}

    for rule in _NUMERIC_RULES:
        best_val: int | None = None
        best_code: str | None = None
        for code in known:
            val = jurisdictions[code].get(rule)
            if val is None:
                continue  # no published limit — skip, do not treat as a bound
            val = int(val)
            if best_val is None or val < best_val:
                best_val, best_code = val, code
        rules[rule] = best_val
        if best_code:
            provenance[rule] = best_code

    for rule in _BOOLEAN_RULES:
        strictest = False
        source: str | None = None
        for code in known:
            if bool(jurisdictions[code].get(rule)):
                strictest, source = True, code
                break
        rules[rule] = strictest
        if source:
            provenance[rule] = source

    # Derived flags so templates can branch without arithmetic in the body.
    rules["has_cookie_lifetime_cap"] = rules["cookie_max_lifetime_months"] is not None
    rules["has_data_retention_cap"] = rules["cookie_data_retention_months"] is not None
    rules["has_consent_renewal_period"] = rules["consent_renewal_months"] is not None
    rules["is_multi_market"] = len(known) > 1

    # The named supervisory authority follows ESTABLISHMENT, not market.
    #
    # Under GDPR one-stop-shop the establishment's authority is lead for
    # cross-border processing, so a BE-established company selling into FR
    # names the APD. ePrivacy is a Directive with no one-stop-shop, which is
    # why the RULES above go strictest-wins while the AUTHORITY here does not.
    # These two genuinely diverge and collapsing them would be wrong.
    authority_code = establishment_code if establishment_code in jurisdictions else None
    if authority_code is None and len(known) == 1:
        authority_code = known[0]

    return JurisdictionResolution(
        rules=rules,
        codes_applied=known,
        authority_code=authority_code,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

BlockRenderer = Callable[[Mapping[str, Any], str], str]


def render_template(
    body_md: str,
    *,
    values: Mapping[str, Any],
    specs: Iterable[FieldSpec],
    language: str,
    block_renderers: Mapping[str, BlockRenderer] | None = None,
    block_context: Mapping[str, Any] | None = None,
    theme: str | None = None,
) -> RenderResult:
    """Render one template body in one language.

    `theme` is accepted and threaded but not consumed until S43. Taking it now
    costs nothing; adding it later would mean touching every call site.
    """
    del theme  # S43

    # Normalise line endings BEFORE anything is matched.
    #
    # _BLOCK_RE is anchored with [ \t]*$, which cannot match a '\r' sitting
    # before the newline — so a CRLF template silently lost every block, and
    # only blocks: conditionals and merge fields are unanchored and matched
    # fine. A Cookie Policy shipped without its third-party vendor table
    # because the seed SQL was saved on Windows.
    #
    # Body text comes from Postgres, authored on whatever machine ran the
    # seed, so the renderer cannot assume anything about line endings.
    body_md = body_md.replace("\r\n", "\n").replace("\r", "\n")

    spec_by_name = {s.name: s for s in specs}
    block_renderers = block_renderers or {}
    block_context = block_context or {}

    # --- 1. Conditionals, before any field scanning -----------------------
    def _truthy(name: str) -> bool:
        val = values.get(name)
        if isinstance(val, str):
            return bool(val.strip())
        if isinstance(val, (list, tuple, dict)):
            return len(val) > 0
        return bool(val)

    body = _IF_RE.sub(lambda m: m.group(2) if _truthy(m.group(1)) else "", body_md)
    body = _IFNOT_RE.sub(lambda m: m.group(2) if not _truthy(m.group(1)) else "", body)

    # --- 2. Blocks ---------------------------------------------------------
    missing_blocks: list[str] = []

    def _render_block(match: re.Match[str]) -> str:
        name = match.group(1)
        renderer = block_renderers.get(name)
        if renderer is None:
            missing_blocks.append(name)
            return PLACEHOLDER_FORMAT.format(label=f"block '{name}' unavailable")
        return renderer(block_context, language)

    body = _BLOCK_RE.sub(_render_block, body)

    # --- 3. Fields ---------------------------------------------------------
    missing_required: list[str] = []
    outstanding: list[dict[str, str]] = []
    unknown: list[str] = []

    def _render_field(match: re.Match[str]) -> str:
        name = match.group(1)
        spec = spec_by_name.get(name)

        if spec is None:
            unknown.append(name)
            return PLACEHOLDER_FORMAT.format(label=f"unknown field '{name}'")

        raw = values.get(name)
        present = raw is not None and (not isinstance(raw, str) or raw.strip() != "")

        if present:
            return str(raw)

        if spec.required:
            missing_required.append(name)
            return ""  # body is discarded anyway when blocked

        outstanding.append({"field": name, "label": spec.label, "language": language})
        return PLACEHOLDER_FORMAT.format(label=spec.label)

    body = _FIELD_RE.sub(_render_field, body)

    # --- 4. Leftovers ------------------------------------------------------
    # Anything still tag-shaped is a malformed or unclosed construct. It must
    # never reach a client document, so it is reported rather than emitted.
    leftovers = _ANY_TAG_RE.findall(body)
    if leftovers:
        unknown.extend(leftovers)
        body = _ANY_TAG_RE.sub("", body)

    body = _tidy(body)

    blocked = bool(missing_required)
    return RenderResult(
        body=None if blocked else body,
        blocked=blocked,
        missing_required=sorted(set(missing_required)),
        outstanding_fields=outstanding,
        unknown_tags=sorted(set(unknown + missing_blocks)),
    )


def _tidy(text: str) -> str:
    """Collapse the blank-line debris conditionals leave behind.

    Trailing whitespace is stripped EXCEPT for a markdown hard break — two or
    more trailing spaces, normalised to exactly two. Without this exception a
    multi-line address block collapses onto one line, because markdown ignores
    a single newline. Learned from the first real generated document, where
    "RECOSA SRL / Rue X / Company number Y" rendered as one run-on line.
    """
    text = re.sub(
        r"[ \t]*\n",
        lambda m: "  \n" if len(m.group(0)) >= 3 else "\n",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# ---------------------------------------------------------------------------
# Block renderers
# ---------------------------------------------------------------------------
# Tabular content is built here, not expressed in the template body (D-01a).
# A markdown table with a variable row count cannot be a merge field without
# putting loops in the template, and loops in the template are the thing the
# template-first decision exists to avoid.

_COOKIE_TABLE_HEADERS = {
    "en": ("Vendor", "Purpose", "Category", "Role"),
    "fr": ("Fournisseur", "Finalité", "Catégorie", "Rôle"),
    "nl": ("Leverancier", "Doel", "Categorie", "Rol"),
    "de": ("Anbieter", "Zweck", "Kategorie", "Rolle"),
}

_NO_VENDORS = {
    "en": "_No third-party services are currently recorded._",
    "fr": "_Aucun service tiers n'est actuellement enregistré._",
    "nl": "_Er zijn momenteel geen diensten van derden geregistreerd._",
    "de": "_Derzeit sind keine Drittanbieterdienste erfasst._",
}


def render_cookie_table(context: Mapping[str, Any], language: str) -> str:
    """Vendor table for the Cookie Policy, from the S24 inventory.

    Expects context["vendors"]: a sequence of mappings already resolved to the
    target language by inventory.py, which owns label translation and the
    English fallback for missing NL/DE.
    """
    vendors = context.get("vendors") or []
    if not vendors:
        return _NO_VENDORS.get(language, _NO_VENDORS["en"])

    headers = _COOKIE_TABLE_HEADERS.get(language, _COOKIE_TABLE_HEADERS["en"])
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
    ]
    for v in vendors:
        cells = [
            _cell(v.get("vendor_name")),
            _cell(v.get("purpose")),
            _cell(v.get("category_label")),
            _cell(v.get("role_label")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    """Escape pipes so a vendor name never breaks the table structure."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


DEFAULT_BLOCK_RENDERERS: dict[str, BlockRenderer] = {
    "cookie_table": render_cookie_table,
}
