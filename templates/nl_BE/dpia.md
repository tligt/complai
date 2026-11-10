# Gegevensbeschermingseffectbeoordeling

*Conceptvertaling — nog niet nagekeken door een Belgische jurist.*

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

**{{assessment_title}}**

{{#if:has_policy_effective_date}}Beoordeeld op {{policy_effective_date}}.{{/if:has_policy_effective_date}}

## 1. Waarom deze beoordeling werd uitgevoerd

Artikel 35, lid 1, vereist een gegevensbeschermingseffectbeoordeling wanneer
een verwerking waarschijnlijk een hoog risico inhoudt voor de rechten en
vrijheden van natuurlijke personen.

{{#if:has_scope_note}}
{{assessment_scope}}
{{/if:has_scope_note}}

Deze beoordeling gaat over het risico voor **de personen van wie de gegevens
worden verwerkt** — niet over het risico voor deze organisatie. Dat zijn
verschillende vragen, en een document dat de tweede beantwoordt terwijl het de
eerste lijkt te beantwoorden, is erger dan geen document.

## 2. Wat de verwerking inhoudt

{{#ifnot:has_processing_table}}
Er zijn geen verwerkingsactiviteiten aan deze beoordeling gekoppeld.
{{/ifnot:has_processing_table}}

{{#block:dpia_processing}}

## 3. Noodzaak en evenredigheid

Artikel 35, lid 7, onder b), vraagt of de verwerking noodzakelijk is voor het
doel, en of hetzelfde doel kan worden bereikt met minder gegevens, minder
ingrijpend of met een kortere bewaartermijn.

De doeleinden en rechtsgronden hierboven zijn het vertrekpunt voor dat oordeel.
Het is aan ons om het te vellen en hier vast te leggen.

## 4. De risico's, en wat wij eraan doen

Elk risico wordt geregistreerd met hoe waarschijnlijk het is en hoe ernstig het
zou zijn **voor de betrokkene**, vóór en na de maatregelen die wij nemen.

Beide worden afzonderlijk gehouden in plaats van tot één score te worden
samengevoegd. Een risico dat zelden voorkomt maar rampzalig is, en een risico
dat voortdurend voorkomt maar onbeduidend is, kunnen dezelfde score hebben en
toch een totaal andere aanpak vereisen.

{{#ifnot:has_risks}}
Er zijn geen risico's geregistreerd. Deze beoordeling is onvolledig.
{{/ifnot:has_risks}}

{{#block:dpia_risks}}

## 5. Conclusie

{{#if:needs_consultation}}
**Na de hierboven beschreven maatregelen blijft het restrisico hoog.**

Overeenkomstig artikel 36, lid 1, moet de toezichthoudende autoriteit —
{{authority_line}} — worden geraadpleegd **voordat deze verwerking begint**.

Dit is geen formaliteit, en het indienen van dit document volstaat niet. De
verwerking begint pas nadat de raadpleging heeft plaatsgevonden.
{{/if:needs_consultation}}

{{#if:has_unassessed}}
**Sommige risico's hierboven zijn na de maatregelen niet beoordeeld.** Zolang
dat niet gebeurd is, kan niet worden besloten of het restrisico aanvaardbaar
is, noch of artikel 36 van toepassing is.
{{/if:has_unassessed}}

## 6. Actueel houden

Artikel 35, lid 11, verwacht een herbeoordeling wanneer het risico verandert.
Een nieuw systeem, een nieuw doel, een nieuwe categorie gegevens of een
incident zijn telkens redenen om dit opnieuw te bekijken.

{{#if:has_dpo_advice}}
## 7. Het advies van de functionaris voor gegevensbescherming

Artikel 35, lid 2, verplicht de verwerkingsverantwoordelijke het advies in te
winnen van de functionaris voor gegevensbescherming, wanneer die is aangewezen.

{{dpo_name}} werd geraadpleegd en adviseerde:

{{dpo_advice}}
{{/if:has_dpo_advice}}

{{#if:dpo_not_consulted}}
## 7. Het advies van de functionaris voor gegevensbescherming

Er is een functionaris voor gegevensbescherming aangewezen, en zijn of haar
advies werd voor deze beoordeling niet ingewonnen. Artikel 35, lid 2, vereist
dat wel.
{{/if:dpo_not_consulted}}

{{#if:dpo_unanswered}}
## 7. Het advies van de functionaris voor gegevensbescherming

Er is een functionaris voor gegevensbescherming aangewezen. Of zijn of haar
advies voor deze beoordeling werd ingewonnen, is niet vastgelegd — artikel 35,
lid 2, vereist dat het wordt ingewonnen, en dit document kan niet zeggen of dat
gebeurde.
{{/if:dpo_unanswered}}
