"""
template_nis2.py — S29A. Incident response, breach notification, continuity.

TIER 2 — AND WHAT THAT MEANS HERE
---------------------------------
S28 turned out to be Tier 1: Art. 13/14 prescribe the content and every
prescribed item was structured data. NIS2 Art. 21(2) does the opposite. It
names ten AREAS an entity must have measures for and says nothing about what
the measures are. The answer is specific to the organisation and the inventory
does not hold it.

So these documents need prose RECOSA cannot derive. The question is where it
comes from.

INSERTS ARE STORED ON THE CLIENT AND DRAFTED ONCE — NOT GENERATED PER RENDER
---------------------------------------------------------------------------
Each insert is a column on `clients`, drafted by an LLM the first time, edited
by the client, then merged like any other field.

This is D-43/D-44 extended: RECOSA supplies a defensible starting point, the
client owns the answer, and it is not scored. The only new thing is that the
starting point is drafted rather than hand-authored.

*Rejected — generating prose at render time.* Every regeneration would produce
different text; nothing would be reviewable before it landed in a document; and
a lawyer reviewing a template would be reviewing a shape rather than a
document. That is the whole of template-first (D-01), and Tier 2 is not a
reason to abandon it — it is a reason to move the LLM one step earlier, to
where a human still sees the output.

Consequence: `retrieve(regulations=["NIS2"])` is called when DRAFTING, not when
rendering. First real use of the D-70 filter, and the reason it exists — the
diagnostic showed a NIS2 question in plain language returns AI Act or GDPR
chunks, because the AI Act holds 39% of the collection.

THE BREACH PROCEDURE IS TWO REGIMES
-----------------------------------
                    GDPR Art. 33          NIS2 Art. 23
    trigger         personal data breach   significant incident
    to              supervisory authority  CSIRT / competent authority
    clock           72 hours               24h early warning, 72h notification,
                                           1 month final report

Most incidents are one or the other. Some are both — ransomware on a system
holding personal data starts both clocks, and the 24-hour one binds.

One document, two decision paths, and an explicit both-apply case. Two separate
documents would make a client under time pressure choose between them in the
first hour, which is exactly when they are least able to.
"""

from __future__ import annotations

from typing import Any, Mapping

from template_renderer import Block, FieldSpec


# ── Drafted inserts ───────────────────────────────────────────────────────
# Each is a column on `clients`. The key is the column name; the prompt is what
# the LLM is asked to draft when the client has nothing yet.
#
# Prompts are deliberately narrow. "Describe your access control policy"
# produces a page of plausible nothing; "in two or three sentences, say who
# grants access and how it is removed when someone leaves" produces something
# a client can correct.

INSERTS: dict[str, dict[str, str]] = {
    "nis2_detection_text": {
        "column": "nis2_detection_i18n",
        "label": "How incidents are detected",
        "prompt": (
            "In two or three sentences, describe how this organisation would "
            "notice a cybersecurity incident: monitoring, alerts, staff "
            "reports, supplier notification. Write it as a statement of what "
            "they do, not as advice."
        ),
        "query": "NIS2 incident detection and monitoring obligations",
    },
    "nis2_containment_text": {
        "column": "nis2_containment_i18n",
        "label": "Containment and recovery steps",
        "prompt": (
            "In three or four sentences, describe the immediate steps this "
            "organisation takes to contain a cybersecurity incident and "
            "restore service: isolating affected systems, restoring from "
            "backup, confirming the cause is closed before reconnecting."
        ),
        "query": "NIS2 incident handling containment recovery measures",
    },
    "nis2_roles_text": {
        "column": "nis2_roles_i18n",
        "label": "Who does what during an incident",
        "prompt": (
            "In two or three sentences, describe who leads an incident, who "
            "decides whether to notify an authority, and who speaks to "
            "customers. Use roles rather than names — a plan naming a person "
            "who has left is worse than one naming a role."
        ),
        "query": "NIS2 incident response governance management body",
    },
    "nis2_continuity_text": {
        "column": "nis2_continuity_i18n",
        "label": "How the business keeps running",
        "prompt": (
            "In three or four sentences, describe how this organisation "
            "continues to operate while a critical system is unavailable: "
            "manual fallbacks, alternative tools, which activities stop."
        ),
        "query": "NIS2 business continuity crisis management backup",
    },
    "nis2_testing_text": {
        "column": "nis2_testing_i18n",
        "label": "How the plan is tested",
        "prompt": (
            "In two sentences, describe how and how often this organisation "
            "tests that it can recover: restore tests, tabletop exercises, "
            "who reviews the outcome. An untested plan is a document, not a "
            "capability — say so if testing is not yet in place."
        ),
        "query": "NIS2 testing effectiveness assessment of measures",
    },
}


# ── Fields ────────────────────────────────────────────────────────────────
# Identity fields are declared per doc_type — check_bodies() validates each
# template against its OWN list, so a body may only reference what its doc_type
# declares (the S28 lesson).

# No registered_address, no enterprise_number.
#
# These are INTERNAL procedures — read by staff during an incident, not filed
# with anyone — so a postal address is noise. It also matters mechanically:
# check_bodies rule 6 rejects a required field no body references, because it
# would block generation and change nothing. Declaring the same identity block
# for every document type is convenient and wrong.
# Only what EVERY one of the three uses. Contact details and the DPO are added
# per document, because the continuity plan uses neither — it defers to the
# incident response plan for both, and declaring contact_email as required
# there would block generation on a field no body references (check_bodies
# rule 6).
#
# Declaring one identity block for every doc_type is convenient and wrong. It
# was wrong twice in this sprint before the rule caught it.
_IDENTITY = [
    FieldSpec("legal_name", "Legal name of the company", required=True),
    FieldSpec("legal_form", "Legal form"),
    FieldSpec("has_legal_form", "Legal form recorded", flag=True),
    FieldSpec("policy_effective_date", "Effective from"),
    FieldSpec("has_policy_effective_date", "Effective date known", flag=True),
]

_CONTACT = [
    FieldSpec("contact_email", "Contact for incidents", required=True),
    FieldSpec("dpo_name", "Data Protection Officer name"),
    FieldSpec("dpo_email", "Data Protection Officer email"),
    FieldSpec("has_dpo_section", "DPO appointed", flag=True),
]

_ENTITY = [
    FieldSpec("nis2_entity_class_label", "NIS2 classification"),
    FieldSpec("has_nis2_class", "Classification recorded", flag=True),
]

IR_FIELDS = _IDENTITY + _CONTACT + _ENTITY + [
    FieldSpec("nis2_detection_text", "How incidents are detected", required=True),
    FieldSpec("nis2_containment_text", "Containment and recovery", required=True),
    FieldSpec("nis2_roles_text", "Who does what", required=True),
    FieldSpec("has_critical_systems", "At least one system recorded", flag=True),
]

BREACH_FIELDS = _IDENTITY + _CONTACT + _ENTITY + [
    FieldSpec("authority_name", "Supervisory authority", required=True),
    FieldSpec("authority_url", "Supervisory authority website"),
    FieldSpec("has_authority_url", "Authority website known", flag=True),
    FieldSpec("csirt_name", "National CSIRT", required=True),
    FieldSpec("csirt_url", "CSIRT website"),
    FieldSpec("has_csirt_url", "CSIRT website known", flag=True),
    FieldSpec("nis2_roles_text", "Who does what", required=True),
    # Both regimes can bite at once. The flag exists so the template can say so
    # rather than leaving a client to work it out mid-incident.
    FieldSpec("has_both_regimes", "Subject to GDPR and NIS2", flag=True),
]

BCP_FIELDS = _IDENTITY + _ENTITY + [
    FieldSpec("nis2_continuity_text", "How the business keeps running", required=True),
    FieldSpec("nis2_testing_text", "How the plan is tested", required=True),
    FieldSpec("has_recovery_objectives", "Recovery objectives recorded", flag=True),
    FieldSpec("has_unset_objectives", "Some systems have no objectives", flag=True),
]

IR_BLOCKS = ("nis2_systems",)
BREACH_BLOCKS = ("nis2_timeline",)
BCP_BLOCKS = ("nis2_recovery",)


# ── Loaders ───────────────────────────────────────────────────────────────

# Singular and plural per language, the same table shape as S26C's retention
# units and for the same reason: one label column cannot express "1 heure" and
# "2 heures". Dutch "uur" is invariant, which is why it needs saying rather
# than assuming.
_UNITS = {
    "en": {"minute": ("minute", "minutes"), "hour": ("hour", "hours"),
           "day": ("day", "days")},
    "fr": {"minute": ("minute", "minutes"), "hour": ("heure", "heures"),
           "day": ("jour", "jours")},
    "nl": {"minute": ("minuut", "minuten"), "hour": ("uur", "uur"),
           "day": ("dag", "dagen")},
}
_NONE = {"en": "none", "fr": "aucune", "nl": "geen"}


def _fmt_minutes(m: int | None, language: str) -> str:
    """Minutes as something a person reads. 240 -> '4 hours', 60 -> '1 hour'.

    Stored as minutes because a plan that orders systems by urgency must sort
    numerically; rendered in the largest whole unit because "480 minutes" in a
    continuity plan is a number nobody pictures.
    """
    if m is None:
        return "—"
    lang = language if language in _UNITS else "en"
    if m == 0:
        return _NONE.get(lang, _NONE["en"])

    if m < 60:
        value, unit = m, "minute"
    elif m < 60 * 24:
        value, unit = m / 60, "hour"
    else:
        value, unit = m / (60 * 24), "day"

    if float(value).is_integer():
        n, plural = int(value), int(value) != 1
    else:
        n, plural = round(value, 1), True
        if lang == "fr":
            # French uses a comma as the decimal separator. "1.5 heures" in a
            # French document reads as a typo.
            n = str(n).replace(".", ",")

    singular, many = _UNITS[lang][unit]
    return f"{n} {many if plural else singular}"


_CLASS_LABELS = {
    "essential": {"en": "Essential entity (Annex I)",
                  "fr": "Entité essentielle (annexe I)",
                  "nl": "Essentiële entiteit (bijlage I)"},
    "important": {"en": "Important entity (Annex II)",
                  "fr": "Entité importante (annexe II)",
                  "nl": "Belangrijke entiteit (bijlage II)"},
    "out_of_scope": {"en": "Not in scope", "fr": "Hors champ d'application",
                     "nl": "Buiten toepassingsgebied"},
}


def build_nis2_block_context(
    client_id: str, language: str,
) -> tuple[dict[str, Any], str | None]:
    """Systems, ordered by how urgently they must come back."""
    from template_store import _load_inventory  # noqa: PLC0415

    inv = _load_inventory(client_id)
    if inv.get("error"):
        return {}, inv["error"]

    systems = inv["systems"]

    # Ordered by RTO, tightest first, with unset last. A continuity plan is
    # read under pressure and its order IS its priority — alphabetical would
    # be worse than useless.
    ordered = sorted(
        systems,
        key=lambda s: (s.get("rto_minutes") is None, s.get("rto_minutes") or 0),
    )
    return {
        "nis2_systems": ordered,
        "nis2_has_objectives": any(
            s.get("rto_minutes") is not None or s.get("rpo_minutes") is not None
            for s in systems
        ),
        "nis2_unset": [
            s for s in systems
            if s.get("rto_minutes") is None and s.get("rpo_minutes") is None
        ],
        "nis2_activities": inv["activities"],
    }, None


# ── Renderers ─────────────────────────────────────────────────────────────

_H = {
    "en": {"system": "System", "vendor": "Provider", "rto": "Back within",
           "rpo": "Data loss limit", "how": "How it is recovered",
           "crit": "Criticality", "not_set": "not set",
           "when": "When", "who": "Who to tell", "what": "What to send"},
    "fr": {"system": "Système", "vendor": "Fournisseur",
           "rto": "Rétabli sous", "rpo": "Perte de données admise",
           "how": "Modalités de rétablissement", "crit": "Criticité",
           "not_set": "non défini", "when": "Quand",
           "who": "Qui prévenir", "what": "Que transmettre"},
    "nl": {"system": "Systeem", "vendor": "Leverancier", "rto": "Hersteld binnen",
           "rpo": "Toegestaan gegevensverlies", "how": "Wijze van herstel",
           "crit": "Kritikaliteit", "not_set": "niet ingesteld",
           "when": "Wanneer", "who": "Wie informeren", "what": "Wat versturen"},
}


def _t(language: str, key: str) -> str:
    return _H.get(language, _H["en"]).get(key, _H["en"][key])


def render_nis2_systems(context: Mapping[str, Any], language: str) -> Block:
    """Systems and how they are recovered. Ordered by urgency, not by name."""
    from inventory import label_for  # noqa: PLC0415

    block = Block(
        name="nis2_systems",
        headers=[_t(language, "system"), _t(language, "vendor"),
                 _t(language, "crit")],
    )
    for s in context.get("nis2_systems") or []:
        block.rows.append([
            s.get("name") or "",
            s.get("vendor_legal_name") or "",
            label_for("criticality", s.get("criticality") or "", language)
            if s.get("criticality") else "—",
        ])
    return block


def render_nis2_recovery(context: Mapping[str, Any], language: str) -> Block:
    """The continuity table: how fast, how much loss, and how.

    Systems with no objectives are INCLUDED, showing "not set". Dropping them
    would make the plan look complete while saying nothing about the systems
    nobody has thought about — which are the ones most likely to fail badly.
    """
    block = Block(
        name="nis2_recovery",
        headers=[_t(language, "system"), _t(language, "rto"),
                 _t(language, "rpo"), _t(language, "how")],
    )
    for s in context.get("nis2_systems") or []:
        rto = s.get("rto_minutes")
        rpo = s.get("rpo_minutes")
        block.rows.append([
            s.get("name") or "",
            _fmt_minutes(rto, language) if rto is not None
            else _t(language, "not_set"),
            _fmt_minutes(rpo, language) if rpo is not None
            else _t(language, "not_set"),
            s.get("recovery_note") or "—",
        ])
    return block


# The reporting timeline. Static per language and per regime — it is the law,
# not the client's data, so it is a renderer rather than a merge field only to
# keep the two regimes in one table where they can be compared.
_TIMELINE = {
    "en": [
        ("Within 24 hours", "NIS2 — CSIRT",
         "Early warning: that an incident happened, whether it looks "
         "malicious, and whether it may have cross-border effect."),
        ("Within 72 hours", "NIS2 — CSIRT",
         "Incident notification: an assessment of severity and impact, "
         "indicators of compromise where available."),
        ("Within 72 hours", "GDPR — supervisory authority",
         "Where personal data is affected: nature of the breach, categories "
         "and approximate numbers, likely consequences, measures taken."),
        ("Without undue delay", "GDPR — the people affected",
         "Only where the breach is likely to result in a high risk to them."),
        ("Within one month", "NIS2 — CSIRT",
         "Final report: root cause, mitigation applied, cross-border impact."),
    ],
    "fr": [
        ("Dans les 24 heures", "NIS2 — CSIRT",
         "Alerte précoce : qu'un incident est survenu, s'il semble d'origine "
         "malveillante et s'il peut avoir un impact transfrontalier."),
        ("Dans les 72 heures", "NIS2 — CSIRT",
         "Notification d'incident : évaluation de la gravité et de l'impact, "
         "indicateurs de compromission le cas échéant."),
        ("Dans les 72 heures", "RGPD — autorité de contrôle",
         "Lorsque des données à caractère personnel sont concernées : nature "
         "de la violation, catégories et nombre approximatif de personnes, "
         "conséquences probables, mesures prises."),
        ("Dans les meilleurs délais", "RGPD — les personnes concernées",
         "Uniquement lorsque la violation est susceptible d'engendrer un "
         "risque élevé pour elles."),
        ("Dans un délai d'un mois", "NIS2 — CSIRT",
         "Rapport final : cause profonde, mesures d'atténuation appliquées, "
         "impact transfrontalier."),
    ],
}


def render_nis2_timeline(context: Mapping[str, Any], language: str) -> Block:
    rows = _TIMELINE.get(language, _TIMELINE["en"])
    block = Block(
        name="nis2_timeline",
        headers=[_t(language, "when"), _t(language, "who"),
                 _t(language, "what")],
    )
    for when, who, what in rows:
        block.rows.append([when, who, what])
    return block


NIS2_BLOCK_RENDERERS = {
    "nis2_systems":  render_nis2_systems,
    "nis2_recovery": render_nis2_recovery,
    "nis2_timeline": render_nis2_timeline,
}


def apply_nis2_values(
    values: dict[str, Any],
    client: Mapping[str, Any],
    block_context: Mapping[str, Any] | None,
    language: str,
) -> None:
    """Flags and inserts. Every omitted section is omitted on a fact."""
    ctx = block_context or {}

    # Per language, falling back to English then to the legacy TEXT column.
    #
    # These shipped as single-language TEXT and produced English paragraphs
    # under French headings — the S26C defect one sprint later, and worse,
    # because a mistranslated containment procedure is acted on at 2am.
    for key, spec in INSERTS.items():
        blob = client.get(spec["column"]) or {}
        text = ""
        if isinstance(blob, Mapping):
            for lang in (language, "en"):
                if (blob.get(lang) or "").strip():
                    text = blob[lang].strip()
                    break
        values[key] = text or (client.get(key) or "")

    cls = client.get("nis2_entity_class")
    values["has_nis2_class"] = bool(cls)
    values["nis2_entity_class_label"] = (
        _CLASS_LABELS.get(cls, {}).get(language)
        or _CLASS_LABELS.get(cls, {}).get("en") or ""
    )

    values["has_critical_systems"] = bool(ctx.get("nis2_systems"))
    values["has_recovery_objectives"] = bool(ctx.get("nis2_has_objectives"))
    values["has_unset_objectives"] = bool(ctx.get("nis2_unset"))

    # Both regimes bite where the client processes personal data at all — which
    # is any client with a RoPA. Said explicitly in the document because the
    # 24-hour clock is the binding one and a client reading only the GDPR
    # procedure would miss it.
    values["has_both_regimes"] = bool(ctx.get("nis2_activities"))

    values["has_policy_effective_date"] = bool(values.get("policy_effective_date"))
    values["has_authority_url"] = bool(values.get("authority_url"))
    values["has_csirt_url"] = bool(values.get("csirt_url"))
