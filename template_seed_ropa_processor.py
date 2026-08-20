"""
template_seed_ropa_processor.py — S26

Authors the Art. 30(2) record — the register a processor keeps of processing
carried out on behalf of its customers.

Run:  python3 template_seed_ropa_processor.py > seed_s26_ropa_processor.sql

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
THE PIVOT IS THE POINT
---------------------------------------------------------------------------
Art. 30(1) is one row per activity. Art. 30(2) is one row per CONTROLLER,
listing the categories of processing carried out for them. Same underlying
data, different shape, and the shape is prescribed.

Art. 30(2)(a) requires the name and contact details of EACH controller. Art.
30(2)(b) permits the PROCESSING to be described in categories. The asymmetry is
in the text and it is deliberate: a processor may summarise what it does, not
who it does it for.

Where a client's customer roster changes constantly, the register reference
mechanism records where the maintained list is kept. That is a statement about
the record rather than a row in it, which is why it renders as a caption under
the table and not as a column. It is not a substitute for being able to produce
the list — section 4 says so in terms.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. The register-reference mechanism. Naming a maintained list rather than
   enumerating controllers is common practice among processors with large
   rosters, but Art. 30(2)(a) says "each". Confirm the wording in section 4 is
   the right characterisation of what the client is asserting.
2. Art. 30(2)(c) transfers and 30(2)(d) security measures are aggregated across
   the activities carried out for each controller. Where two activities for the
   same controller have different security measures, the union is shown.
   Confirm that aggregation is acceptable rather than requiring per-activity
   granularity.
3. Art. 30(2) also contemplates naming the controller's representative and DPO
   where they exist. RECOSA does not currently collect those. The omission is
   deliberate and flagged rather than silently absent.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


# ===========================================================================
# ENGLISH
# ===========================================================================

BODY_EN = """\
# {{record_type}}

## 1. Processor

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{registered_address}}

{{#if:has_enterprise_number}}Company registration number: {{enterprise_number}}{{/if:has_enterprise_number}}

Contact for data protection matters: {{contact_email}}

Website: {{website_url}}

{{#if:has_dpo_section}}
### Data Protection Officer

{{dpo_name}} — {{dpo_email}}
{{/if:has_dpo_section}}

## 2. About this record

This record is maintained under Article 30(2) of Regulation (EU) 2016/679 and
covers processing carried out on behalf of other controllers, on their
instructions.

Processing for which the organisation named above determines the purposes and
means is recorded separately, under Article 30(1).

**Produced as at {{record_as_at}}.**{{#if:has_last_updated}} The underlying record was last changed on {{record_last_updated}}.{{/if:has_last_updated}}

This document is a snapshot. The record itself is maintained continuously and
is made available to the supervisory authority on request in its current form.

## 3. Processing carried out for each controller

{{#ifnot:has_rows}}
No processing is recorded as carried out on behalf of another controller.
{{/ifnot:has_rows}}

{{#block:ropa_processor_table}}

## 4. Scope and limitations

This record reflects the controllers, processing activities and systems
recorded in RECOSA as at the date above.

{{#if:has_register_reference}}
Where controllers are identified by reference to a maintained list rather than
named individually above, that list is kept current and can be produced in full
on request. The reference identifies where the list is held; it does not
replace the obligation to be able to produce it.
{{/if:has_register_reference}}

Where a field is shown as incomplete, the underlying information has not yet
been confirmed. It is shown as missing rather than inferred.
"""


# ===========================================================================
# FRENCH
# ===========================================================================

BODY_FR = """\
# {{record_type}}

## 1. Sous-traitant

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{registered_address}}

{{#if:has_enterprise_number}}Numéro d'entreprise : {{enterprise_number}}{{/if:has_enterprise_number}}

Contact pour les questions de protection des données : {{contact_email}}

Site web : {{website_url}}

{{#if:has_dpo_section}}
### Délégué à la protection des données

{{dpo_name}} — {{dpo_email}}
{{/if:has_dpo_section}}

## 2. À propos de ce registre

Ce registre est tenu en application de l'article 30(2) du règlement (UE)
2016/679 et couvre les traitements effectués pour le compte d'autres
responsables du traitement, sur leurs instructions.

Les traitements pour lesquels l'organisation désignée ci-dessus détermine les
finalités et les moyens font l'objet d'un registre distinct, au titre de
l'article 30(1).

**Établi au {{record_as_at}}.**{{#if:has_last_updated}} Le registre sous-jacent a été modifié pour la dernière fois le {{record_last_updated}}.{{/if:has_last_updated}}

Ce document est un instantané. Le registre lui-même est tenu à jour en continu
et est communiqué à l'autorité de contrôle, sur demande, dans sa version
courante.

## 3. Traitements effectués pour chaque responsable du traitement

{{#ifnot:has_rows}}
Aucun traitement effectué pour le compte d'un autre responsable du traitement
n'est enregistré.
{{/ifnot:has_rows}}

{{#block:ropa_processor_table}}

## 4. Portée et limites

Ce registre reflète les responsables du traitement, les activités de traitement
et les systèmes enregistrés dans RECOSA à la date indiquée ci-dessus.

{{#if:has_register_reference}}
Lorsque les responsables du traitement sont identifiés par renvoi à une liste
tenue à jour plutôt que nommés individuellement ci-dessus, cette liste est
maintenue à jour et peut être communiquée intégralement sur demande. Le renvoi
indique où la liste est conservée ; il ne dispense pas de l'obligation de
pouvoir la produire.
{{/if:has_register_reference}}

Lorsqu'une rubrique est signalée comme incomplète, l'information correspondante
n'a pas encore été confirmée. Elle est présentée comme manquante plutôt que
déduite.
"""


DOC = TemplateDoc(
    doc_type="ropa_processor",
    title="Record of Processing Activities — Processor (Art. 30(2))",
    tier=1,
    sort_order=21,
    sprint="S26",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"ropa_processor_table"},
    source_revision=2,
    version_no=2,
    change_note="S26: register-reference paragraph now conditional.",
)


if __name__ == "__main__":
    run(DOC, "seed_s26_ropa_processor.sql")
