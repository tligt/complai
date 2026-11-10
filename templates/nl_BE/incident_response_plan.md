# Incidentresponsplan

*Conceptvertaling — nog niet nagekeken door een Belgische jurist.*

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**Van kracht vanaf {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}NIS2-classificatie: {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. Waarop dit betrekking heeft

Hoe wij merken dat er iets misloopt met onze systemen of onze gegevens, wat wij
daaraan doen en wie waarvoor verantwoordelijk is.

Het melden van een incident aan een autoriteit wordt afzonderlijk behandeld, in
onze procedure voor de melding van incidenten en inbreuken. Dit document gaat
over de afhandeling van het incident zelf.

## 2. Hoe wij het merken

{{nis2_detection_text}}

Iedereen in de organisatie kan een vermoedelijk incident melden via
{{contact_email}}. Niemand hoeft eerst te beoordelen of het ernstig is.

## 3. Wat wij doen

{{nis2_containment_text}}

Wij schakelen systemen niet uit, tenzij er geen alternatief is — dat vernietigt
sporen die nodig kunnen zijn om te begrijpen wat er gebeurde en om correct te
melden.

## 4. Wie wat doet

{{nis2_roles_text}}

{{#if:has_dpo_section}}
Wanneer persoonsgegevens betrokken zijn, wordt {{dpo_name}} ({{dpo_email}})
vanaf het begin betrokken in plaats van achteraf ingelicht.
{{/if:has_dpo_section}}

## 5. Systemen waarop het plan betrekking heeft

{{#ifnot:has_critical_systems}}
Er zijn geen systemen geregistreerd. Dit plan kan niet zeggen wat het
beschermt zolang dat niet gebeurd is.
{{/ifnot:has_critical_systems}}

{{#block:nis2_systems}}

Onze herstelobjectieven voor deze systemen — hoe snel elk systeem terug moet
zijn en hoeveel werk verloren mag gaan — staan in ons
bedrijfscontinuïteitsplan.

## 6. Ervan leren

Nadat een incident is afgesloten, leggen wij vast wat er gebeurde, wat wij
deden en wat wij daardoor hebben veranderd.

Wij testen dit plan in plaats van aan te nemen dat het werkt. **Een plan dat
nooit is getest, is een document, geen vermogen**, en de eerste keer dat u
ontdekt of een back-up zich laat terugzetten, mag niet de dag zijn waarop u die
nodig hebt.
