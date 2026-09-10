"""
template_seed_nis2ra.py — S30

Authors the NIS2 cybersecurity risk assessment: Art. 21(2)(a), "policies on
risk analysis and information system security".

Run:  python3 template_seed_nis2ra.py > seed_s30_nis2ra.sql

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
NOT A DPIA WITH DIFFERENT WORDS
---------------------------------------------------------------------------
The register is the same shape. What it measures is not (D-85):

    DPIA   risk to the rights and freedoms of natural persons
           high residual risk -> Art. 36 prior consultation, before processing
    NIS2   risk to network and information systems
           high residual risk -> a named person accepts it, or nobody has

There is no Art. 36 here and no authority to consult. Art. 20(1) puts approval
of the measures on the management body and makes them supervise implementation,
so what a high residual risk needs is somebody's name against it.

This document therefore ends differently, and section 5 asks a question the
DPIA never asks: who decided this was acceptable?

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. Section 5 treats an unaccepted high residual risk as a finding. Art. 20(1)
   makes management responsible for approving the measures; an unaccepted risk
   is a decision nobody has made. Confirm that framing.
2. Art. 21(1) requires measures "appropriate to the risk" and proportionate to
   exposure, size and the likelihood of incidents. This document records the
   risks and the measures; whether they are appropriate is a judgement it does
   not claim to make.
3. Likelihood and severity are a pair, never multiplied.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


BODY_EN = """\
# Cybersecurity risk assessment

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

## {{assessment_title}}

{{#if:has_policy_effective_date}}**Assessed {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Why this assessment exists

Article 21(2)(a) requires policies on risk analysis and information system
security. This is the analysis those policies rest on.

{{#if:has_scope_note}}
{{assessment_scope}}
{{/if:has_scope_note}}

It is about the risk to **the systems and services we depend on**. Risk to the
people whose personal data we hold is a different question, assessed separately
under Article 35 GDPR — some situations appear in both, with different
consequences.

## 2. What is in scope

{{#ifnot:has_systems_table}}
No systems have been recorded against this assessment.
{{/ifnot:has_systems_table}}

{{#block:nis2ra_systems}}

Recovery objectives for these systems are set out in our business continuity
plan.

## 3. The risks

Each risk is recorded with how likely it is and how serious it would be, before
and after the measures we take.

The two are kept separate rather than combined into a score. A risk that is
rare but catastrophic and one that is constant but trivial can share a score
and demand entirely different responses.

{{#ifnot:has_risks}}
No risks have been recorded. This assessment is incomplete.
{{/ifnot:has_risks}}

{{#block:dpia_risks}}

## 4. Whether the measures are appropriate

Article 21(1) requires measures appropriate to the risk, taking account of our
exposure, our size, and the likelihood of incidents occurring.

This document records the risks and what we do about them. Whether that is
appropriate is a judgement, and it is ours — reviewing it is the point of
repeating this assessment rather than filing it.

## 5. Accepting what remains

{{#if:has_unaccepted}}
**Some high residual risks have not been accepted by anyone.**

Article 20(1) makes the management body approve the cybersecurity measures and
supervise their implementation. A high risk left in the register with nobody's
name against it is not a risk that was accepted — it is a decision nobody made.
{{/if:has_unaccepted}}

{{#if:has_unassessed}}
**Some risks above have not been assessed after measures.** Until they are,
whether what remains is acceptable cannot be concluded.
{{/if:has_unassessed}}

## 6. Keeping this current

A new system, a supplier change, a significant incident, or a material change
in what we do are all reasons to revisit this. An assessment that describes
last year's systems protects nothing.
"""

BODY_FR = """\
# Analyse des risques de cybersécurité

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

## {{assessment_title}}

{{#if:has_policy_effective_date}}**Analyse réalisée le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Objet de la présente analyse

L'article 21(2)(a) impose des politiques d'analyse des risques et de sécurité
des systèmes d'information. La présente analyse en constitue le fondement.

{{#if:has_scope_note}}
{{assessment_scope}}
{{/if:has_scope_note}}

Elle porte sur le risque pesant sur **les systèmes et services dont nous
dépendons**. Le risque pour les personnes dont nous détenons les données à
caractère personnel relève d'une autre question, évaluée séparément au titre de
l'article 35 du RGPD — certaines situations relèvent des deux, avec des
conséquences différentes.

## 2. Périmètre

{{#ifnot:has_systems_table}}
Aucun système n'a été rattaché à la présente analyse.
{{/ifnot:has_systems_table}}

{{#block:nis2ra_systems}}

Les objectifs de rétablissement de ces systèmes figurent dans notre plan de
continuité d'activité.

## 3. Les risques

Chaque risque est consigné avec sa probabilité et sa gravité, avant et après
les mesures que nous prenons.

Les deux sont maintenues distinctes plutôt que combinées en un score. Un risque
rare mais catastrophique et un risque constant mais anodin peuvent partager un
même score et appeler des réponses entièrement différentes.

{{#ifnot:has_risks}}
Aucun risque n'a été consigné. La présente analyse est incomplète.
{{/ifnot:has_risks}}

{{#block:dpia_risks}}

## 4. Caractère approprié des mesures

L'article 21(1) exige des mesures appropriées au risque, compte tenu de notre
exposition, de notre taille et de la probabilité de survenance d'incidents.

Le présent document consigne les risques et les mesures prises. Leur caractère
approprié relève d'une appréciation, et cette appréciation nous incombe : la
réexaminer est la raison d'être de la répétition de cette analyse.

## 5. Acceptation du risque résiduel

{{#if:has_unaccepted}}
**Certains risques résiduels élevés n'ont été acceptés par personne.**

L'article 20(1) charge l'organe de direction d'approuver les mesures de
cybersécurité et d'en superviser la mise en œuvre. Un risque élevé laissé au
registre sans nom en regard n'est pas un risque accepté : c'est une décision
que personne n'a prise.
{{/if:has_unaccepted}}

{{#if:has_unassessed}}
**Certains risques ci-dessus n'ont pas été évalués après mesures.** Tant que ce
n'est pas fait, le caractère acceptable de ce qui subsiste ne peut être conclu.
{{/if:has_unassessed}}

## 6. Maintien à jour

Un nouveau système, un changement de fournisseur, un incident significatif ou
une évolution notable de notre activité sont autant de motifs de réexamen. Une
analyse décrivant les systèmes de l'an dernier ne protège rien.
"""


DOC = TemplateDoc(
    doc_type="nis2_risk_assessment",
    title="Cybersecurity risk assessment (NIS2 Art. 21(2)(a))",
    tier=3,
    sort_order=61,
    sprint="S30",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"nis2ra_systems", "dpia_risks"},
    materiality="required",
    source_revision=1,
    version_no=1,
    change_note=(
        "Initial version (S30). Shares the register with the DPIA and ends "
        "differently: no Art. 36, and an unaccepted high residual risk is a "
        "finding under Art. 20(1). DRAFT — not yet reviewed by counsel."
    ),
)


if __name__ == "__main__":
    run(DOC, "seed_s30_nis2ra.sql")
