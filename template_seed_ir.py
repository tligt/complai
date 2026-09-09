"""
template_seed_ir.py — S29A

Authors the incident response plan: how this organisation detects, contains and
recovers from a cybersecurity incident.

Run:  python3 template_seed_ir.py > seed_s29a_ir.sql

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
WHY THIS IS SEPARATE FROM THE BREACH PROCEDURE
---------------------------------------------------------------------------
They are read at different moments by different people.

The breach procedure answers "who do I have to tell, and by when" — it is
consulted in the first hours, under pressure, by whoever is dealing with it.

This answers "how do we handle incidents" — it is the standing arrangement, and
it is what an auditor asks to see. Art. 21(2)(b) requires incident handling as
a measure; Art. 23 requires reporting. Different subparagraphs, different
questions.

Merging them would repeat the mistake this sprint exists to fix: one document
answering five obligations, where a client with one scores as having all.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. Three sections are client-authored prose drafted by RECOSA and edited by
   the client (D-43/D-44 pattern): detection, containment, and roles. They are
   not scored and RECOSA does not vouch for them.
2. The plan does not define "incident". Art. 6(6) does, and restating a
   definition in a client's own document invites divergence when it changes.
3. Section 5 says an untested plan is a document rather than a capability.
   Deliberate, and it may read as an admission. Confirm it is the right tone
   for something an authority may read.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


BODY_EN = """\
# Incident response plan

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**In force from {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}NIS2 classification: {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. What this covers

How we notice that something has gone wrong with our systems or our data, what
we do about it, and who is responsible for what.

Reporting an incident to an authority is dealt with separately, in our incident
and breach notification procedure. This document is about handling the incident
itself.

## 2. How we notice

{{nis2_detection_text}}

Anyone in the organisation can report a suspected incident to
{{contact_email}}. They are not expected to judge whether it is serious first.

## 3. What we do

{{nis2_containment_text}}

We do not power systems off unless there is no alternative — it destroys
evidence that may be needed to understand what happened and to notify
accurately.

## 4. Who does what

{{nis2_roles_text}}

{{#if:has_dpo_section}}
Where personal data is involved, {{dpo_name}} ({{dpo_email}}) is involved from
the start rather than told afterwards.
{{/if:has_dpo_section}}

## 5. Systems in scope

{{#ifnot:has_critical_systems}}
No systems have been recorded. This plan cannot say what it protects until they
are.
{{/ifnot:has_critical_systems}}

{{#block:nis2_systems}}

Our recovery objectives for these systems — how quickly each must be back and
how much work may be lost — are set out in our business continuity plan.

## 6. Learning from it

After an incident is closed we record what happened, what we did, and what we
changed as a result.

We test this plan rather than assuming it works. **A plan that has never been
tested is a document, not a capability**, and the first time you find out
whether a backup restores should not be the day you need it.
"""

BODY_FR = """\
# Plan de réponse aux incidents

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**En vigueur depuis le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}Classification NIS2 : {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. Objet

La manière dont nous détectons qu'un problème affecte nos systèmes ou nos
données, ce que nous faisons alors, et qui est responsable de quoi.

La notification d'un incident à une autorité fait l'objet d'un document
distinct, notre procédure de notification des incidents et violations. Le
présent document porte sur le traitement de l'incident lui-même.

## 2. Comment nous détectons

{{nis2_detection_text}}

Toute personne de l'organisation peut signaler un incident présumé à
{{contact_email}}. Il ne lui appartient pas d'en apprécier au préalable la
gravité.

## 3. Ce que nous faisons

{{nis2_containment_text}}

Nous n'éteignons pas les systèmes sauf en l'absence d'alternative : cela
détruit des éléments nécessaires pour comprendre ce qui s'est passé et pour
notifier avec exactitude.

## 4. Qui fait quoi

{{nis2_roles_text}}

{{#if:has_dpo_section}}
Lorsque des données à caractère personnel sont concernées, {{dpo_name}}
({{dpo_email}}) est associé dès le départ, et non informé après coup.
{{/if:has_dpo_section}}

## 5. Systèmes concernés

{{#ifnot:has_critical_systems}}
Aucun système n'a été enregistré. Ce plan ne peut pas indiquer ce qu'il protège
tant que ce n'est pas fait.
{{/ifnot:has_critical_systems}}

{{#block:nis2_systems}}

Nos objectifs de rétablissement pour ces systèmes — délai de remise en service
et perte de travail admissible — figurent dans notre plan de continuité
d'activité.

## 6. Retour d'expérience

Après la clôture d'un incident, nous consignons ce qui s'est passé, ce que nous
avons fait et ce que nous avons modifié en conséquence.

Nous testons ce plan plutôt que de présumer qu'il fonctionne. **Un plan jamais
testé est un document, pas une capacité** : le jour où vous avez besoin d'une
sauvegarde n'est pas le bon moment pour découvrir si elle se restaure.
"""


DOC = TemplateDoc(
    doc_type="incident_response_plan",
    title="Incident response plan (NIS2 Art. 21(2)(b))",
    tier=2,
    sort_order=51,
    sprint="S29A",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"nis2_systems"},
    materiality="required",
    source_revision=1,
    version_no=1,
    change_note=(
        "Initial version (S29A). Tier 2 — three client-authored sections "
        "drafted by RECOSA under the D-43/D-44 pattern, edited by the client, "
        "not scored. DRAFT — not yet reviewed by counsel."
    ),
)


if __name__ == "__main__":
    run(DOC, "seed_s29a_ir.sql")
