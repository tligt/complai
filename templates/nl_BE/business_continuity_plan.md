# Bedrijfscontinuïteitsplan

*Conceptvertaling — nog niet nagekeken door een Belgische jurist.*

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**Van kracht vanaf {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}NIS2-classificatie: {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. Waarop dit betrekking heeft

Hoe wij blijven werken wanneer een systeem waarvan wij afhangen niet
beschikbaar is, hoe snel elk systeem terug moet zijn en hoeveel werk wij ons
kunnen permitteren te verliezen.

De afhandeling van het incident dat de onderbreking veroorzaakte, wordt
behandeld in ons incidentresponsplan. Dit document gaat over het voortzetten
van de werking terwijl het incident aan de gang is.

## 2. Hoe wij blijven werken

{{nis2_continuity_text}}

## 3. Herstelobjectieven

Twee waarden per systeem. **Hoe lang het onbeschikbaar mag zijn** voordat het
terug moet zijn, en **hoeveel werk verloren mag gaan** — als de laatste back-up
een uur oud was, is een uur aan invoer verloren.

Een systeem kan snel hersteld zijn en toch veel gegevens verliezen: binnen
enkele minuten terug, maar met de gegevens van gisteren.

{{#block:nis2_recovery}}

{{#if:has_some_unset}}
### Systemen zonder objectieven

Voor sommige systemen hierboven is geen herstelobjectief vastgelegd. Dat
betekent niet dat ze onbelangrijk zijn, maar dat nog niemand heeft beslist hoe
lang wij zonder ze kunnen. Zolang die beslissing niet is genomen, gaat dit plan
voor die systemen geen enkele verbintenis aan.
{{/if:has_some_unset}}

{{#ifnot:has_recovery_objectives}}
**Voor geen enkel systeem is een herstelobjectief vastgelegd.** Zolang dat zo is,
beschrijft dit plan voornemens en geen verbintenissen.
{{/ifnot:has_recovery_objectives}}

## 4. Back-ups

Waar en hoe elk systeem wordt hersteld, staat bij dat systeem in de tabel
hierboven. Waar die kolom leeg is, hangt het herstel af van de regelingen van
de leverancier zelf, en die hebben wij niet nagegaan.

## 5. Testen

{{nis2_testing_text}}

**Een plan dat nooit is getest, is een document, geen vermogen.** De dag
waarop u een back-up nodig hebt, is niet het moment om te ontdekken of ze zich
laat terugzetten.

## 6. Wie beslist

Dit plan in werking stellen — verklaren dat wij in continuïteitsmodus werken, en
later dat wij naar de normale werking zijn teruggekeerd — is een beslissing, en
iemand moet ze nemen. Die verantwoordelijkheid ligt bij dezelfde personen die
een incident leiden, zoals vastgelegd in ons incidentresponsplan.
