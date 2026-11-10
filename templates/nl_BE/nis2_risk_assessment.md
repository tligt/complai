# Risicobeoordeling cyberbeveiliging

*Conceptvertaling — nog niet nagekeken door een Belgische jurist.*

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

## {{assessment_title}}

{{#if:has_policy_effective_date}}**Beoordeeld op {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

## 1. Waarom deze beoordeling bestaat

Artikel 21, lid 2, onder a), vereist beleid inzake risicoanalyse en beveiliging
van informatiesystemen. Dit is de analyse waarop dat beleid steunt.

{{#if:has_scope_note}}
{{assessment_scope}}
{{/if:has_scope_note}}

Ze gaat over het risico voor **de systemen en diensten waarvan wij afhangen**.
Het risico voor de personen van wie wij persoonsgegevens bewaren, is een andere
vraag, die afzonderlijk wordt beoordeeld volgens artikel 35 AVG — sommige
situaties komen in beide voor, met verschillende gevolgen.

## 2. Wat erbinnen valt

{{#ifnot:has_systems_table}}
Er zijn geen systemen aan deze beoordeling gekoppeld.
{{/ifnot:has_systems_table}}

{{#block:nis2ra_systems}}

De herstelobjectieven voor deze systemen staan in ons
bedrijfscontinuïteitsplan.

## 3. De risico's

Elk risico wordt geregistreerd met hoe waarschijnlijk het is en hoe ernstig het
zou zijn, vóór en na de maatregelen die wij nemen.

Beide worden afzonderlijk gehouden in plaats van tot één score te worden
samengevoegd. Een risico dat zelden voorkomt maar rampzalig is, en een risico
dat voortdurend voorkomt maar onbeduidend is, kunnen dezelfde score hebben en
toch een totaal andere aanpak vereisen.

{{#ifnot:has_risks}}
Er zijn geen risico's geregistreerd. Deze beoordeling is onvolledig.
{{/ifnot:has_risks}}

{{#block:dpia_risks}}

## 4. Of de maatregelen passend zijn

Artikel 21, lid 1, vereist maatregelen die passend zijn voor het risico,
rekening houdend met onze blootstelling, onze omvang en de waarschijnlijkheid
dat zich incidenten voordoen.

Dit document legt de risico's vast en wat wij eraan doen. Of dat passend is, is
een oordeel, en dat oordeel is aan ons — het herzien ervan is precies de reden
om deze beoordeling te herhalen in plaats van ze te archiveren.

## 5. Aanvaarden wat overblijft

{{#if:has_unaccepted}}
**Sommige hoge restrisico's zijn door niemand aanvaard.**

Artikel 20, lid 1, laat het bestuursorgaan de
cyberbeveiligingsmaatregelen goedkeuren en toezien op de uitvoering ervan. Een
hoog risico dat in het register staat zonder iemands naam erbij, is geen
aanvaard risico — het is een beslissing die niemand heeft genomen.
{{/if:has_unaccepted}}

{{#if:has_unassessed}}
**Sommige risico's hierboven zijn na de maatregelen niet beoordeeld.** Zolang
dat niet gebeurd is, kan niet worden besloten of wat overblijft aanvaardbaar
is.
{{/if:has_unassessed}}

## 6. Actueel houden

Een nieuw systeem, een andere leverancier, een significant incident of een
wezenlijke verandering in wat wij doen, zijn telkens redenen om dit opnieuw te
bekijken. Een beoordeling die de systemen van vorig jaar beschrijft, beschermt
niets.
