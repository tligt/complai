# ---------------------------------------------------------------------------
# ADD TO template_renderer.py — S26A
# ---------------------------------------------------------------------------
# TWO BLOCKS, NOT FIVE.
#
# The earlier S26A draft made all five annex slots blocks. Three of them are
# not tabular and have no variable row count:
#
#   annex_iii_security          a single joined string of measure labels
#   annex_iii_assistance        prose the client may edit (D-44)
#   annex_iii_breach_elements   prose the client may edit (D-44)
#
# A block exists because a table with a variable row count cannot be a merge
# field without loops in the template (D-01a). None of those three has that
# problem, and routing prose through a block renderer would put client-editable
# text somewhere the client cannot edit it. They are merge fields with defaults
# supplied in build_values().
#
# What remains genuinely tabular: Annex II (one entry per processing) and
# Schedule 1 (one row per sub-processor).

_DPA_ANNEX_II_HEADERS = {
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

_DPA_SUBPROC_HEADERS = {
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
# the DPA entirely when the client has no processor-role activity. It is worded
# as a safety net rather than a statement, because a signed contract whose
# Annex II says "none" describes no processing at all, and Clause 1(c) makes
# these Clauses apply to the processing Annex II specifies.
_DPA_ANNEX_II_EMPTY = {
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

# Schedule 1 empty is a legitimate state and says so positively. The template's
# {{#ifnot:has_subprocessors}} branch carries the substantive sentence, so this
# only fires if the flag and the rows ever disagree.
_DPA_SUBPROC_EMPTY = {
    "en": "_No sub-processors are engaged for the processing described in Annex II._",
    "fr": "_Aucun sous-traitant ultérieur n'intervient dans le traitement décrit "
          "à l'annexe II._",
    "nl": "_Er worden geen subverwerkers ingeschakeld voor de in bijlage II "
          "beschreven verwerking._",
    "de": "_Für die in Anhang II beschriebene Verarbeitung werden keine "
          "Unterauftragsverarbeiter eingesetzt._",
}


def render_dpa_annex_ii_table(context: Mapping[str, Any], language: str):
    """Annex II — one entry per processing carried out as processor.

    The OJ's Annex II is a single flat description, which assumes one
    processing. A client processing on a customer's behalf usually has several.
    Emitting one row each is adding information to an annex, which Clause 2(a)
    expressly permits.

    Sensitive data and its safeguards share one cell deliberately, the same
    reasoning as Art. 9(1) and 9(2) in the controller register: Clause 7.5
    obliges specific restrictions where sensitive data is involved, so naming
    the trigger without the safeguard states half an obligation.
    """
    rows_in = context.get("dpa_annex_ii_rows") or []
    block = Block(
        name="dpa_annex_ii_table",
        headers=list(_pick(_DPA_ANNEX_II_HEADERS, language)),
        empty_text=_pick(_DPA_ANNEX_II_EMPTY, language),
    )
    for r in rows_in:
        block.rows.append([
            r.get("nature") or r.get("name"),
            r.get("data_subjects"),
            r.get("data_categories"),
            _join(r.get("special_categories"), r.get("sensitive_safeguards")),
            r.get("purpose"),
            # Clause 7.3 confines processing to the duration Annex II states,
            # so an unset retention period renders as an em dash rather than
            # a guess — _cell() handles that. Inventing a duration would
            # shorten or extend the client's own contract.
            _join(r.get("duration"), r.get("duration_basis")),
        ])
    return block


def render_dpa_subprocessor_table(context: Mapping[str, Any], language: str):
    """Schedule 1 — the agreed list for Clause 7.7(a) Option 2.

    Location and transfer mechanism are columns because Clause 7.8(a) confines
    third-country transfers to documented instructions from the controller, and
    a controller cannot instruct on a sub-processor whose location the schedule
    does not state.
    """
    rows_in = context.get("dpa_subprocessor_rows") or []
    block = Block(
        name="dpa_subprocessor_table",
        headers=list(_pick(_DPA_SUBPROC_HEADERS, language)),
        empty_text=_pick(_DPA_SUBPROC_EMPTY, language),
    )
    for r in rows_in:
        block.rows.append([
            r.get("name"),
            r.get("category_label"),
            r.get("role_label"),
            r.get("country"),
            r.get("transfer_mechanism"),
        ])
    return block


# Add to DEFAULT_BLOCK_RENDERERS:
#     "dpa_annex_ii_table": render_dpa_annex_ii_table,
#     "dpa_subprocessor_table": render_dpa_subprocessor_table,
