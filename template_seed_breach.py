"""
template_seed_breach.py — S29A

Authors the incident and breach notification procedure: what to do in the first
hours, and who has to be told.

Run:  python3 template_seed_breach.py > seed_s29a_breach.sql

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
ONE DOCUMENT, TWO REGIMES
---------------------------------------------------------------------------
                    GDPR Art. 33            NIS2 Art. 23
    trigger         personal data breach     significant incident
    to              supervisory authority    CSIRT / competent authority
    clock           72 hours                 24h early warning
                                             72h notification
                                             1 month final report

Most incidents are one or the other. Some are both — ransomware on a system
holding personal data starts both clocks, and the 24-hour one binds.

Two separate documents would make someone under time pressure choose between
them in the first hour, which is exactly when they are least able to. So: one
document, two decision paths, and the both-apply case stated rather than left
to be worked out.

---------------------------------------------------------------------------
WHY THE FIRST SECTION IS SO SHORT
---------------------------------------------------------------------------
This is read at 2am by someone who has just found out. Everything they must do
in the first hour is on the first page, in the order they do it, with no
conditions to evaluate first.

The assessment of whether it is notifiable comes SECOND, because containment
does not depend on the answer and waiting for a lawyer before pulling a plug is
how a bad hour becomes a bad week.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. The 24-hour NIS2 early warning is presented as the binding deadline
   whenever both regimes apply. Confirm that framing.
2. Section 3 tells staff to report anything suspicious without judging whether
   it qualifies. Deliberate — an employee who has to assess "significant"
   before reporting will under-report — but it means the log will contain
   non-incidents.
3. The GDPR path does not attempt to define "high risk" for Art. 34. It names
   the decision and who makes it. Confirm that is the right level.
4. Timelines are rendered from a static table, not from client data. They are
   the law; if they change, the template changes.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run


BODY_EN = """\
# Incident and breach notification procedure

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**In force from {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}NIS2 classification: {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. The first hour

Do these in order. Do not wait for anyone to decide whether this is
reportable — that comes next, and it does not change any of the following.

1. **Contain it.** Disconnect what needs disconnecting. Do not power systems
   off if it can be avoided: it destroys evidence you may need.
2. **Write down the time** you found out, and what you saw. Everything after
   this is measured from that moment.
3. **Tell the person who leads incidents.** {{nis2_roles_text}}
4. **Do not delete anything**, including the thing that caused it.
5. **Do not tell customers or the public yet.** That decision comes with the
   assessment below.

## 2. Is it reportable?

Two separate regimes can apply, and they ask different questions.

**Is personal data involved?** If personal data has been lost, exposed,
altered or made unavailable — even temporarily — the GDPR applies. Clock: 72
hours from becoming aware.

{{#if:has_both_regimes}}
**Is it a significant incident?** NIS2 applies where an incident seriously
disrupts the services you provide, or causes considerable operational or
financial damage. Clock: **24 hours** from becoming aware.

**Both can apply at once.** Ransomware on a system holding personal data is
the obvious case. When both apply, work to the 24-hour deadline — meeting it
also leaves time for the other.
{{/if:has_both_regimes}}

If you are unsure, treat it as reportable and say so in the notification. A
notification that turns out to be unnecessary costs an email. A missed one does
not.

## 3. Reporting deadlines

{{#block:nis2_timeline}}

**Who to contact**

- Supervisory authority: {{authority_name}}{{#if:has_authority_url}} — {{authority_url}}{{/if:has_authority_url}}
- National CSIRT: {{csirt_name}}{{#if:has_csirt_url}} — {{csirt_url}}{{/if:has_csirt_url}}
{{#if:has_dpo_section}}- Data Protection Officer: {{dpo_name}} — {{dpo_email}}{{/if:has_dpo_section}}

You do not need complete information to notify. Send what you have within the
deadline and follow up — that is what the law expects, and a late complete
notification is worse than an early incomplete one.

## 4. Reporting an incident internally

Anyone who notices something wrong reports it to {{contact_email}} without
first deciding whether it is serious. Judging significance is not the job of
the person who spotted it, and an organisation where staff assess before
reporting is one that finds out late.

Report a lost or stolen device, an email you replied to and should not have, a
file shared with the wrong person, a system behaving oddly, a supplier telling
you they have had an incident.

## 5. After it is closed

Record what happened, what was done, and what changed as a result. Where the
incident was notified, the final report is due within a month.

Reviewing an incident is not optional paperwork — it is the only part of this
procedure that reduces the chance of the next one.
"""

BODY_FR = """\
# Procédure de notification des incidents et violations

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**En vigueur depuis le {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}Classification NIS2 : {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. La première heure

À faire dans cet ordre. N'attendez pas qu'une décision soit prise sur le
caractère notifiable de l'incident : cela vient ensuite et ne change rien à ce
qui suit.

1. **Contenez l'incident.** Déconnectez ce qui doit l'être. Évitez d'éteindre
   les systèmes : cela détruit des éléments de preuve dont vous pourriez avoir
   besoin.
2. **Notez l'heure** à laquelle vous en avez eu connaissance, et ce que vous
   avez constaté. Tous les délais courent à partir de ce moment.
3. **Prévenez la personne qui pilote les incidents.** {{nis2_roles_text}}
4. **Ne supprimez rien**, y compris ce qui est à l'origine de l'incident.
5. **N'informez pas encore les clients ni le public.** Cette décision relève de
   l'évaluation ci-dessous.

## 2. L'incident est-il notifiable ?

Deux régimes distincts peuvent s'appliquer et ils posent des questions
différentes.

**Des données à caractère personnel sont-elles concernées ?** Si des données
ont été perdues, divulguées, altérées ou rendues indisponibles — même
temporairement — le RGPD s'applique. Délai : 72 heures à compter de la prise de
connaissance.

{{#if:has_both_regimes}}
**S'agit-il d'un incident important ?** NIS2 s'applique lorsqu'un incident
perturbe gravement les services que vous fournissez ou cause un dommage
opérationnel ou financier considérable. Délai : **24 heures** à compter de la
prise de connaissance.

**Les deux peuvent s'appliquer simultanément.** Un rançongiciel sur un système
contenant des données à caractère personnel en est l'exemple type. Dans ce cas,
travaillez sur le délai de 24 heures : le respecter laisse le temps de traiter
l'autre.
{{/if:has_both_regimes}}

En cas de doute, considérez l'incident comme notifiable et indiquez-le dans la
notification. Une notification qui s'avère inutile coûte un courriel. Une
notification manquée, non.

## 3. Délais de notification

{{#block:nis2_timeline}}

**Qui contacter**

- Autorité de contrôle : {{authority_name}}{{#if:has_authority_url}} — {{authority_url}}{{/if:has_authority_url}}
- CSIRT national : {{csirt_name}}{{#if:has_csirt_url}} — {{csirt_url}}{{/if:has_csirt_url}}
{{#if:has_dpo_section}}- Délégué à la protection des données : {{dpo_name}} — {{dpo_email}}{{/if:has_dpo_section}}

Vous n'avez pas besoin d'informations complètes pour notifier. Transmettez ce
dont vous disposez dans le délai imparti, puis complétez : c'est ce que la loi
prévoit, et une notification tardive mais complète vaut moins qu'une
notification rapide et partielle.

## 4. Signaler un incident en interne

Toute personne qui constate une anomalie la signale à {{contact_email}} sans
avoir à décider au préalable si elle est grave. Apprécier la gravité n'incombe
pas à la personne qui constate, et une organisation où le personnel évalue
avant de signaler est une organisation qui apprend tard.

Signalez un appareil perdu ou volé, un courriel auquel vous avez répondu à
tort, un fichier partagé avec la mauvaise personne, un système au comportement
inhabituel, ou un fournisseur vous annonçant un incident.

## 5. Après la clôture

Consignez ce qui s'est passé, ce qui a été fait et ce qui a changé en
conséquence. Lorsque l'incident a été notifié, le rapport final est dû dans le
mois.

Le retour d'expérience n'est pas une formalité : c'est la seule partie de cette
procédure qui réduit la probabilité de l'incident suivant.
"""


DOC = TemplateDoc(
    doc_type="breach_notification_procedure",
    title="Incident and breach notification procedure (GDPR Art. 33, NIS2 Art. 23)",
    tier=2,
    sort_order=50,
    sprint="S29A",
    bodies={"en": BODY_EN, "fr": BODY_FR},
    blocks={"nis2_timeline"},
    materiality="required",
    source_revision=1,
    version_no=1,
    change_note=(
        "Initial version (S29A). One procedure covering both the GDPR Art. 33 "
        "and NIS2 Art. 23 regimes, with the both-apply case stated explicitly "
        "and the 24-hour NIS2 clock presented as binding where both apply. "
        "DRAFT — not yet reviewed by counsel."
    ),
)


if __name__ == "__main__":
    run(DOC, "seed_s29a_breach.sql")
