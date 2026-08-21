"""
template_dpa.py — S26A

Everything the DPA adds to the rendering layer, in one module.

WHY A SEPARATE MODULE
---------------------
The alternative was three hand-edits scattered through template_store.py and
template_renderer.py. This keeps the DPA together, matching the reasoning in
template_seed_lib: one file per legal document, because a lawyer reviews one
document and not the others.

WIRING — append these three lines to the END of template_store.py:

    from template_dpa import DPA_FIELDS, DPA_BLOCKS      # noqa: E402
    FIELD_SPECS["dpa"] = DPA_FIELDS
    DOC_BLOCKS["dpa"] = DPA_BLOCKS

And these two to DEFAULT_BLOCK_RENDERERS in template_renderer.py:

    "dpa_annex_ii_table": render_dpa_annex_ii_table,
    "dpa_subprocessor_table": render_dpa_subprocessor_table,

...which are re-exported here, so template_renderer.py can instead do:

    from template_dpa import DPA_BLOCK_RENDERERS
    DEFAULT_BLOCK_RENDERERS.update(DPA_BLOCK_RENDERERS)

Imports from template_store happen INSIDE functions. template_store imports
this module at the bottom of the file, so a module-level import here would be
circular; a call-time import is not, because by then template_store is loaded.

NEVER a runtime dependency of the seed scripts: template_seed_dpa.py reaches
FIELD_SPECS through template_store, which is where the wiring above puts it.
"""

from __future__ import annotations

from typing import Any, Mapping

from template_renderer import Block, FieldSpec


# ===========================================================================
# FIELD SPECIFICATION
# ===========================================================================
# Deliberately NOT built from _COMMON_CLIENT_FIELDS.
#
# That list marks website_url required, and check 6 in template_seed_lib
# rejects a required field no body references. A DPA has no business citing the
# client's website URL, so satisfying the check would mean writing a line into
# a contract to keep a self-check quiet. Same reasoning as _ROPA_FIELDS
# declining to share _JURISDICTION_FIELDS.
#
# It shares no jurisdiction fields either. These Clauses are a Union instrument
# applying identically in every Member State: there is no national variation to
# resolve, and Clause 2(a) would forbid expressing it in the clause text anyway.

DPA_FIELDS = [
    FieldSpec("legal_name", "Legal name of the company", required=True),
    FieldSpec("registered_address", "Registered address", required=True),
    FieldSpec("enterprise_number", "Company registration number"),
    FieldSpec("contact_email", "Contact for matters under these Clauses", required=True),
    FieldSpec("dpo_name", "Data Protection Officer name"),
    FieldSpec("dpo_email", "Data Protection Officer email"),

    # Annex III part 1. required=True because Clause 7.4(a) obliges the
    # processor to implement AT LEAST the measures Annex III specifies. An
    # empty Annex III leaves that obligation with nothing to bite on — the
    # document is wrong, not merely incomplete, which is the FieldSpec test.
    #
    # Consequence worth knowing: a client with processor activities but no
    # recorded security_measures cannot generate a DPA at all. That is the
    # harshest gate in the product and it is deliberate.
    FieldSpec("annex_iii_security", "Security measures (Annex III)", required=True),

    # Annex III parts 2 and 3 — D-44. Not required: build_dpa_values supplies
    # the RECOSA default, so an absent value means the client cleared it
    # deliberately, and a visible placeholder is the right signal for that.
    FieldSpec("annex_iii_assistance", "Assistance to the controller (Annex III)"),
    FieldSpec("annex_iii_breach_elements", "Breach notification elements (Annex III)"),

    # D-43. Clause 7.7(a) Option 2 requires notice of sub-processor changes
    # "at least [SPECIFY TIME PERIOD] in advance". The Commission left it blank
    # deliberately: a commercial term for the parties, not a value the
    # instrument prescribes.
    #
    # required=True because a contract reading "at least [[ TO COMPLETE ]] in
    # advance" is not a contract. format_notice_period() defaults to 30 days,
    # so this blocks only if the default is removed.
    #
    # NOT a readiness() check. A client who sets two days has made a commercial
    # choice that may be contested, not a compliance failure.
    FieldSpec(
        "sub_processor_notice_period",
        "Notice before adding or replacing a sub-processor",
        required=True,
    ),

    # Optional identity fields are flag-guarded rather than placeholder-
    # rendered. In a signed contract a visible placeholder points the
    # counterparty at a gap that may not be one: a sole trader has no
    # enterprise number and most SMEs have no DPO.
    FieldSpec("has_enterprise_number", "Registration number recorded", flag=True),
    FieldSpec("has_dpo", "Has a DPO", flag=True),

    # Guards Schedule 1. Without it a client with no sub-processors signs a
    # schedule reading "the processor engages the sub-processors listed below"
    # above an empty table — which reads as an omission rather than as the true
    # statement that there are none.
    FieldSpec("has_subprocessors", "Engages at least one sub-processor", flag=True),
]

# Only genuinely tabular content is a block. The three Annex III slots are
# merge fields: a joined string of measure labels, and two pieces of prose the
# client may edit. Routing editable prose through a block renderer would put it
# somewhere the client cannot reach.
DPA_BLOCKS = ("dpa_annex_ii_table", "dpa_subprocessor_table")


# ===========================================================================
# NOTICE PERIOD — integer stored, formatted per language
# ===========================================================================
# "30 days" cannot render into the French body, and the French body is the
# official French text, not somewhere an English string may appear. Same
# failure mode as "Dernière mise à jour : 18 August 2026", and the same fix:
# a table, not locale.

DEFAULT_SUBPROCESSOR_NOTICE_DAYS = 30

_NOTICE_PERIOD = {
    "en": lambda n: f"{n} days",
    "fr": lambda n: f"{n} jours",
    "nl": lambda n: f"{n} dagen",
    "de": lambda n: f"{n} Tage",
}


def format_notice_period(days: Any, language: str) -> str:
    """Render the Clause 7.7(a) notice period in the document's language.

    Falls back to the default rather than returning None: the field is
    required, and a client who never opened the setting should still get a
    defensible contract rather than a blocked one.
    """
    n = days if isinstance(days, int) and days > 0 else DEFAULT_SUBPROCESSOR_NOTICE_DAYS
    return _NOTICE_PERIOD.get(language, _NOTICE_PERIOD["en"])(n)


# ===========================================================================
# D-44 — Annex III parts 2 and 3 have no inventory source
# ===========================================================================
# Clause 8(d) requires Annex III to set out the measures by which the processor
# assists the controller AND the scope and extent of that assistance. The
# closing paragraph of Clause 9.2 requires the further elements provided when
# assisting with breach notification. Neither has anything in S24 to draw on:
# security_measures are controls, assistance is a service commitment.
#
# Rejected: leaving them blank (emits a DPA that fails its own clauses), and
# deriving them from security_measures (answers a different question).
#
# Adopted: a RECOSA-authored default the client edits, on the D-43 reasoning —
# a commercial term on the client's contract with their own customer, where
# RECOSA supplies a defensible starting point and does not score the answer.
# Part 3 is the more determinate of the two, since Clause 9.2(a)-(c) already
# fixes the minimum content and the default adds only the routing.

_ASSISTANCE_DEFAULT = {
    "en": (
        "The processor assists the controller by: forwarding any data subject "
        "request received to the controller's stated contact without responding "
        "to it directly; providing, on request, the information held about the "
        "processing that the controller needs for a data protection impact "
        "assessment or a prior consultation; informing the controller without "
        "delay on becoming aware that personal data it processes is inaccurate "
        "or out of date; and making available the information necessary to "
        "demonstrate compliance with these Clauses, including permitting and "
        "contributing to audits under Clause 7.6.\n\n"
        "Assistance is provided within the timeframes the controller specifies "
        "as necessary to meet its own statutory deadlines, and at no additional "
        "charge where the request arises from the processing described in "
        "Annex II."
    ),
    "fr": (
        "Le sous-traitant prête assistance au responsable du traitement en : "
        "transmettant au contact désigné par le responsable du traitement toute "
        "demande reçue d'une personne concernée, sans y répondre directement ; "
        "fournissant, sur demande, les informations dont il dispose sur le "
        "traitement et qui sont nécessaires au responsable du traitement pour "
        "réaliser une analyse d'impact relative à la protection des données ou "
        "une consultation préalable ; informant sans délai le responsable du "
        "traitement lorsqu'il apprend que les données à caractère personnel "
        "qu'il traite sont inexactes ou obsolètes ; et mettant à disposition "
        "les informations nécessaires pour démontrer le respect des présentes "
        "clauses, y compris en permettant les audits prévus à la clause 7.6 et "
        "en y contribuant.\n\n"
        "L'assistance est fournie dans les délais indiqués par le responsable "
        "du traitement comme nécessaires au respect de ses propres délais "
        "légaux, et sans frais supplémentaires lorsque la demande découle du "
        "traitement décrit à l'annexe II."
    ),
}

_BREACH_ELEMENTS_DEFAULT = {
    "en": (
        "In addition to the information required by Clause 9.2(a) to (c), the "
        "processor provides: the date and time the breach was detected and, "
        "where known, when it began; which of the systems listed in Schedule 1 "
        "were involved; whether any sub-processor was affected; the containment "
        "steps already taken; and whether the data was encrypted or otherwise "
        "rendered unintelligible.\n\n"
        "Notification is sent to the controller's stated contact and is not "
        "withheld pending a complete picture — an initial notification carries "
        "what is known at the time, and further information follows as it "
        "becomes available."
    ),
    "fr": (
        "Outre les informations exigées par la clause 9.2, points a) à c), le "
        "sous-traitant communique : la date et l'heure de la détection de la "
        "violation et, si elle est connue, celle de son début ; ceux des "
        "systèmes énumérés à l'annexe technique 1 qui sont concernés ; si un "
        "sous-traitant ultérieur est touché ; les mesures de confinement déjà "
        "prises ; et si les données étaient chiffrées ou rendues "
        "incompréhensibles par un autre moyen.\n\n"
        "La notification est adressée au contact désigné par le responsable du "
        "traitement et n'est pas différée dans l'attente d'un tableau complet : "
        "la notification initiale contient les informations disponibles à ce "
        "moment-là, les informations complémentaires suivant à mesure qu'elles "
        "deviennent disponibles."
    ),
}


def assistance_text(language: str) -> str:
    return _ASSISTANCE_DEFAULT.get(language, _ASSISTANCE_DEFAULT["en"])


def breach_elements_text(language: str) -> str:
    return _BREACH_ELEMENTS_DEFAULT.get(language, _BREACH_ELEMENTS_DEFAULT["en"])


# ===========================================================================
# LOADERS
# ===========================================================================
# THE SCOPING RULE, WHICH IS THE WHOLE POINT
# ------------------------------------------
# Every function here filters to activities with controller_role == 'processor'
# FIRST, and only then walks to systems.
#
# The scope-lock said the sub-processor list comes from S24 `systems` filtered
# to role != 'internal'. That is wrong twice over. `role` is not on systems —
# it is on activity_systems, because a vendor can be processor for one activity
# and joint controller for another. And filtering the whole inventory lists
# every vendor the client uses, including those touching only the client's OWN
# controller-side data.
#
# The second error is the serious one. It would name, in a signed contract with
# a customer, vendors that never touch that customer's data — asserting a
# disclosure that never happened, and inviting an objection under Clause 7.7(a)
# to a sub-processor which is not one. Naming too many is not the safe
# direction here.


def _processor_activity_ids(inv: Mapping[str, Any]) -> set[str]:
    """Activities the client carries out on someone else's behalf."""
    return {
        a["id"] for a in inv["activities"]
        if a.get("controller_role") == "processor"
    }


def build_annex_ii_rows(inv: Mapping[str, Any], language: str) -> list[dict[str, Any]]:
    """Annex II — one entry per processing carried out as processor.

    The OJ's Annex II is a single flat description, which assumes one
    processing. A client processing on a customer's behalf usually has several,
    so this emits one entry each. That is adding information to an annex, which
    Clause 2(a) expressly permits.

    Duration is left as None when retention is unset rather than defaulted:
    Clause 7.3 confines processing to the duration Annex II specifies, so a
    guess would silently shorten or extend the client's own contract.
    """
    from template_store import _clean_retention_basis, _labels  # noqa: PLC0415

    rows: list[dict[str, Any]] = []
    for a in sorted(inv["activities"], key=lambda r: (r.get("name") or "")):
        if a.get("controller_role") != "processor":
            continue

        specials = _labels("special_category", a.get("special_categories"), language)
        criminal = _labels("criminal_data", a.get("criminal_data"), language)

        rows.append({
            "name": a.get("name"),
            # Annex II asks for nature AND purpose as separate headings. The
            # inventory has one free-text purpose field, so nature comes from
            # the activity name and purpose carries the client's text.
            "nature": a.get("name"),
            "purpose": a.get("purpose"),
            "data_subjects": _labels(
                "data_subject_category", a.get("data_subject_categories"), language),
            "data_categories": ", ".join(
                x for x in (
                    _labels("data_category", a.get("data_categories"), language),
                    criminal,
                ) if x
            ) or None,
            # Clause 7.5 obliges specific restrictions where sensitive data is
            # involved, and Annex II asks for them by name. Carrying the
            # categories without the safeguards states half an obligation.
            "special_categories": specials,
            "sensitive_safeguards": (
                _labels("security_measure", a.get("security_measures"), language)
                if specials else None
            ),
            "duration": a.get("retention_period"),
            "duration_basis": _clean_retention_basis(a.get("retention_basis")),
        })
    return rows


def build_security_measures(inv: Mapping[str, Any], language: str) -> str | None:
    """Annex III part 1 — Clause 7.4(a).

    Unioned across the processor activities rather than listed per activity.
    Clause 7.4(a) sets a floor for the engagement as a whole; splitting the
    measures per activity would read as though one listed against activity A
    does not apply to activity B.
    """
    from template_store import _labels  # noqa: PLC0415

    act_ids = _processor_activity_ids(inv)
    codes: set[str] = set()
    for a in inv["activities"]:
        if a["id"] in act_ids:
            for code in a.get("security_measures") or []:
                codes.add(code)
    return _labels("security_measure", sorted(codes), language)


def build_subprocessor_rows(inv: Mapping[str, Any], language: str) -> list[dict[str, Any]]:
    """Schedule 1 — the agreed list for Clause 7.7(a) Option 2.

    Scoped to systems supporting processor-role activities, with internal
    systems excluded: a client's own server is not a sub-processor, the same
    reason _NON_RECIPIENT_ROLES exists for the controller register.

    Location and transfer mechanism are included because Clause 7.8(a) confines
    third-country transfers to documented instructions, and a controller cannot
    give an informed instruction about a sub-processor whose location the
    schedule does not state.
    """
    from inventory import is_third_country, label_for  # noqa: PLC0415
    from template_store import _NON_RECIPIENT_ROLES  # noqa: PLC0415

    act_ids = _processor_activity_ids(inv)
    systems_by_id = {s["id"]: s for s in inv["systems"]}

    roles_by_system: dict[str, list[str]] = {}
    for link in inv["links"]:
        if link["activity_id"] not in act_ids:
            continue
        role = link.get("role")
        if (role or "") in _NON_RECIPIENT_ROLES:
            continue
        bucket = roles_by_system.setdefault(link["system_id"], [])
        if role and role not in bucket:
            bucket.append(role)

    rows: list[dict[str, Any]] = []
    for system_id, roles in roles_by_system.items():
        s = systems_by_id.get(system_id)
        if not s:
            continue
        country = (s.get("processing_country") or "").upper() or None
        rows.append({
            "name": s.get("vendor_legal_name") or s.get("name"),
            "category_label": (
                label_for("system_category", s["category"], language)
                if s.get("category") else None
            ),
            "role_label": "; ".join(
                label_for("system_role", r, language) for r in roles
            ) or None,
            "country": country,
            "transfer_mechanism": (
                label_for("transfer_mechanism",
                          s.get("transfer_mechanism") or "unknown", language)
                if country and is_third_country(country) else None
            ),
        })
    return sorted(rows, key=lambda r: (r["name"] or "").lower())


# ===========================================================================
# BLOCK RENDERERS
# ===========================================================================

_ANNEX_II_HEADERS = {
    "en": ("Processing", "Categories of data subjects", "Categories of personal data",
           "Sensitive data and safeguards", "Purpose", "Duration"),
    "fr": ("Traitement", "Catégories de personnes concernées",
           "Catégories de données à caractère personnel",
           "Données sensibles et garanties", "Finalité", "Durée"),
    "nl": ("Verwerking", "Categorieën betrokkenen", "Categorieën persoonsgegevens",
           "Bijzondere gegevens en waarborgen", "Doel", "Duur"),
    "de": ("Verarbeitung", "Kategorien betroffener Personen",
           "Kategorien personenbezogener Daten",
           "Sensible Daten und Garantien", "Zweck", "Dauer"),
}

_SUBPROC_HEADERS = {
    "en": ("Sub-processor", "Service", "Role", "Location of processing",
           "Transfer mechanism"),
    "fr": ("Sous-traitant ultérieur", "Service", "Rôle", "Lieu du traitement",
           "Mécanisme de transfert"),
    "nl": ("Subverwerker", "Dienst", "Rol", "Plaats van verwerking",
           "Doorgiftemechanisme"),
    "de": ("Unterauftragsverarbeiter", "Dienst", "Rolle", "Ort der Verarbeitung",
           "Übermittlungsmechanismus"),
}

# Annex II empty is a should-not-happen: the gate in pages/documents.py hides
# the DPA when the client has no processor-role activity. Worded as a safety
# net rather than a statement, because a signed contract whose Annex II says
# "none" describes no processing at all, and Clause 1(c) makes these Clauses
# apply to the processing Annex II specifies.
_ANNEX_II_EMPTY = {
    "en": "_No processing carried out on behalf of a controller is recorded. "
          "This Annex must be completed before these Clauses are signed._",
    "fr": "_Aucun traitement effectué pour le compte d'un responsable du "
          "traitement n'est enregistré. La présente annexe doit être complétée "
          "avant la signature des présentes clauses._",
    "nl": "_Er is geen verwerking namens een verwerkingsverantwoordelijke "
          "geregistreerd. Deze bijlage moet vóór ondertekening worden ingevuld._",
    "de": "_Es ist keine Verarbeitung im Auftrag eines Verantwortlichen erfasst. "
          "Dieser Anhang ist vor Unterzeichnung auszufüllen._",
}

# Schedule 1 empty is a legitimate state. The template's
# {{#ifnot:has_subprocessors}} branch carries the substantive sentence, so this
# fires only if the flag and the rows ever disagree.
_SUBPROC_EMPTY = {
    "en": "_No sub-processors are engaged for the processing described in Annex II._",
    "fr": "_Aucun sous-traitant ultérieur n'intervient dans le traitement décrit "
          "à l'annexe II._",
    "nl": "_Er worden geen subverwerkers ingeschakeld voor de in bijlage II "
          "beschreven verwerking._",
    "de": "_Für die in Anhang II beschriebene Verarbeitung werden keine "
          "Unterauftragsverarbeiter eingesetzt._",
}


def _pick(mapping: Mapping[str, Any], language: str) -> Any:
    return mapping.get(language, mapping["en"])


def render_dpa_annex_ii_table(context: Mapping[str, Any], language: str) -> Block:
    """Annex II. Sensitive data and its safeguards share one cell deliberately,
    the same reasoning as Art. 9(1) and 9(2) in the controller register."""
    from template_renderer import _join  # noqa: PLC0415

    block = Block(
        name="dpa_annex_ii_table",
        headers=list(_pick(_ANNEX_II_HEADERS, language)),
        empty_text=_pick(_ANNEX_II_EMPTY, language),
    )
    for r in context.get("dpa_annex_ii_rows") or []:
        block.rows.append([
            r.get("nature") or r.get("name"),
            r.get("data_subjects"),
            r.get("data_categories"),
            _join(r.get("special_categories"), r.get("sensitive_safeguards")),
            r.get("purpose"),
            _join(r.get("duration"), r.get("duration_basis")),
        ])
    return block


def render_dpa_subprocessor_table(context: Mapping[str, Any], language: str) -> Block:
    """Schedule 1. Location and transfer mechanism are columns because Clause
    7.8(a) confines third-country transfers to documented instructions."""
    block = Block(
        name="dpa_subprocessor_table",
        headers=list(_pick(_SUBPROC_HEADERS, language)),
        empty_text=_pick(_SUBPROC_EMPTY, language),
    )
    for r in context.get("dpa_subprocessor_rows") or []:
        block.rows.append([
            r.get("name"),
            r.get("category_label"),
            r.get("role_label"),
            r.get("country"),
            r.get("transfer_mechanism"),
        ])
    return block


DPA_BLOCK_RENDERERS = {
    "dpa_annex_ii_table": render_dpa_annex_ii_table,
    "dpa_subprocessor_table": render_dpa_subprocessor_table,
}


# ===========================================================================
# WIRING HELPERS
# ===========================================================================
# Called from build_block_context() and build_values() in template_store.py:
#
#     if doc_type == "dpa":
#         from template_dpa import build_dpa_block_context
#         return build_dpa_block_context(client_id, language)
#
#     if doc_type == "dpa":
#         from template_dpa import apply_dpa_values
#         apply_dpa_values(values, client, block_context, language)


def build_dpa_block_context(client_id: str, language: str) -> tuple[dict[str, Any], str | None]:
    """Reuses _load_inventory: it already fetches activities, systems and links,
    and a DPA needs no table the registers do not."""
    from template_store import _load_inventory  # noqa: PLC0415

    inv = _load_inventory(client_id)
    stamps = [
        r.get("updated_at")
        for key in ("activities", "systems")
        for r in inv[key] if r.get("updated_at")
    ]
    return {
        "dpa_annex_ii_rows": build_annex_ii_rows(inv, language),
        "dpa_subprocessor_rows": build_subprocessor_rows(inv, language),
        "dpa_security_measures": build_security_measures(inv, language),
    }, (max(stamps)[:10] if stamps else None)


def apply_dpa_values(
    values: dict[str, Any],
    client: Mapping[str, Any],
    block_context: Mapping[str, Any] | None,
    language: str,
) -> None:
    """Fill the DPA-specific merge fields. has_dpo is already set for every
    doc_type by build_values, so the DPA gets it free."""
    ctx = block_context or {}
    values["has_enterprise_number"] = bool((client.get("enterprise_number") or "").strip())
    values["has_subprocessors"] = bool(ctx.get("dpa_subprocessor_rows"))
    values["sub_processor_notice_period"] = format_notice_period(
        client.get("sub_processor_notice_days"), language)
    values["annex_iii_security"] = ctx.get("dpa_security_measures")
    # The client's stored text wins where present; the default fills the blank.
    # An empty stored string is treated as absent by the renderer, so a client
    # who clears the field sees a placeholder rather than silently getting
    # RECOSA's wording back.
    values["annex_iii_assistance"] = (
        client.get("dpa_assistance_text") or assistance_text(language))
    values["annex_iii_breach_elements"] = (
        client.get("dpa_breach_elements_text") or breach_elements_text(language))
