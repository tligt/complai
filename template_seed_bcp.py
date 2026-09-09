"""
template_seed_bcp.py — S29A

Authors the business continuity plan: how the organisation keeps operating when
a system it depends on is unavailable, and how fast each one must come back.

Run:  python3 template_seed_bcp.py > seed_s29a_bcp.sql

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
THE TABLE IS THE DOCUMENT
---------------------------------------------------------------------------
Everything else here is framing. A continuity plan without recovery objectives
says service will be restored without saying how fast, which is the one thing
it exists to state and the only part that can be tested.

That is why S29A part 1 added rto_minutes and rpo_minutes rather than accepting
a placeholder: the alternative was a document that reads like a plan and
commits to nothing.

Systems with no objectives are LISTED, showing "not set". Dropping them would
make the plan look complete while saying nothing about the systems nobody has
thought about — which are the ones most likely to fail badly.

Ordered by recovery time, tightest first. A continuity plan is read under
pressure and its order IS its priority.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. Section 4 states plainly where objectives have not been set. An
   organisation may prefer that not to appear in a document an authority
   might read; the alternative is a plan that implies coverage it does not
   have.
2. Two sections are client-authored prose drafted by RECOSA and edited by the
   client (D-43/D-44): continuity arrangements and testing. Not scored.
3. Art. 21(2)(c) requires business continuity "such as backup management and
   disaster recovery, and crisis management". Backup and recovery are covered
   here; crisis management is deliberately thin, because for an SME it is the
   incident response plan under another name.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


BODY_EN = """\
# Business continuity plan

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**In force from {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}NIS2 classification: {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. What this covers

How we keep operating when a system we depend on is unavailable, how quickly
each one has to come back, and how much work we can afford to lose.

Handling the incident that caused the outage is dealt with in our incident
response plan. This document is about continuing to operate while it is
happening.

## 2. How we keep going

{{nis2_continuity_text}}

## 3. Recovery objectives

Two numbers per system. **How long it may be down** before it has to be back,
and **how much work may be lost** — if the last backup was an hour old, an hour
of entries is gone.

A system can have a fast recovery time and a poor recovery point: back within
minutes, running on yesterday's data.

{{#block:nis2_recovery}}

{{#if:has_unset_objectives}}
### Systems without objectives

Some systems above show no recovery objective. That does not mean they do not
matter — it means nobody has yet decided how long we could manage without
them. Until that decision is made, this plan does not commit to anything for
those systems.
{{/if:has_unset_objectives}}

{{#ifnot:has_recovery_objectives}}
**No recovery objectives have been set for any system.** This plan describes
intentions rather than commitments until they are.
{{/ifnot:has_recovery_objectives}}

## 4. Backups

Where and how each system is recovered is recorded against it in the table
above. Where that column is empty, recovery depends on the provider's own
arrangements and we have not confirmed what they are.

## 5. Testing

{{nis2_testing_text}}

**An untested plan is a document, not a capability.** The day you need a backup
is the wrong time to find out whether it restores.

## 6. Who decides

Invoking this plan — declaring that we are operating in continuity mode, and
later that we have returned to normal — is a decision, and someone has to make
it. That responsibility sits with the same people who lead an incident, as set
out in our incident response plan.
"""

BODY_FR = """\
# Plan de continuité d'activité

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**En vigueur depuis le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}Classification NIS2 : {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. Objet

Comment nous continuons à fonctionner lorsqu'un système dont nous dépendons est
indisponible, dans quel délai chacun doit être rétabli, et quelle perte de
travail nous pouvons supporter.

Le traitement de l'incident à l'origine de l'interruption relève de notre plan
de réponse aux incidents. Le présent document porte sur la poursuite de
l'activité pendant l'incident.

## 2. Comment nous poursuivons l'activité

{{nis2_continuity_text}}

## 3. Objectifs de rétablissement

Deux valeurs par système. **La durée d'indisponibilité admissible** avant
rétablissement, et **la perte de travail admissible** : si la dernière
sauvegarde datait d'une heure, une heure de saisie est perdue.

Un système peut avoir un délai de rétablissement rapide et une perte de données
importante : rétabli en quelques minutes, mais sur les données de la veille.

{{#block:nis2_recovery}}

{{#if:has_unset_objectives}}
### Systèmes sans objectifs

Certains systèmes ci-dessus n'affichent aucun objectif de rétablissement. Cela
ne signifie pas qu'ils sont sans importance : personne n'a encore déterminé
combien de temps nous pourrions nous en passer. Tant que cette décision n'est
pas prise, le présent plan ne comporte aucun engagement pour ces systèmes.
{{/if:has_unset_objectives}}

{{#ifnot:has_recovery_objectives}}
**Aucun objectif de rétablissement n'a été défini pour aucun système.** Ce plan
exprime des intentions et non des engagements tant que ce n'est pas fait.
{{/ifnot:has_recovery_objectives}}

## 4. Sauvegardes

Les modalités de rétablissement de chaque système figurent dans le tableau
ci-dessus. Lorsque cette colonne est vide, le rétablissement dépend des
dispositions propres au fournisseur, que nous n'avons pas vérifiées.

## 5. Tests

{{nis2_testing_text}}

**Un plan jamais testé est un document, pas une capacité.** Le jour où vous
avez besoin d'une sauvegarde n'est pas le bon moment pour découvrir si elle se
restaure.

## 6. Qui décide

Déclencher ce plan — déclarer que nous fonctionnons en mode continuité, puis
que nous sommes revenus à la normale — est une décision qui incombe à
quelqu'un. Cette responsabilité revient aux personnes qui pilotent les
incidents, telles qu'identifiées dans notre plan de réponse aux incidents.
"""


DOC = TemplateDoc(
    doc_type="business_continuity_plan",
    title="Business continuity plan (NIS2 Art. 21(2)(c))",
    tier=2,
    sort_order=52,
    sprint="S29A",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"nis2_recovery"},
    materiality="required",
    source_revision=1,
    version_no=1,
    change_note=(
        "Initial version (S29A). Recovery objectives rendered from "
        "systems.rto_minutes/rpo_minutes; systems without objectives are "
        "listed rather than hidden. DRAFT — not yet reviewed by counsel."
    ),
)


if __name__ == "__main__":
    run(DOC, "seed_s29a_bcp.sql")
