"""
template_dpia.py — S30. DPIA and NIS2 risk assessment documents.

TIER 3. The first documents RECOSA produces from a JUDGEMENT rather than from a
description.

A RoPA describes processing. A privacy policy discloses it. A DPIA says whether
it is acceptable, and that conclusion is not in the inventory — it is what the
client decided, risk by risk, in the register.

ONE MODULE, TWO DOCUMENTS, TWO MEANINGS (D-85)
-----------------------------------------------
The table is the same shape either way. What it measures is not:

    DPIA   risk to the rights and freedoms of natural persons
           high residual risk -> Art. 36 prior consultation, BEFORE processing
    NIS2   risk to network and information systems
           high residual risk -> a named person accepts it, or nobody has

The conclusion at the foot of each document is therefore different, and the
severity column means different things. Sharing the wording would have implied
a consequence that does not exist on one side.

WHAT THE TEMPLATE DOES NOT DECIDE
---------------------------------
`consultation_required` is computed by risk_assessment.consultation_needed()
over the items. The template renders it and never derives it — a client must
not be able to assert either way that prior consultation does or does not
apply, and a flag set in a page could be set wrongly.
"""

from __future__ import annotations

from typing import Any, Mapping

from template_renderer import Block, FieldSpec


_IDENTITY = [
    FieldSpec("legal_name", "Legal name of the company", required=True),
    FieldSpec("legal_form", "Legal form"),
    FieldSpec("has_legal_form", "Legal form recorded", flag=True),
    FieldSpec("policy_effective_date", "Effective from"),
    FieldSpec("has_policy_effective_date", "Effective date known", flag=True),
]

_ASSESSMENT = [
    FieldSpec("assessment_title", "What this assesses", required=True),
    FieldSpec("assessment_scope", "Scope note"),
    FieldSpec("has_scope_note", "Scope described", flag=True),
    FieldSpec("has_risks", "At least one risk recorded", flag=True),
    FieldSpec("has_unassessed", "Some risks not assessed after measures", flag=True),
]

DPIA_FIELDS = _IDENTITY + _ASSESSMENT + [
    # ONE composed field, not a name plus a conditional URL.
    #
    # The first version nested {{#if:has_authority_url}} inside
    # {{#if:needs_consultation}}. Conditionals do not nest — the non-greedy
    # match ends the OUTER conditional at the INNER closing tag — and this is
    # the fourth time that has been written in this codebase despite being
    # documented at the top of template_renderer.py.
    #
    # Composing in code removes the possibility rather than the instance.
    FieldSpec("authority_line", "Supervisory authority", required=True),

    # Derived, never entered. The conclusion the document exists to reach.
    FieldSpec("needs_consultation", "Art. 36 prior consultation required",
              flag=True),

    FieldSpec("dpo_name", "Data Protection Officer name"),
    # Tri-state collapsed to two flags: "we did not ask" and "we have not said
    # whether we asked" are different, and the document says which.
    FieldSpec("dpo_advice", "The DPO's advice"),
    FieldSpec("has_dpo_advice", "DPO advice recorded", flag=True),
    FieldSpec("dpo_not_consulted", "DPO advice explicitly not sought", flag=True),

    FieldSpec("has_processing_table", "Processing described", flag=True),
]

NIS2RA_FIELDS = _IDENTITY + _ASSESSMENT + [
    FieldSpec("has_unaccepted", "High risks nobody has accepted", flag=True),
    FieldSpec("has_systems_table", "Systems in scope recorded", flag=True),
]

DPIA_BLOCKS = ("dpia_processing", "dpia_risks")
NIS2RA_BLOCKS = ("nis2ra_systems", "dpia_risks")


# ── Renderers ─────────────────────────────────────────────────────────────

_H = {
    "en": {"risk": "What could happen", "case": "In our case",
           "before": "Before measures", "controls": "What already reduces it",
           "measures": "What we will do", "after": "After measures",
           "accepted": "Accepted by", "activity": "Activity",
           "purpose": "Purpose", "basis": "Legal basis", "data": "Data",
           "system": "System", "crit": "Criticality", "rto": "Back within",
           "unassessed": "not assessed", "none": "—"},
    "fr": {"risk": "Ce qui pourrait arriver", "case": "Dans notre cas",
           "before": "Avant mesures", "controls": "Ce qui le réduit déjà",
           "measures": "Ce que nous allons faire", "after": "Après mesures",
           "accepted": "Accepté par", "activity": "Activité",
           "purpose": "Finalité", "basis": "Base légale", "data": "Données",
           "system": "Système", "crit": "Criticité", "rto": "Rétabli sous",
           "unassessed": "non évalué", "none": "—"},
}


def _t(language: str, key: str) -> str:
    return _H.get(language, _H["en"]).get(key, _H["en"][key])


def render_dpia_risks(context: Mapping[str, Any], language: str) -> Block:
    """The register itself.

    Likelihood and severity are shown as a PAIR, never multiplied. A 1x4 and a
    4x1 share a product and are completely different situations — one is rare
    and catastrophic, the other constant and trivial, and a score hides which
    (D-85).
    """
    from inventory import label_for  # noqa: PLC0415
    from risk_assessment import level_label  # noqa: PLC0415

    vocab = context.get("risk_vocab") or "dpia_risk"
    is_nis2 = vocab == "nis2_risk"

    headers = [_t(language, "risk"), _t(language, "before"),
               _t(language, "measures"), _t(language, "after")]
    if is_nis2:
        headers.append(_t(language, "accepted"))

    block = Block(name="dpia_risks", headers=headers)
    for it in context.get("risk_items") or []:
        label = label_for(vocab, it.get("catalogue_code") or "", language)
        what = f"**{label}**"
        if it.get("description"):
            # The line that proves the assessment was done rather than ticked
            # through. An authority reading five bare catalogue labels learns
            # nothing about whether anyone thought about it.
            what += f" — {it['description']}"

        before = (f"{level_label(it.get('likelihood'), language)} / "
                  f"{level_label(it.get('severity'), language)}")
        after = (
            f"{level_label(it.get('residual_likelihood'), language)} / "
            f"{level_label(it.get('residual_severity'), language)}"
            if it.get("residual_severity") is not None
            else _t(language, "unassessed")
        )
        measures = "\n".join(filter(None, [
            it.get("existing_controls"), it.get("additional_measures"),
        ])) or _t(language, "none")

        row = [what, before, measures, after]
        if is_nis2:
            row.append(it.get("accepted_by") or _t(language, "none"))
        block.rows.append(row)
    return block


def render_dpia_processing(context: Mapping[str, Any], language: str) -> Block:
    """Art. 35(7)(a) — a systematic description of the processing.

    The same content as the RoPA, arranged for a different question. Not
    duplicated data: read from the same activities, scoped to what this
    assessment covers.
    """
    from inventory import label_for  # noqa: PLC0415
    from template_store import _i18n, build_retention_cells  # noqa: PLC0415

    block = Block(
        name="dpia_processing",
        headers=[_t(language, "activity"), _t(language, "purpose"),
                 _t(language, "basis"), _t(language, "data")],
    )
    for a in context.get("scoped_activities") or []:
        block.rows.append([
            _i18n(a, "name", language) or a.get("name") or "",
            _i18n(a, "purpose", language) or a.get("purpose") or "",
            label_for("legal_basis", a.get("legal_basis") or "", language)
            if a.get("legal_basis") else _t(language, "none"),
            ", ".join(label_for("data_category", c, language)
                      for c in (a.get("data_categories") or []))
            or _t(language, "none"),
        ])
    return block


def render_nis2ra_systems(context: Mapping[str, Any], language: str) -> Block:
    from inventory import label_for  # noqa: PLC0415
    from template_nis2 import _fmt_minutes  # noqa: PLC0415

    block = Block(
        name="nis2ra_systems",
        headers=[_t(language, "system"), _t(language, "crit"),
                 _t(language, "rto")],
    )
    for s in context.get("scoped_systems") or []:
        block.rows.append([
            s.get("name") or "",
            label_for("criticality", s.get("criticality") or "", language)
            if s.get("criticality") else _t(language, "none"),
            _fmt_minutes(s.get("rto_minutes"), language),
        ])
    return block


DPIA_BLOCK_RENDERERS = {
    "dpia_risks": render_dpia_risks,
    "dpia_processing": render_dpia_processing,
    "nis2ra_systems": render_nis2ra_systems,
}


def build_dpia_block_context(
    client_id: str, language: str, assessment_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Everything a risk assessment document renders.

    Needs an assessment_id: a client may hold several, and a document about
    "all of them" answers no question. Where none is given, the most recent
    complete one is used and the caller is told which.
    """
    from database import get_supabase  # noqa: PLC0415
    from template_store import _load_inventory  # noqa: PLC0415

    try:
        q = (get_supabase().table("risk_assessments").select("*")
             .eq("client_id", client_id))
        if assessment_id:
            q = q.eq("id", assessment_id)
        else:
            q = q.order("created_at", desc=True).limit(1)
        rows = q.execute().data or []
    except Exception as e:
        return {}, f"Could not read the assessment: {e}"

    if not rows:
        return {}, ("No risk assessment has been created yet. Start one under "
                    "Risk assessments.")
    a = rows[0]

    try:
        items = (get_supabase().table("risk_items").select("*")
                 .eq("assessment_id", a["id"]).order("created_at")
                 .execute().data or [])
    except Exception as e:
        return {}, f"Could not read the risk register: {e}"

    inv = _load_inventory(client_id)
    if inv.get("error"):
        return {}, inv["error"]

    scoped_ids = set(a.get("activity_ids") or [])
    sys_ids = set(a.get("system_ids") or [])

    return {
        "assessment": a,
        "risk_items": items,
        "risk_vocab": "dpia_risk" if a["regulation"] == "GDPR" else "nis2_risk",
        # Empty scope means everything. Valid for a NIS2 assessment; for a
        # DPIA it means the client did not narrow it, and the document says so
        # rather than silently covering the lot.
        "scoped_activities": [
            x for x in inv["activities"]
            if not scoped_ids or x["id"] in scoped_ids
        ],
        "scoped_systems": [
            x for x in inv["systems"] if not sys_ids or x["id"] in sys_ids
        ],
    }, None


def apply_dpia_values(
    values: dict[str, Any],
    client: Mapping[str, Any],
    block_context: Mapping[str, Any] | None,
    language: str,
) -> None:
    from risk_assessment import consultation_needed, nis2_unaccepted  # noqa: PLC0415

    ctx = block_context or {}
    a = ctx.get("assessment") or {}
    items = ctx.get("risk_items") or []

    values["assessment_title"] = a.get("title") or ""
    values["assessment_scope"] = a.get("scope_note") or ""
    values["has_scope_note"] = bool(a.get("scope_note"))
    values["has_risks"] = bool(items)
    values["has_unassessed"] = any(
        it.get("residual_severity") is None for it in items
    )
    values["has_processing_table"] = bool(ctx.get("scoped_activities"))
    values["has_systems_table"] = bool(ctx.get("scoped_systems"))

    # DERIVED. Never a flag the page sets — a client must not be able to assert
    # that Art. 36 does or does not apply to them.
    verdict = consultation_needed(items)
    values["needs_consultation"] = bool(verdict.get("required"))

    values["has_unaccepted"] = bool(nis2_unaccepted(items).get("unaccepted"))

    # Art. 35(2). Three states, two flags: advice recorded, explicitly not
    # sought, or neither — and "neither" renders nothing rather than implying
    # an answer.
    values["dpo_advice"] = a.get("dpo_advice") or ""
    values["has_dpo_advice"] = bool(
        a.get("dpo_consulted") and (a.get("dpo_advice") or "").strip()
    )
    values["dpo_not_consulted"] = a.get("dpo_consulted") is False

    values["has_policy_effective_date"] = bool(values.get("policy_effective_date"))

    # "Name (url)" or just "Name". Composed here so the template needs one
    # merge field and no conditional — see the note on authority_line above.
    _name = values.get("authority_name") or ""
    _url = values.get("authority_url") or ""
    values["authority_line"] = f"{_name} ({_url})" if _name and _url else _name
