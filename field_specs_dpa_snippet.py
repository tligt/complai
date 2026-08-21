# ---------------------------------------------------------------------------
# ADD TO template_store.py — S26A
# ---------------------------------------------------------------------------

# S26A. Deliberately NOT built from _COMMON_CLIENT_FIELDS.
#
# That list marks website_url and contact_email required, and check 6 in
# template_seed_lib rejects a required field no body references. A DPA has no
# business citing the client's website URL, so satisfying the check would mean
# writing a line into a contract to keep a self-check quiet. Same reasoning as
# _ROPA_FIELDS declining to share _JURISDICTION_FIELDS.
#
# It also shares NO jurisdiction fields. These Clauses are a Union instrument
# applying identically in every Member State; there is no national variation to
# resolve, and Clause 2(a) would forbid expressing it in the clause text anyway.
_DPA_FIELDS = [
    FieldSpec("legal_name", "Legal name of the company", required=True),
    FieldSpec("registered_address", "Registered address", required=True),
    FieldSpec("enterprise_number", "Company registration number"),
    FieldSpec("contact_email", "Contact for matters under these Clauses", required=True),
    FieldSpec("dpo_name", "Data Protection Officer name"),
    FieldSpec("dpo_email", "Data Protection Officer email"),

    # D-43. Clause 7.7(a) Option 2 requires the processor to give the controller
    # notice of sub-processor changes "at least [SPECIFY TIME PERIOD] in
    # advance". The Commission left it blank deliberately: it is a commercial
    # term for the parties, not a value the instrument prescribes.
    #
    # required=True because a contract that says "at least [[ TO COMPLETE ]]
    # in advance" is not a contract. The renderer's default supplies 30 days,
    # so this blocks only if the default is removed.
    #
    # NOT a readiness() check. A client who sets two days has made a commercial
    # choice that may be contested, not a compliance failure.
    FieldSpec(
        "sub_processor_notice_period",
        "Notice before adding or replacing a sub-processor",
        required=True,
    ),

    # Annex III part 1. required=True because Clause 7.4(a) obliges the
    # processor to implement AT LEAST the measures Annex III specifies. An
    # empty Annex III leaves that obligation with nothing to bite on — the
    # document is wrong, not merely incomplete, which is the FieldSpec test.
    FieldSpec("annex_iii_security", "Security measures (Annex III)", required=True),

    # Annex III parts 2 and 3, D-44. Not required: build_values supplies the
    # RECOSA default, so an absent value means the client cleared it
    # deliberately, and a placeholder is the right signal for that.
    FieldSpec("annex_iii_assistance", "Assistance to the controller (Annex III)"),
    FieldSpec("annex_iii_breach_elements", "Breach notification elements (Annex III)"),

    FieldSpec("has_enterprise_number", "Registration number recorded", flag=True),
    FieldSpec("has_dpo", "Has a DPO", flag=True),

    # Guards Schedule 1. Without it, a client with no sub-processors signs a
    # schedule reading "the processor engages the sub-processors listed below"
    # above an empty table — which reads as an omission rather than as the
    # true statement that there are none.
    FieldSpec("has_subprocessors", "Engages at least one sub-processor", flag=True),
]

# Then, in FIELD_SPECS:
#     "dpa": _DPA_FIELDS,
#
# And in DOC_BLOCKS:
#     "dpa": ("dpa_annex_ii_table", "dpa_subprocessor_table"),


# ---------------------------------------------------------------------------
# The notice period is stored as an integer and formatted per language.
# ---------------------------------------------------------------------------
# "30 days" cannot render into the French body, and the French body is the
# official French text — not somewhere an English string may appear. Same
# failure mode as "Dernière mise à jour : 18 August 2026", and the same fix:
# a table, not locale.
#
# Store sub_processor_notice_days as an integer on the client (or on the DPA
# settings row, wherever S26A puts it) and format at merge time.

DEFAULT_SUBPROCESSOR_NOTICE_DAYS = 30

_NOTICE_PERIOD = {
    "en": lambda n: f"{n} days",
    "fr": lambda n: f"{n} jours",
    "nl": lambda n: f"{n} dagen",
    "de": lambda n: f"{n} Tage",
}


def format_notice_period(days: int | None, language: str) -> str:
    """Render the Clause 7.7(a) notice period in the document's language.

    Falls back to the default rather than returning None: this field is
    required, and a client who never opened the setting should still get a
    defensible contract rather than a blocked one.
    """
    n = days if isinstance(days, int) and days > 0 else DEFAULT_SUBPROCESSOR_NOTICE_DAYS
    return _NOTICE_PERIOD.get(language, _NOTICE_PERIOD["en"])(n)
