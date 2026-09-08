"""
template_privacy.py — S28. Privacy Policy (Art. 13 and 14 GDPR).

TIER 1. NO LLM.
--------------
The roadmap called this Tier 2, "first LLM inserts". It does not need them.

Art. 13 and 14 prescribe the content: identity and contact details, DPO,
purposes, legal bases, legitimate interests where relied on, recipients,
third-country transfers and safeguards, retention, data subject rights,
withdrawal, complaint route, and — for Art. 14 — the categories of data and
where it came from.

Every one of those is structured data after S26, S26C and S28 part 1. A privacy
policy is the controller register rendered for a public audience: same source,
different reader.

The evidence agrees. The privacy policy went from 30-40% to 80% review scores by
constraining toward fixed structure. The reading is that constraint produced the
gain, and the remaining 20% is more constraint rather than better prose.

GROUPED BY DATA SUBJECT, NOT BY ACTIVITY
----------------------------------------
"If you are a customer / an employee / a supplier contact" is how a reader
arrives at this document. Fifteen activities listed flat is a register, not a
policy.

An employee who is also a customer reads both sections, and that is correct:
they are subject to two distinct sets of processing with different purposes,
bases and retention. Transparency is per processing, not per person.

So role sections carry ONLY what varies — purposes, bases, data, retention,
source. Everything universal is stated once outside them: rights, complaints,
transfers, security, changes. An activity covering both employees and customers
appears in both sections; a few duplicated lines beat a cross-reference telling
a reader to look somewhere else.
"""

from __future__ import annotations

from typing import Any, Mapping

from template_renderer import Block, FieldSpec


# ── Fields ────────────────────────────────────────────────────────────────
# Identity fields are shared with the registers and come from the common block
# in build_values(); only what is specific to this document is declared here.

PRIVACY_FIELDS = [
    # Identity. Declared per doc_type, not inherited: build_values() populates
    # these for every document, but check_bodies() validates each template
    # against its OWN FieldSpec list — so a body may only reference what its
    # doc_type declares. Each document also decides for itself what is
    # required, and the answers differ.
    FieldSpec("legal_name", "Legal name of the company", required=True),
    FieldSpec("registered_address", "Registered address", required=True),
    FieldSpec("enterprise_number", "Company registration number"),
    FieldSpec("legal_form", "Legal form"),
    FieldSpec("has_legal_form", "Legal form recorded", flag=True),
    FieldSpec("has_enterprise_number", "Registration number recorded", flag=True),

    # required=True. Art. 13(1)(a)-(b) requires contact details, and a notice
    # telling someone they may exercise their rights without saying where to
    # write does not discharge it. The DPA takes the same view for a different
    # reason; the registers do not, because a supervisory authority already
    # knows how to reach the controller.
    FieldSpec("contact_email", "Contact for privacy matters", required=True),

    FieldSpec("dpo_name", "Data Protection Officer name"),
    FieldSpec("dpo_email", "Data Protection Officer email"),
    FieldSpec("has_dpo_section", "DPO appointed", flag=True),

    # Flags. Every section this document can omit is omitted on a fact, never
    # on a guess: a policy that describes transfers a client does not make is
    # as wrong as one that hides transfers they do.
    FieldSpec("has_role_sections", "At least one controller activity", flag=True),
    FieldSpec("has_art14", "Holds data not obtained from the data subject", flag=True),
    FieldSpec("has_public_source", "Some data came from a public source", flag=True),
    FieldSpec("has_recipients", "Shares data with named recipients", flag=True),
    FieldSpec("has_transfers", "Transfers data outside the EEA", flag=True),
    FieldSpec("has_special_categories", "Processes Art. 9 data", flag=True),

    # Rights are NOT universal — see rights_in_play(). Each flag is computed
    # from the legal bases actually in use.
    FieldSpec("has_right_withdraw", "Consent is a basis somewhere", flag=True),
    FieldSpec("has_right_object", "Legitimate interests or public task", flag=True),
    FieldSpec("has_right_portability", "Consent or contract", flag=True),
    FieldSpec("has_statutory_retention", "Some retention is legally required", flag=True),

    FieldSpec("policy_effective_date", "Effective from"),
    FieldSpec("has_policy_effective_date", "Effective date known", flag=True),
    # required=True: a notice that cannot tell the reader where to complain
    # fails Art. 13(2)(d). Not a placeholder case.
    FieldSpec("supervisory_authority", "Supervisory authority", required=True),
    FieldSpec("supervisory_authority_url", "Supervisory authority website"),
    FieldSpec("has_supervisory_authority_url", "Authority website known", flag=True),
]

PRIVACY_BLOCKS = ("privacy_role_sections", "privacy_recipients", "privacy_transfers")


# ── Rights depend on legal basis, and most policies get this wrong ────────
#
# A template listing every right unconditionally tells a data subject they can
# demand portability of records held under a statutory retention duty. That is a
# promise the client cannot keep, in a published document.
#
# Encoded as a check over the activity set rather than as prose, per the
# constraint that rules are executable — the same pattern that caught three
# Microsoft 365 activities in S24.

_CONSENT_BASES = {"consent", "explicit_consent"}
_CONTRACT_BASES = {"contract"}
_OBJECTION_BASES = {"legitimate_interests", "public_task"}
_STATUTORY_BASES = {"legal_obligation"}


def rights_in_play(activities: list[Mapping[str, Any]]) -> dict[str, bool]:
    """Which rights this client's processing actually gives rise to.

    Access, rectification and restriction are unconditional and are not
    returned — the template states them outright.
    """
    bases = {a.get("legal_basis") for a in activities if a.get("legal_basis")}
    return {
        # Art. 7(3). Only meaningful where consent is a basis for something.
        "has_right_withdraw": bool(bases & _CONSENT_BASES),
        # Art. 21. Does not apply to consent, contract or legal obligation.
        "has_right_object": bool(bases & _OBJECTION_BASES),
        # Art. 20. Consent or contract, AND processing carried out by automated
        # means — which is every activity in a system RECOSA knows about, so the
        # basis is the only live test.
        "has_right_portability": bool(bases & (_CONSENT_BASES | _CONTRACT_BASES)),
        # Not a right. Erasure is qualified where retention is legally required,
        # and the template says so rather than promising deletion it cannot do.
        "has_statutory_retention": bool(bases & _STATUTORY_BASES),
    }


# ── Loaders ───────────────────────────────────────────────────────────────

# Roles that mean the client decides purposes and means. A privacy policy is a
# CONTROLLER's disclosure: processor-role activities belong in the customer's
# own policy, and listing them here would tell a data subject that this client
# decides purposes they do not decide.
_CONTROLLER_ROLES = {"controller", "joint_controller"}


def _subject_groups(
    activities: list[Mapping[str, Any]], language: str,
) -> list[tuple[str, list[Mapping[str, Any]]]]:
    """Activities grouped by data subject category, in vocabulary order.

    An activity naming three subject categories appears in three groups. That
    is the point: a supplier contact reading the supplier section must see the
    processing that touches them, whether or not it also touches employees.

    Activities with no subject category recorded are grouped last under a
    heading that says so, rather than being dropped. A policy silently omitting
    processing is worse than one admitting a gap.
    """
    from inventory import options_for  # noqa: PLC0415

    codes, labels = options_for("data_subject_category", language, None)
    order = {c: i for i, c in enumerate(codes)}

    buckets: dict[str, list] = {}
    unassigned: list = []
    for a in activities:
        subs = [c for c in (a.get("data_subject_categories") or []) if c]
        if not subs:
            unassigned.append(a)
            continue
        for c in subs:
            buckets.setdefault(c, []).append(a)

    out = [
        (labels.get(c, c), rows)
        for c, rows in sorted(buckets.items(), key=lambda kv: order.get(kv[0], 999))
    ]
    if unassigned:
        out.append((None, unassigned))
    return out


def build_privacy_block_context(
    client_id: str, language: str,
) -> tuple[dict[str, Any], str | None]:
    """Everything the privacy policy renders, in one inventory pass."""
    from template_store import _load_inventory, _i18n  # noqa: PLC0415

    inv = _load_inventory(client_id)
    if inv.get("error"):
        return {}, inv["error"]

    acts = [
        a for a in inv["activities"]
        if a.get("controller_role") in _CONTROLLER_ROLES
    ]

    # Recipients: counterparties reached through controller activities only.
    # A vendor that only ever touches processor-role work is not a recipient of
    # the data this policy describes, and naming it would misstate the flow.
    act_ids = {a["id"] for a in acts}
    cp_by_id = {c["id"]: c for c in inv["counterparties"]}
    sys_by_id = {s["id"]: s for s in inv["systems"]}

    recipients: dict[str, dict[str, Any]] = {}
    for l in inv["cp_links"]:
        if l.get("activity_id") in act_ids:
            cp = cp_by_id.get(l.get("counterparty_id"))
            if cp:
                recipients[cp["id"]] = cp
    for l in inv["links"]:
        if l.get("activity_id") in act_ids:
            sysrow = sys_by_id.get(l.get("system_id"))
            if sysrow:
                recipients.setdefault(f"sys:{sysrow['id']}", sysrow)

    return {
        "privacy_activities": acts,
        "privacy_groups": _subject_groups(acts, language),
        "privacy_recipient_rows": list(recipients.values()),
        "privacy_transfer_rows": [
            r for r in recipients.values()
            if (r.get("processing_country") or "EU") not in ("EU", "EEA", "")
        ],
        "_i18n": _i18n,
    }, None


# ── Renderers ─────────────────────────────────────────────────────────────

_H = {
    "en": {
        "purpose": "What we do", "basis": "Why we are allowed to",
        "data": "What we hold", "retention": "How long",
        "recipient": "Who", "role": "What they do for us",
        "country": "Where", "safeguard": "Safeguard",
        "unassigned": "Other processing",
        "from_others": "We received this from someone other than you",
        "public": "This information was publicly available",
        "not_recorded": "not recorded",
    },
    "fr": {
        "purpose": "Ce que nous faisons", "basis": "Ce qui nous y autorise",
        "data": "Ce que nous détenons", "retention": "Durée",
        "recipient": "Qui", "role": "Ce qu'ils font pour nous",
        "country": "Où", "safeguard": "Garantie",
        "unassigned": "Autres traitements",
        "from_others": "Nous avons reçu ces données d'une autre personne que vous",
        "public": "Ces informations étaient accessibles au public",
        "not_recorded": "non renseigné",
    },
}


def _t(language: str, key: str) -> str:
    return _H.get(language, _H["en"]).get(key, _H["en"][key])


def _source_line(
    activity: Mapping[str, Any], language: str,
) -> str | None:
    """The Art. 14 disclosure, rendered ONLY where it applies.

    For most activities the answer is "you gave it to us", which is noise —
    and Art. 14 bites only where the data did NOT come from the data subject.
    So this returns None for the common case and a sentence for the rest.

    An empty list returns None too, but that is not the same statement: an
    unrecorded source means the policy says nothing about it, which is a gap
    the inventory page flags. It must never be read as "from the data subject"
    (see the column comment on data_source_codes).
    """
    from inventory import label_for, metadata_for  # noqa: PLC0415

    codes = [c for c in (activity.get("data_source_codes") or []) if c]
    art14 = [
        c for c in codes
        if metadata_for("data_source", c, None).get("art14")
    ]
    if not art14:
        return None

    names = [label_for("data_source", c, language) for c in art14]
    line = f"*{_t(language, 'from_others')}: " + ", ".join(names).lower() + ".*"
    if any(metadata_for("data_source", c, None).get("public") for c in art14):
        # Art. 14(2)(f) asks specifically whether the source was publicly
        # accessible, so it is a separate statement rather than an adjective.
        line += f" *{_t(language, 'public')}.*"
    return line


def render_privacy_role_sections(
    context: Mapping[str, Any], language: str,
) -> str:
    """One section per data subject category, each a short table.

    Markdown rather than a Block: this is several tables with headings between
    them, not one tabular structure, and a Block cannot express that. The
    registers are the tabular documents; this is prose with tables in it.
    """
    from inventory import label_for  # noqa: PLC0415
    from template_store import build_retention_cells  # noqa: PLC0415

    _i18n = context.get("_i18n")
    groups = context.get("privacy_groups") or []
    if not groups:
        return ""

    out: list[str] = []
    for label, rows in groups:
        heading = label or _t(language, "unassigned")
        out.append(f"### {heading}\n")

        out.append(
            f"| {_t(language,'purpose')} | {_t(language,'basis')} "
            f"| {_t(language,'data')} | {_t(language,'retention')} |"
        )
        out.append("| --- | --- | --- | --- |")

        notes: list[str] = []
        for a in rows:
            purpose = (_i18n(a, "purpose", language) if _i18n else None) \
                or a.get("purpose") or _t(language, "not_recorded")
            name = (_i18n(a, "name", language) if _i18n else None) or a.get("name") or ""
            basis = label_for("legal_basis", a.get("legal_basis") or "", language) \
                if a.get("legal_basis") else _t(language, "not_recorded")
            cats = ", ".join(
                label_for("data_category", c, language)
                for c in (a.get("data_categories") or [])
            ) or _t(language, "not_recorded")
            period, _ = build_retention_cells(a, language)

            cell = f"**{name}** — {purpose}" if name else purpose
            out.append(
                f"| {_cell(cell)} | {_cell(basis)} | {_cell(cats)} "
                f"| {_cell(period or _t(language,'not_recorded'))} |"
            )

            src = _source_line(a, language)
            if src:
                notes.append(f"- **{name or purpose}** — {src}")

        if notes:
            # Art. 14 sits under the table, not in it. A column that is empty
            # for four rows in five is a column that teaches the reader to
            # ignore it.
            out.append("")
            out.extend(notes)
        out.append("")

    return "\n".join(out).rstrip()


def _cell(v: Any) -> str:
    """Escape for a markdown table cell. Pipes and newlines both break rows."""
    s = "" if v is None else str(v)
    return s.replace("|", "\\|").replace("\n", " ").strip()


def render_privacy_recipients(context: Mapping[str, Any], language: str) -> Block:
    from inventory import label_for  # noqa: PLC0415

    block = Block(
        name="privacy_recipients",
        headers=[_t(language, "recipient"), _t(language, "role"),
                 _t(language, "country")],
    )
    for r in context.get("privacy_recipient_rows") or []:
        block.rows.append([
            r.get("legal_name") or r.get("vendor_legal_name") or r.get("name") or "",
            label_for("system_category", r.get("category") or "", language)
            if r.get("category") else "",
            r.get("processing_country") or r.get("country") or "EU",
        ])
    return block


def render_privacy_transfers(context: Mapping[str, Any], language: str) -> Block:
    from inventory import label_for  # noqa: PLC0415

    block = Block(
        name="privacy_transfers",
        headers=[_t(language, "recipient"), _t(language, "country"),
                 _t(language, "safeguard")],
    )
    for r in context.get("privacy_transfer_rows") or []:
        block.rows.append([
            r.get("legal_name") or r.get("vendor_legal_name") or r.get("name") or "",
            r.get("processing_country") or r.get("country") or "",
            label_for("transfer_mechanism", r.get("transfer_mechanism") or "", language)
            if r.get("transfer_mechanism") else _t(language, "not_recorded"),
        ])
    return block


PRIVACY_BLOCK_RENDERERS = {
    "privacy_role_sections": render_privacy_role_sections,
    "privacy_recipients":    render_privacy_recipients,
    "privacy_transfers":     render_privacy_transfers,
}


def apply_privacy_values(
    values: dict[str, Any],
    client: Mapping[str, Any],
    block_context: Mapping[str, Any] | None,
    language: str,
) -> None:
    """Set the flags. Every omitted section is omitted on a fact."""
    from inventory import metadata_for  # noqa: PLC0415

    ctx = block_context or {}
    acts = ctx.get("privacy_activities") or []

    values.update(rights_in_play(acts))
    values["has_role_sections"] = bool(ctx.get("privacy_groups"))
    values["has_recipients"] = bool(ctx.get("privacy_recipient_rows"))
    values["has_transfers"] = bool(ctx.get("privacy_transfer_rows"))
    values["has_special_categories"] = any(
        a.get("special_categories") for a in acts
    )

    art14_codes = {
        c for a in acts for c in (a.get("data_source_codes") or [])
        if metadata_for("data_source", c, None).get("art14")
    }
    values["has_art14"] = bool(art14_codes)
    values["has_public_source"] = any(
        metadata_for("data_source", c, None).get("public") for c in art14_codes
    )

    # Flags for fields the common block does not set. A URL the client has not
    # given renders as a placeholder inside a sentence about where to complain,
    # which reads worse than the sentence without it.
    values["has_policy_effective_date"] = bool(values.get("policy_effective_date"))
    values["has_supervisory_authority_url"] = bool(
        values.get("supervisory_authority_url")
    )
