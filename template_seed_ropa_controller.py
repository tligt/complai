"""
template_seed_ropa_controller.py — S26

Authors the Art. 30(1) record of processing activities — the register kept by
a company for processing it decides the purposes and means of.

Run:  python3 template_seed_ropa_controller.py > seed_s26_ropa_controller.sql

NEVER IMPORTED AT RUNTIME. The machinery lives in template_seed_lib.py; this
file is text and nothing else.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
WHY THIS IS A SEPARATE DOCUMENT FROM THE PROCESSOR REGISTER
---------------------------------------------------------------------------
The CNIL recommends that an organisation acting as both controller and
processor keep two separate registers rather than one blended record, and
Art. 30(1) and Art. 30(2) prescribe different content — eight items against
five. A single table with a "your role" column would satisfy neither cleanly
and is the shape supervisory authorities specifically advise against.

---------------------------------------------------------------------------
WHY THE PROSE IS SHORT
---------------------------------------------------------------------------
A RoPA is a table, not an essay. Everything outside the block is there to make
the table intelligible to a reader who did not build it: who the record belongs
to, when it was produced, and what it does and does not cover.

The one thing the prose must do is be honest about currency. A register is a
living record (D-28); an export is a snapshot of it. Saying so on the face of
the document is the difference between evidence and a claim.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. Art. 30(1)(d) asks for CATEGORIES of recipients. The table names the vendor
   AND its category. That exceeds the requirement; confirm it creates no
   difficulty.
2. The scope paragraph states that the record covers processing recorded in
   RECOSA. That is a limitation of fact, not of law, and is written plainly
   rather than buried.
3. Art. 30(5)'s under-250 exemption is not mentioned anywhere. In practice the
   "not occasional" limb catches any employer with HR data, so surfacing the
   exemption would mislead far more clients than it would help.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


# ===========================================================================
# ENGLISH
# ===========================================================================

BODY_EN = """\
# {{record_type}}

## 1. Controller

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

This record is maintained under Article 30(1) of Regulation (EU) 2016/679 and
covers the processing activities for which the organisation named above
determines the purposes and means.

Processing carried out on behalf of another controller is recorded separately,
under Article 30(2).

**Produced as at {{record_as_at}}.**{{#if:has_last_updated}} The underlying record was last changed on {{record_last_updated}}.{{/if:has_last_updated}}

This document is a snapshot. The record itself is maintained continuously and
is made available to the supervisory authority on request in its current form.

## 3. Processing activities

{{#ifnot:has_rows}}
No processing activities have been recorded. An empty record does not mean no
processing takes place; it means none has yet been documented.
{{/ifnot:has_rows}}

{{#block:ropa_controller_table}}

## 4. Scope and limitations

This record reflects the systems, processing activities and vendors recorded in
RECOSA as at the date above. Processing that has not been recorded does not
appear here.

Where a field is shown as incomplete, the underlying information has not yet
been confirmed. It is shown as missing rather than inferred.
"""


# ===========================================================================
# FRENCH
# ===========================================================================

BODY_FR = """\
# {{record_type}}

## 1. Responsable du traitement

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

Ce registre est tenu en application de l'article 30(1) du règlement (UE)
2016/679 et couvre les activités de traitement pour lesquelles l'organisation
désignée ci-dessus détermine les finalités et les moyens.

Les traitements effectués pour le compte d'un autre responsable du traitement
font l'objet d'un registre distinct, au titre de l'article 30(2).

**Établi au {{record_as_at}}.**{{#if:has_last_updated}} Le registre sous-jacent a été modifié pour la dernière fois le {{record_last_updated}}.{{/if:has_last_updated}}

Ce document est un instantané. Le registre lui-même est tenu à jour en continu
et est communiqué à l'autorité de contrôle, sur demande, dans sa version
courante.

## 3. Activités de traitement

{{#ifnot:has_rows}}
Aucune activité de traitement n'a été enregistrée. Un registre vide ne signifie
pas qu'aucun traitement n'a lieu ; il signifie qu'aucun n'a encore été
documenté.
{{/ifnot:has_rows}}

{{#block:ropa_controller_table}}

## 4. Portée et limites

Ce registre reflète les systèmes, activités de traitement et fournisseurs
enregistrés dans RECOSA à la date indiquée ci-dessus. Un traitement qui n'a pas
été enregistré n'y figure pas.

Lorsqu'une rubrique est signalée comme incomplète, l'information correspondante
n'a pas encore été confirmée. Elle est présentée comme manquante plutôt que
déduite.
"""


DOC = TemplateDoc(
    doc_type="ropa_controller",
    title="Record of Processing Activities — Controller (Art. 30(1))",
    tier=1,
    sort_order=20,
    sprint="S26",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"ropa_controller_table"},
)


if __name__ == "__main__":
    run(DOC, "seed_s26_ropa_controller.sql")
