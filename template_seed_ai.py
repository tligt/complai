"""
template_seed_ai.py — S62 (D-161)

Authors the AI deployer pack: the AI acceptable use policy, the human
oversight policy, and the AI transparency notice.

Run:  python template_seed_ai.py aup     > seed_s62_ai_aup.sql
      python template_seed_ai.py hop     > seed_s62_ai_hop.sql
      python template_seed_ai.py notice  > seed_s62_ai_notice.sql

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. The acceptable use policy says personal data may go only into tools with
   a signed data processing agreement. That is stricter than the GDPR asks
   (a processor needs Art. 28 terms, which is what the DPA is), and it is
   the rule an SME can actually apply.
2. The human oversight policy states, in a table, where no overseer is named
   or an overseer's training has lapsed. An organisation may prefer that not
   to appear in a document an authority might read; the alternative is a
   policy that implies coverage it does not have (the BCP precedent, S29A).
3. The transparency notice covers Art. 50(1), (3) and (4). It does not
   replace the disclosure at the point of interaction that Art. 50(1)
   requires: it is the standing notice behind it, and says so.
"""

from __future__ import annotations

import sys

from template_seed_lib import TemplateDoc, run


AUP_EN = """\
# AI acceptable use policy

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**In force from {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. What this covers

Everyone who works for us, employees and contractors alike, whenever they use
an AI tool for their work: to write, summarise, translate, analyse, code,
answer customers or make or prepare a decision.

AI tools are useful and we want them used well. This policy says which ones,
for what, and with which information.

## 2. Approved tools and uses

Only the tools and uses below are approved. A tool approved for one purpose is
not approved for another.

{{#block:ai_approved_uses}}

{{#if:has_unapproved_systems}}
A tool marked "no approved use yet" may not be used for work until a use has
been approved.
{{/if:has_unapproved_systems}}

{{#ifnot:has_ai_uses}}
**No AI use has been approved yet.** Until one is, no AI tool may be used with
our information.
{{/ifnot:has_ai_uses}}

## 3. Information you must never put into an AI tool

- Passwords, access keys or any other credentials.
- Health data, or data revealing racial or ethnic origin, political opinions,
  religious or philosophical beliefs, trade union membership, sex life or
  sexual orientation, genetic or biometric data.
- Personal data of anyone — customers, colleagues, candidates — in a tool
  whose "personal data" column above does not say it is allowed.
- Information a customer or partner gave us in confidence, unless the tool is
  approved for exactly that work.

When in doubt, leave it out, or ask.

## 4. Your responsibilities

- **Check what it produces.** AI output can be wrong, invented or out of date.
  You are responsible for anything you send, publish or decide with it.
- **Do not let it decide alone** about a person — an applicant, an employee, a
  customer — without someone reviewing the result.
- **Say when content is AI-made** where people would otherwise not know: a
  chatbot must not pass for a person, and realistic images, audio or video
  that are generated or altered must be labelled.
{{#if:has_generative}}
- Our approved tools include ones that generate text, images, audio or video.
  Their output is reviewed by a person before it leaves the company.
{{/if:has_generative}}

## 5. Never allowed

Some uses of AI are prohibited by law (AI Act, Art. 5), whatever the tool and
whoever asks:

{{#block:ai_prohibited}}

## 6. New tools and new uses

Ask **{{ai_policy_owner}}** before using a new AI tool, or an approved tool for
a new purpose. It is added to our AI inventory, assessed and listed above
before anyone uses it. This includes free tools, browser extensions and AI
features switched on inside software we already use.

## 7. Training

Everyone who uses AI at work follows AI literacy training, renewed every year
(AI Act, Art. 4).

## 8. If something goes wrong

If you entered information you should not have, or an AI tool produced
something harmful, tell **{{ai_policy_owner}}** at once. If personal data is
involved, it is handled as a possible data breach. Breaching this policy is
handled like any other breach of our internal rules.
"""

AUP_FR = """\
# Politique d'utilisation acceptable de l'IA

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**En vigueur depuis le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Objet

Toute personne qui travaille pour nous, salariée ou prestataire, chaque fois
qu'elle utilise un outil d'IA dans son travail : pour rédiger, résumer,
traduire, analyser, coder, répondre à des clients, ou prendre ou préparer une
décision.

Les outils d'IA sont utiles et nous voulons qu'ils soient bien utilisés. Cette
politique indique lesquels, pour quoi, et avec quelles informations.

## 2. Outils et usages autorisés

Seuls les outils et usages ci-dessous sont autorisés. Un outil autorisé pour un
usage ne l'est pas pour un autre.

{{#block:ai_approved_uses}}

{{#if:has_unapproved_systems}}
Un outil marqué « aucun usage autorisé à ce jour » ne peut pas être utilisé
pour le travail tant qu'un usage n'a pas été autorisé.
{{/if:has_unapproved_systems}}

{{#ifnot:has_ai_uses}}
**Aucun usage de l'IA n'est encore autorisé.** D'ici là, aucun outil d'IA ne
peut être utilisé avec nos informations.
{{/ifnot:has_ai_uses}}

## 3. Ce que vous ne devez jamais saisir dans un outil d'IA

- Des mots de passe, clés d'accès ou autres identifiants.
- Des données de santé, ou révélant l'origine raciale ou ethnique, les
  opinions politiques, les convictions religieuses ou philosophiques,
  l'appartenance syndicale, la vie ou l'orientation sexuelle, des données
  génétiques ou biométriques.
- Des données personnelles de qui que ce soit — clients, collègues, candidats —
  dans un outil dont la colonne « données personnelles » ci-dessus ne les
  autorise pas.
- Des informations confiées par un client ou un partenaire, sauf si l'outil est
  autorisé pour précisément ce travail.

En cas de doute, ne les saisissez pas, ou demandez.

## 4. Vos responsabilités

- **Vérifiez ce qu'il produit.** Le résultat d'une IA peut être faux, inventé
  ou dépassé. Vous êtes responsable de tout ce que vous envoyez, publiez ou
  décidez avec lui.
- **Ne le laissez pas décider seul** au sujet d'une personne — candidat,
  salarié, client — sans que quelqu'un vérifie le résultat.
- **Signalez qu'un contenu est produit par l'IA** lorsque les personnes ne le
  sauraient pas autrement : un agent conversationnel ne doit pas se faire
  passer pour une personne, et les images, sons ou vidéos réalistes générés ou
  modifiés doivent être signalés.
{{#if:has_generative}}
- Nos outils autorisés comprennent des outils qui génèrent du texte, des
  images, du son ou de la vidéo. Leur production est relue par une personne
  avant de quitter l'entreprise.
{{/if:has_generative}}

## 5. Jamais autorisé

Certains usages de l'IA sont interdits par la loi (AI Act, art. 5), quel que
soit l'outil et quel que soit le demandeur :

{{#block:ai_prohibited}}

## 6. Nouveaux outils et nouveaux usages

Demandez à **{{ai_policy_owner}}** avant d'utiliser un nouvel outil d'IA, ou un
outil autorisé pour un nouvel usage. Il est ajouté à notre inventaire de l'IA,
évalué et listé ci-dessus avant toute utilisation. Cela vaut aussi pour les
outils gratuits, les extensions de navigateur et les fonctions d'IA activées
dans des logiciels que nous utilisons déjà.

## 7. Formation

Toute personne qui utilise l'IA au travail suit une formation à la maîtrise de
l'IA, renouvelée chaque année (AI Act, art. 4).

## 8. En cas de problème

Si vous avez saisi une information qui n'aurait pas dû l'être, ou si un outil
d'IA a produit quelque chose de préjudiciable, prévenez immédiatement
**{{ai_policy_owner}}**. Si des données personnelles sont concernées, la
situation est traitée comme une violation de données possible. Un manquement à
cette politique est traité comme tout manquement à nos règles internes.
"""


HOP_EN = """\
# Human oversight policy for AI

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**In force from {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Why

A person, not the system, stays responsible for what our AI does. For
high-risk AI systems the law requires it: a deployer assigns human oversight to
people with the necessary competence, training and authority (AI Act,
Art. 26(2)), from 2 December 2027.

This policy names those people and says what they do.

## 2. Who oversees what

{{#block:ai_oversight}}

{{#if:has_unassigned}}
**Some high-risk uses have no overseer.** They may not be used until
**{{ai_policy_owner}}** names one.
{{/if:has_unassigned}}

{{#if:has_untrained}}
**Some overseers have no current training** for this role. Their training is
arranged before they continue.
{{/if:has_untrained}}

## 3. What an overseer needs

- **Competence.** They understand what the system can and cannot do, from the
  provider's instructions for use, and follow training for this role.
- **Authority.** They may decide not to use the system in a given case,
  disregard or reverse its output, and stop it. Nobody may overrule them on
  safety in favour of the system's output.
- **Time.** Oversight is part of their job, not done on top of it.

## 4. What an overseer does

- Watches how the system performs and what it produces, and notices when it
  behaves unexpectedly.
- Guards against relying on its output too readily — especially when it
  produces recommendations about people.
- Interprets each output before it is used, using the provider's instructions.
- Stops the system, or a use of it, when it presents a risk.

For uses that are not high-risk, the same principle applies in a lighter form:
a person reviews the output before anyone relies on it.

## 5. Escalation

When an overseer believes a system presents a risk to health, safety or
fundamental rights, they suspend its use and inform **{{ai_policy_owner}}**,
who informs the provider (Art. 26(5)). A serious incident is reported to the
provider and to the market surveillance authority, and handled under our
incident procedure.

## 6. Records

Logs a high-risk system generates under our control are kept for at least six
months (Art. 26(6)).
{{#if:has_workers}}

## 7. Our workers

Some high-risk uses concern our workers. Workers and their representatives are
told before the system is put into use (Art. 26(7)), in addition to any
consultation national labour law requires.
{{/if:has_workers}}

## Review

**{{ai_policy_owner}}** reviews this policy every year, and whenever a
high-risk use is added or changes.
"""

HOP_FR = """\
# Politique de contrôle humain de l'IA

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**En vigueur depuis le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Pourquoi

Une personne, et non le système, reste responsable de ce que fait notre IA.
Pour les systèmes d'IA à haut risque, la loi l'exige : le déployeur confie le
contrôle humain à des personnes disposant de la compétence, de la formation et
de l'autorité nécessaires (AI Act, art. 26(2)), à partir du 2 décembre 2027.

Cette politique désigne ces personnes et décrit leur rôle.

## 2. Qui contrôle quoi

{{#block:ai_oversight}}

{{#if:has_unassigned}}
**Certains usages à haut risque n'ont pas de responsable du contrôle.** Ils ne
peuvent pas être utilisés tant que **{{ai_policy_owner}}** n'en a pas désigné.
{{/if:has_unassigned}}

{{#if:has_untrained}}
**Certains responsables du contrôle n'ont pas de formation à jour** pour ce
rôle. Leur formation est organisée avant qu'ils ne poursuivent.
{{/if:has_untrained}}

## 3. Ce dont un responsable du contrôle a besoin

- **Compétence.** Il comprend ce que le système peut et ne peut pas faire, à
  partir de la notice d'utilisation du fournisseur, et suit une formation pour
  ce rôle.
- **Autorité.** Il peut décider de ne pas utiliser le système dans un cas
  donné, ignorer ou infirmer son résultat, et l'arrêter. Personne ne peut le
  désavouer sur un point de sécurité au profit du résultat du système.
- **Temps.** Le contrôle fait partie de son travail, il ne s'y ajoute pas.

## 4. Ce que fait un responsable du contrôle

- Il surveille le fonctionnement du système et ce qu'il produit, et repère un
  comportement inattendu.
- Il se garde de se fier trop facilement à son résultat — en particulier
  lorsqu'il produit des recommandations sur des personnes.
- Il interprète chaque résultat avant son utilisation, à l'aide de la notice
  du fournisseur.
- Il arrête le système, ou un usage, lorsqu'il présente un risque.

Pour les usages qui ne sont pas à haut risque, le même principe s'applique de
manière allégée : une personne vérifie le résultat avant qu'on s'y fie.

## 5. Escalade

Lorsqu'un responsable du contrôle estime qu'un système présente un risque pour
la santé, la sécurité ou les droits fondamentaux, il suspend son utilisation et
informe **{{ai_policy_owner}}**, qui informe le fournisseur (art. 26(5)). Un
incident grave est signalé au fournisseur et à l'autorité de surveillance du
marché, et traité selon notre procédure d'incident.

## 6. Enregistrements

Les journaux générés par un système à haut risque sous notre contrôle sont
conservés au moins six mois (art. 26(6)).
{{#if:has_workers}}

## 7. Nos travailleurs

Certains usages à haut risque concernent nos travailleurs. Les travailleurs et
leurs représentants sont informés avant la mise en service du système
(art. 26(7)), en plus de toute consultation exigée par le droit du travail
national.
{{/if:has_workers}}

## Révision

**{{ai_policy_owner}}** revoit cette politique chaque année, et chaque fois
qu'un usage à haut risque est ajouté ou modifié.
"""


NOTICE_EN = """\
# How we use artificial intelligence

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**Last updated {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

We use AI systems in some of our work. Where you deal with one directly, the
law entitles you to know (AI Act, Art. 50). This notice lists those uses.
Each one is also identified at the moment you meet it; this page is the
standing explanation behind that.

## Where you may meet our AI

{{#block:ai_notice}}

{{#if:has_deep_fake}}
Images, audio or video we publish that are artificially generated or
manipulated are labelled as such where they appear.
{{/if:has_deep_fake}}

{{#if:has_emotion}}
Where a system recognises emotions or categorises people from biometric data,
you are told while it operates. Any personal data it processes is protected
under the GDPR, as set out in our privacy policy.
{{/if:has_emotion}}

## Questions

Write to {{contact_email}}. You may ask to deal with a person instead of an AI
system wherever that is possible.
"""

NOTICE_FR = """\
# Notre utilisation de l'intelligence artificielle

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**Mis à jour le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

Nous utilisons des systèmes d'IA dans une partie de notre activité. Lorsque
vous avez directement affaire à l'un d'eux, la loi vous donne le droit de le
savoir (AI Act, art. 50). Cette notice énumère ces usages. Chacun est aussi
signalé au moment où vous le rencontrez ; cette page en est l'explication
permanente.

## Où vous pouvez rencontrer notre IA

{{#block:ai_notice}}

{{#if:has_deep_fake}}
Les images, sons ou vidéos que nous publions et qui sont générés ou manipulés
artificiellement sont signalés comme tels là où ils apparaissent.
{{/if:has_deep_fake}}

{{#if:has_emotion}}
Lorsqu'un système reconnaît des émotions ou catégorise des personnes à partir
de données biométriques, vous en êtes informé pendant son fonctionnement. Les
données personnelles qu'il traite sont protégées par le RGPD, comme indiqué
dans notre politique de confidentialité.
{{/if:has_emotion}}

## Questions

Écrivez à {{contact_email}}. Vous pouvez demander à avoir affaire à une
personne plutôt qu'à un système d'IA lorsque c'est possible.
"""


DOCS = {
    "aup": (TemplateDoc(
        doc_type="ai_acceptable_use", title="AI acceptable use policy", tier=1, sort_order=60,
        sprint="S62", bodies={"en": AUP_EN, "fr": AUP_FR},
        blocks={"ai_approved_uses", "ai_prohibited"},
        change_note="Initial version (S62). Approved uses from the AI inventory; personal data "
                    "allowed only where the system's DPA is signed. DRAFT — not yet reviewed by counsel.",
    ), "seed_s62_ai_aup.sql"),
    "hop": (TemplateDoc(
        doc_type="ai_human_oversight", title="Human oversight policy for AI (AI Act Art. 26(2))",
        tier=1, sort_order=61, sprint="S62", bodies={"en": HOP_EN, "fr": HOP_FR},
        blocks={"ai_oversight"},
        change_note="Initial version (S62). Overseers and their training from the AI inventory and "
                    "the Training page; gaps stated. DRAFT — not yet reviewed by counsel.",
    ), "seed_s62_ai_hop.sql"),
    "notice": (TemplateDoc(
        doc_type="ai_transparency", title="AI transparency notice (AI Act Art. 50)", tier=1,
        sort_order=62, sprint="S62", bodies={"en": NOTICE_EN, "fr": NOTICE_FR},
        blocks={"ai_notice"},
        change_note="Initial templated version (S62), replacing the LLM-written notice of S28. "
                    "Uses from the AI inventory. DRAFT — not yet reviewed by counsel.",
    ), "seed_s62_ai_notice.sql"),
}


if __name__ == "__main__":
    doc, out = DOCS[sys.argv[1] if len(sys.argv) > 1 else "aup"]
    run(doc, out)
