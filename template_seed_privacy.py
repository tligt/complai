"""
template_seed_privacy.py — S28

Authors the Privacy Policy: the Art. 13 and 14 information notice a controller
publishes for the people whose data it holds.

Run:  python3 template_seed_privacy.py > seed_s28_privacy.sql

NEVER IMPORTED AT RUNTIME. The machinery lives in template_seed_lib.py; this
file is text and nothing else.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
WHY THIS IS TIER 1
---------------------------------------------------------------------------
Art. 13 and 14 prescribe the content. Every prescribed item is structured data
after S26, S26C and S28: purposes, bases, categories, recipients, transfers,
retention, and now the source the data came from.

The evidence supports it too. This document went from 30-40% to 80% review
scores by constraining toward fixed structure. Constraint produced the gain,
and what remains is more constraint rather than better prose.

---------------------------------------------------------------------------
WHY THE READER IS ADDRESSED AS "YOU"
---------------------------------------------------------------------------
Art. 12(1) requires the information to be concise, transparent, intelligible
and in clear and plain language. A notice written about "data subjects" is
about someone else. The registers are written for a supervisory authority and
say "the organisation"; this is written for the person and says "you".

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. RIGHTS ARE CONDITIONAL. Sections 6.1 to 6.3 render only where the legal
   basis gives rise to them: withdrawal where consent is used, objection for
   legitimate interests or public task, portability for consent or contract.
   Access, rectification and restriction are stated unconditionally. Confirm
   the mapping, and confirm that omitting a right the client's processing does
   not give rise to is preferable to listing it with a caveat.
2. Section 6.4 qualifies erasure where retention is legally required, rather
   than promising deletion the client cannot perform. Confirm the wording does
   not read as a refusal of the right itself.
3. The Art. 14 disclosure appears per activity, under the table, and only for
   sources other than the data subject. Art. 14(2)(f) is answered by naming the
   source; where the source was public, a second sentence says so.
4. Section 3 states that this policy covers processing the organisation
   determines. Processing it carries out on a customer's instructions is
   covered by that customer's own notice. Confirm the characterisation.
5. Art. 13(2)(e) — whether provision is statutory or contractual and the
   consequences of not providing — is NOT covered. There is no field for it.
   Flagged rather than silently absent.
6. Art. 13(2)(f) / Art. 22 automated decision-making is NOT covered. Same
   reason. Deferred with S51.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


# ===========================================================================
# ENGLISH
# ===========================================================================

BODY_EN = """\
# Privacy Policy

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{registered_address}}

{{#if:has_enterprise_number}}Company registration number: {{enterprise_number}}{{/if:has_enterprise_number}}

{{#if:has_policy_effective_date}}**In force from {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Who we are

We are responsible for the personal data described in this policy. If you have
a question about any of it, write to us at {{contact_email}}.

{{#if:has_dpo_section}}
### Data Protection Officer

{{dpo_name}} — {{dpo_email}}
{{/if:has_dpo_section}}

## 2. What this policy covers

This policy explains what we do with personal data, why we are allowed to do
it, how long we keep it, and what you can ask us to do about it.

It covers the processing we decide the purposes and means of. Where we handle
personal data on a customer's instructions, that customer's own privacy notice
covers it, not this one.

## 3. What we do with your data

Find the heading that describes you. If more than one applies — you might be
both a customer and an employee — read each of them: the processing is
different in each case, and so are the reasons for it and how long we keep it.

{{#ifnot:has_role_sections}}
We have not yet recorded any processing under this policy. That does not mean
none takes place; it means none has yet been documented here.
{{/ifnot:has_role_sections}}

{{#block:privacy_role_sections}}

{{#if:has_art14}}
Some of what we hold did not come from you. Where that is the case we have said
so under the relevant entry above, and named where it came from.{{#if:has_public_source}} Where the
information was already publicly available, we have said that too.{{/if:has_public_source}}
{{/if:has_art14}}

{{#if:has_special_categories}}
### Sensitive information

Some of what we hold falls into the categories the law treats as sensitive —
for example health information. We only handle it where the law specifically
allows it, and we apply additional restrictions to who can see it.
{{/if:has_special_categories}}

{{#if:has_recipients}}
## 4. Who else sees it

We use the organisations below to run parts of our business. They act on our
instructions and may not use your data for their own purposes.

{{#block:privacy_recipients}}

We also share information where the law requires it — with tax and social
security authorities, and with a court or a regulator where we are obliged to.
{{/if:has_recipients}}

{{#if:has_transfers}}
## 5. Sending data outside the EEA

Some of the organisations above process data outside the European Economic
Area. Where that happens we rely on the safeguards named here.

{{#block:privacy_transfers}}

You can ask us for a copy of the safeguard that applies to a particular
transfer.
{{/if:has_transfers}}

## 6. What you can ask us to do

You can ask us for a copy of the personal data we hold about you, ask us to
correct it if it is wrong, and ask us to restrict what we do with it while a
question about it is being resolved.

{{#if:has_right_withdraw}}
### Withdrawing consent

Where we rely on your consent, you can withdraw it at any time. Withdrawing it
does not affect anything we did before you withdrew, and it does not affect
processing we carry out for a different reason.
{{/if:has_right_withdraw}}

{{#if:has_right_object}}
### Objecting

Where we rely on our own legitimate interests, you can object. We will stop
unless we can show compelling grounds that override your interests, rights and
freedoms. Where we use your data for direct marketing, you can object at any
time and we will stop.
{{/if:has_right_object}}

{{#if:has_right_portability}}
### Taking your data elsewhere

Where we hold data because you consented or because we have a contract with
you, you can ask for it in a machine-readable format, or ask us to send it
directly to someone else where that is technically possible.
{{/if:has_right_portability}}

### Deletion

You can ask us to delete your data.

{{#if:has_statutory_retention}}
We cannot always do it. Some of what we hold is kept because the law requires
us to keep it, and for as long as that requirement lasts we have to refuse a
deletion request for that data. Where that applies we will tell you which data
is affected and why. Everything not caught by such a requirement is deleted.
{{/if:has_statutory_retention}}

To exercise any of these, write to {{contact_email}}. We answer within one
month. If a request is complex we may take longer, and if we do we will tell
you within that first month and explain why.

## 7. Complaints

If you are unhappy with how we have handled your data, tell us first — it is
usually the quickest way to put something right.

You can also complain to {{authority_name}}{{#if:has_authority_url}} ({{authority_url}}){{/if:has_authority_url}}, and you can do so
without contacting us first.

## 8. Changes to this policy

We update this policy when what we do with personal data changes. The date it
came into force is at the top. We keep the previous versions, so if you need to
know what applied at some point in the past, ask us.
"""


# ===========================================================================
# FRENCH
# ===========================================================================

BODY_FR = """\
# Politique de confidentialité

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{registered_address}}

{{#if:has_enterprise_number}}Numéro d'entreprise : {{enterprise_number}}{{/if:has_enterprise_number}}

{{#if:has_policy_effective_date}}**En vigueur depuis le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Qui nous sommes

Nous sommes responsables des données à caractère personnel décrites dans la
présente politique. Pour toute question, écrivez-nous à {{contact_email}}.

{{#if:has_dpo_section}}
### Délégué à la protection des données

{{dpo_name}} — {{dpo_email}}
{{/if:has_dpo_section}}

## 2. Ce que couvre la présente politique

Cette politique explique ce que nous faisons des données à caractère personnel,
ce qui nous y autorise, combien de temps nous les conservons et ce que vous
pouvez nous demander à leur sujet.

Elle couvre les traitements dont nous déterminons les finalités et les moyens.
Lorsque nous traitons des données sur instruction d'un client, c'est la
politique de confidentialité de ce client qui s'applique, et non celle-ci.

## 3. Ce que nous faisons de vos données

Repérez la rubrique qui vous concerne. Si plusieurs s'appliquent — vous pouvez
être à la fois client et membre du personnel — lisez-les toutes : les
traitements diffèrent, tout comme leurs motifs et leurs durées de conservation.

{{#ifnot:has_role_sections}}
Aucun traitement n'a encore été enregistré au titre de la présente politique.
Cela ne signifie pas qu'aucun n'a lieu, mais qu'aucun n'y est encore documenté.
{{/ifnot:has_role_sections}}

{{#block:privacy_role_sections}}

{{#if:has_art14}}
Certaines des données que nous détenons ne proviennent pas de vous. Le cas
échéant, nous l'avons indiqué sous l'entrée concernée ci-dessus, en précisant
leur provenance.{{#if:has_public_source}} Lorsque l'information était déjà accessible au public, nous
l'avons également signalé.{{/if:has_public_source}}
{{/if:has_art14}}

{{#if:has_special_categories}}
### Données sensibles

Certaines données que nous détenons relèvent des catégories que la loi
considère comme sensibles — des données de santé, par exemple. Nous ne les
traitons que lorsque la loi l'autorise expressément et nous restreignons
davantage les personnes qui peuvent y accéder.
{{/if:has_special_categories}}

{{#if:has_recipients}}
## 4. Qui d'autre y a accès

Nous faisons appel aux organisations ci-dessous pour faire fonctionner une
partie de notre activité. Elles agissent sur nos instructions et ne peuvent pas
utiliser vos données à leurs propres fins.

{{#block:privacy_recipients}}

Nous communiquons également des informations lorsque la loi l'exige — aux
administrations fiscales et de sécurité sociale, ainsi qu'à une juridiction ou
à une autorité de contrôle lorsque nous y sommes tenus.
{{/if:has_recipients}}

{{#if:has_transfers}}
## 5. Transferts hors de l'EEE

Certaines des organisations mentionnées ci-dessus traitent des données en
dehors de l'Espace économique européen. Le cas échéant, nous nous appuyons sur
les garanties indiquées ici.

{{#block:privacy_transfers}}

Vous pouvez nous demander une copie de la garantie applicable à un transfert
déterminé.
{{/if:has_transfers}}

## 6. Ce que vous pouvez nous demander

Vous pouvez nous demander une copie des données à caractère personnel que nous
détenons à votre sujet, nous demander de les rectifier si elles sont inexactes,
et nous demander d'en limiter le traitement le temps qu'une question les
concernant soit tranchée.

{{#if:has_right_withdraw}}
### Retirer votre consentement

Lorsque nous nous fondons sur votre consentement, vous pouvez le retirer à tout
moment. Ce retrait ne remet pas en cause ce qui a été fait auparavant et
n'affecte pas les traitements que nous effectuons pour un autre motif.
{{/if:has_right_withdraw}}

{{#if:has_right_object}}
### Vous opposer

Lorsque nous nous fondons sur nos intérêts légitimes, vous pouvez vous opposer
au traitement. Nous y mettrons fin, sauf si nous pouvons démontrer des motifs
impérieux qui prévalent sur vos intérêts, droits et libertés. Lorsque vos
données servent à de la prospection, vous pouvez vous y opposer à tout moment
et nous cesserons.
{{/if:has_right_object}}

{{#if:has_right_portability}}
### Emporter vos données

Lorsque nous détenons des données parce que vous y avez consenti ou en vertu
d'un contrat conclu avec vous, vous pouvez en demander une copie dans un format
lisible par machine, ou nous demander de les transmettre directement à un tiers
lorsque cela est techniquement possible.
{{/if:has_right_portability}}

### Effacement

Vous pouvez nous demander d'effacer vos données.

{{#if:has_statutory_retention}}
Nous ne le pouvons pas toujours. Certaines données sont conservées parce que la
loi nous l'impose, et tant que cette obligation dure, nous devons refuser une
demande d'effacement portant sur ces données. Le cas échéant, nous vous
indiquerons lesquelles sont concernées et pourquoi. Tout ce qui n'est pas visé
par une telle obligation est effacé.
{{/if:has_statutory_retention}}

Pour exercer l'un de ces droits, écrivez à {{contact_email}}. Nous répondons
dans un délai d'un mois. Si une demande est complexe, ce délai peut être
prolongé ; nous vous en informerons dans le premier mois en vous expliquant
pourquoi.

## 7. Réclamations

Si vous n'êtes pas satisfait de la manière dont nous avons traité vos données,
dites-le-nous d'abord : c'est généralement le moyen le plus rapide de corriger
une situation.

Vous pouvez également introduire une réclamation auprès de
{{authority_name}}{{#if:has_authority_url}} ({{authority_url}}){{/if:has_authority_url}}, sans avoir à nous contacter au préalable.

## 8. Modifications de la présente politique

Nous mettons cette politique à jour lorsque ce que nous faisons des données à
caractère personnel change. La date d'entrée en vigueur figure en tête du
document. Nous conservons les versions précédentes : si vous avez besoin de
savoir ce qui s'appliquait à un moment donné, demandez-le-nous.
"""


DOC = TemplateDoc(
    doc_type="privacy_policy",
    title="Privacy Policy (Art. 13 and 14 GDPR)",
    tier=1,
    sort_order=10,
    sprint="S28",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"privacy_role_sections", "privacy_recipients", "privacy_transfers"},
    materiality="required",
    source_revision=1,
    version_no=1,
    change_note=(
        "Initial version (S28). Tier 1 — no runtime LLM. Rights sections are "
        "conditional on the legal bases in use; the Art. 14 source disclosure "
        "renders per activity only where data was not obtained from the data "
        "subject. DRAFT — not yet reviewed by counsel."
    ),
)


if __name__ == "__main__":
    run(DOC, "seed_s28_privacy.sql")
