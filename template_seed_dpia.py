"""
template_seed_dpia.py — S30

Authors the DPIA: the assessment Art. 35 requires where processing is likely to
result in a high risk to people.

Run:  python3 template_seed_dpia.py > seed_s30_dpia.sql

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
STRUCTURE FOLLOWS ART. 35(7)
---------------------------------------------------------------------------
    (a) a systematic description of the processing and its purposes
    (b) an assessment of necessity and proportionality
    (c) an assessment of the risks to rights and freedoms
    (d) the measures envisaged to address those risks

Sections 2 to 5 map onto those four in order. An auditor recognising the shape
of the document is worth more than a better-organised original.

---------------------------------------------------------------------------
ART. 36 IS THE POINT
---------------------------------------------------------------------------
Where residual risk remains high after mitigation, Art. 36(1) requires prior
consultation with the supervisory authority BEFORE processing begins.

It appears in section 6, in its own paragraph, in the words a client will act
on. Most DPIA templates bury this or omit it — and a client who mitigates to
medium and files the document has done the work, while one who leaves a high
residual risk and starts processing has broken Art. 36 without knowing it.

The flag is DERIVED from the register, never entered.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. Section 3 (necessity and proportionality) is the thinnest. The inventory
   holds the legal basis and the retention period, which bear on it, but the
   judgement itself is the client's and RECOSA supplies a prompt rather than
   an answer. Confirm that is the right level.
2. Likelihood and severity are shown as a pair and never multiplied into a
   score. A 1x4 and a 4x1 share a product and are opposite situations.
3. Section 7 records the DPO's advice only where a DPO is designated
   (Art. 35(2)). Where one is designated and was not consulted, the document
   says so rather than staying silent.
4. Where risks remain unassessed after measures, section 6 says the conclusion
   cannot be drawn. The assessment can still be produced — it is a working
   document — but it does not claim a conclusion it has not reached.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


BODY_EN = """\
# Data Protection Impact Assessment

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

## {{assessment_title}}

{{#if:has_policy_effective_date}}**Assessed {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Why this assessment was carried out

Article 35(1) requires a data protection impact assessment where processing is
likely to result in a high risk to the rights and freedoms of natural persons.

{{#if:has_scope_note}}
{{assessment_scope}}
{{/if:has_scope_note}}

This assessment is about the risk to **the people whose data is processed** —
not the risk to this organisation. Those are different questions and a document
that answers the second while appearing to answer the first is worse than none.

## 2. What the processing involves

{{#ifnot:has_processing_table}}
No processing activities have been recorded against this assessment.
{{/ifnot:has_processing_table}}

{{#block:dpia_processing}}

## 3. Whether it is necessary and proportionate

Article 35(7)(b) asks whether the processing is necessary for the purpose, and
whether the same purpose could be achieved with less data, less intrusion, or a
shorter retention period.

The purposes and legal bases above are the starting point for that judgement.
It is ours to make and to record here.

## 4. The risks, and what we do about them

Each risk is recorded with how likely it is and how serious it would be **for
the person**, before and after the measures we take.

The two are kept separate rather than combined into a score. A risk that is
rare but catastrophic and one that is constant but trivial can share a score
and demand entirely different responses.

{{#ifnot:has_risks}}
No risks have been recorded. This assessment is incomplete.
{{/ifnot:has_risks}}

{{#block:dpia_risks}}

## 5. Conclusion

{{#if:needs_consultation}}
**Residual risk remains high after the measures described above.**

Under Article 36(1), the supervisory authority — {{authority_line}} — must be
consulted **before this processing begins**.

This is not a formality and it is not satisfied by filing this document. The
processing does not start until the consultation has taken place.
{{/if:needs_consultation}}

{{#if:has_unassessed}}
**Some risks above have not been assessed after measures.** Until they are,
whether the residual risk is acceptable cannot be concluded, and neither can
whether Article 36 applies.
{{/if:has_unassessed}}

## 6. Keeping this current

Article 35(11) expects a review where the risk changes. A new system, a new
purpose, a new category of data, or an incident are all reasons to revisit
this.

{{#if:has_dpo_advice}}
## 7. The Data Protection Officer's advice

Article 35(2) requires the controller to seek the advice of the data protection
officer where one has been designated.

{{dpo_name}} was consulted and advised:

{{dpo_advice}}
{{/if:has_dpo_advice}}

{{#if:dpo_not_consulted}}
## 7. The Data Protection Officer's advice

A data protection officer is designated, and their advice was not sought for
this assessment. Article 35(2) requires it.
{{/if:dpo_not_consulted}}
"""

BODY_FR = """\
# Analyse d'impact relative à la protection des données

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

## {{assessment_title}}

{{#if:has_policy_effective_date}}**Analyse réalisée le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Pourquoi cette analyse a été réalisée

L'article 35(1) impose une analyse d'impact lorsqu'un traitement est
susceptible d'engendrer un risque élevé pour les droits et libertés des
personnes physiques.

{{#if:has_scope_note}}
{{assessment_scope}}
{{/if:has_scope_note}}

La présente analyse porte sur le risque pour **les personnes dont les données
sont traitées**, et non sur le risque pour l'organisation. Ce sont deux
questions distinctes, et un document qui répond à la seconde en paraissant
répondre à la première est pire que pas de document du tout.

## 2. En quoi consiste le traitement

{{#ifnot:has_processing_table}}
Aucune activité de traitement n'a été rattachée à cette analyse.
{{/ifnot:has_processing_table}}

{{#block:dpia_processing}}

## 3. Nécessité et proportionnalité

L'article 35(7)(b) demande si le traitement est nécessaire au regard de la
finalité, et si celle-ci pourrait être atteinte avec moins de données, une
moindre intrusion ou une durée de conservation plus courte.

Les finalités et bases légales ci-dessus constituent le point de départ de
cette appréciation. Il nous appartient de la porter et de la consigner ici.

## 4. Les risques et les mesures prises

Chaque risque est consigné avec sa probabilité et sa gravité **pour la
personne**, avant et après les mesures que nous prenons.

Les deux sont maintenues distinctes plutôt que combinées en un score. Un risque
rare mais catastrophique et un risque constant mais anodin peuvent partager un
même score et appeler des réponses entièrement différentes.

{{#ifnot:has_risks}}
Aucun risque n'a été consigné. La présente analyse est incomplète.
{{/ifnot:has_risks}}

{{#block:dpia_risks}}

## 5. Conclusion

{{#if:needs_consultation}}
**Le risque résiduel demeure élevé après les mesures décrites ci-dessus.**

En application de l'article 36(1), l'autorité de contrôle — {{authority_line}}
— doit être consultée **avant que ce traitement ne commence**.

Il ne s'agit pas d'une formalité et le dépôt du présent document n'y suffit
pas. Le traitement ne débute qu'une fois la consultation effectuée.
{{/if:needs_consultation}}

{{#if:has_unassessed}}
**Certains risques ci-dessus n'ont pas été évalués après mesures.** Tant que ce
n'est pas fait, le caractère acceptable du risque résiduel ne peut être conclu,
ni l'application de l'article 36.
{{/if:has_unassessed}}

## 6. Maintien à jour

L'article 35(11) prévoit un réexamen lorsque le risque évolue. Un nouveau
système, une nouvelle finalité, une nouvelle catégorie de données ou un
incident sont autant de motifs de revoir la présente analyse.

{{#if:has_dpo_advice}}
## 7. Avis du délégué à la protection des données

L'article 35(2) impose au responsable du traitement de demander l'avis du
délégué à la protection des données lorsqu'il en a désigné un.

{{dpo_name}} a été consulté et a rendu l'avis suivant :

{{dpo_advice}}
{{/if:has_dpo_advice}}

{{#if:dpo_not_consulted}}
## 7. Avis du délégué à la protection des données

Un délégué à la protection des données est désigné et son avis n'a pas été
sollicité pour la présente analyse. L'article 35(2) l'exige.
{{/if:dpo_not_consulted}}
"""


DOC = TemplateDoc(
    doc_type="dpia",
    title="Data Protection Impact Assessment (Art. 35 GDPR)",
    tier=3,
    sort_order=60,
    sprint="S30",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"dpia_processing", "dpia_risks"},
    materiality="conditional",
    source_revision=1,
    version_no=1,
    change_note=(
        "Initial version (S30). Structure follows Art. 35(7). The Art. 36 "
        "prior consultation conclusion is derived from the risk register and "
        "never entered. DRAFT — not yet reviewed by counsel."
    ),
)


if __name__ == "__main__":
    run(DOC, "seed_s30_dpia.sql")
