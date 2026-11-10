# Procedure voor de melding van incidenten en inbreuken

*Conceptvertaling — nog niet nagekeken door een Belgische jurist.*

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

{{#if:has_policy_effective_date}}**Van kracht vanaf {{policy_effective_date}}.**{{/if:has_policy_effective_date}}

{{#if:has_nis2_class}}NIS2-classificatie: {{nis2_entity_class_label}}.{{/if:has_nis2_class}}

## 1. Het eerste uur

Doe dit in deze volgorde. Wacht niet tot iemand beslist of het gemeld moet
worden — dat komt daarna, en het verandert niets aan wat volgt.

1. **Beperk de schade.** Koppel los wat losgekoppeld moet worden. Schakel
   systemen zo mogelijk niet uit: dat vernietigt sporen die u nodig kunt
   hebben.
2. **Noteer het tijdstip** waarop u het ontdekte, en wat u zag. Alles wat volgt,
   wordt vanaf dat moment gerekend.
3. **Waarschuw het incidentteam**, te beginnen met wie de incidenten leidt.
   Registreer het incident in RECOSA: het waarschuwt het team hieronder en
   start de klokken.
   {{nis2_roles_text}}
4. **Verwijder niets**, ook niet wat het incident veroorzaakte.
5. **Licht klanten of het publiek nog niet in.** Die beslissing hoort bij de
   beoordeling hieronder.

**Het incidentteam**

{{#block:incident_team}}

## 2. Moet het gemeld worden?

Twee afzonderlijke regelingen kunnen van toepassing zijn, en ze stellen
verschillende vragen.

**Zijn persoonsgegevens betrokken?** Als persoonsgegevens verloren zijn gegaan,
zijn blootgesteld, gewijzigd of — al was het tijdelijk — onbeschikbaar werden,
is er sprake van een inbreuk in verband met persoonsgegevens. Registreer ze,
wat er ook volgt. Beoordeel vervolgens het risico voor de betrokkenen en leg
vast waarom:

- **waarschijnlijk geen risico** — niet gemeld; de reden wordt vastgelegd;
- **een risico** — meld het aan de toezichthoudende autoriteit. Termijn: 72 uur
  nadat u er kennis van kreeg;
- **een hoog risico** — licht ook de betrokkenen in, zonder onredelijke
  vertraging, tenzij de gegevens onbegrijpelijk waren voor iedereen die niet
  gemachtigd is (bijvoorbeeld versleuteld), sindsdien genomen maatregelen het
  hoge risico onwaarschijnlijk maken, of het contacteren van elke persoon een
  onevenredige inspanning zou vergen — dan volstaat een openbare mededeling.

Verwerkt u de gegevens voor een klant, licht die klant dan zonder onredelijke
vertraging in{{#if:has_breach_notice_hours}} — binnen {{breach_notice_hours}} uur, zoals
uw overeenkomsten beloven{{/if:has_breach_notice_hours}} — ongeacht het risico.

{{#if:has_both_regimes}}
**Is het een significant incident?** NIS2 is van toepassing wanneer een
incident de diensten die u verleent ernstig verstoort, of aanzienlijke
operationele of financiële schade veroorzaakt. Termijn: **24 uur** nadat u er
kennis van kreeg. Wanneer het waarschijnlijk gevolgen heeft voor de afnemers van
uw diensten, licht u ook hen in.

**Beide kunnen tegelijk van toepassing zijn.** Ransomware op een systeem met
persoonsgegevens is het voor de hand liggende voorbeeld. Wanneer beide van
toepassing zijn, werkt u naar de termijn van 24 uur — wie die haalt, heeft ook
tijd genoeg voor de andere.
{{/if:has_both_regimes}}

Twijfelt u, behandel het dan als meldingsplichtig en vermeld die twijfel in de
melding. Een melding die achteraf overbodig blijkt, kost een e-mail. Een gemiste
melding niet.

## 3. Meldingstermijnen

{{#block:nis2_timeline}}

**Wie contacteren**

- Toezichthoudende autoriteit: {{authority_name}}{{#if:has_authority_url}} — {{authority_url}}{{/if:has_authority_url}}
- Nationaal CSIRT: {{csirt_name}}{{#if:has_csirt_url}} — {{csirt_url}}{{/if:has_csirt_url}}
{{#if:has_dpo_section}}- Functionaris voor gegevensbescherming: {{dpo_name}} — {{dpo_email}}{{/if:has_dpo_section}}

U hebt geen volledige informatie nodig om te melden. Stuur binnen de termijn wat
u hebt en vul later aan — dat is wat de wet verwacht, en een volledige melding
die te laat komt, is erger dan een vroege onvolledige. Een AVG-melding die na
72 uur wordt verstuurd, moet de redenen voor de vertraging vermelden. Het CSIRT
kan om een tussentijds verslag vragen; als het incident nog wordt afgehandeld
wanneer het eindverslag verschuldigd is, stuurt u dan een voortgangsverslag, en
het eindverslag binnen een maand na het einde van de afhandeling.

Elke melding wordt verstuurd door het teamlid dat ze behandelt — via het
portaal van de autoriteit zelf, of vanuit uw eigen mailbox voor uw klanten en
gebruikers — en in RECOSA geregistreerd met de verstuurde tekst en de ontvangen
referentie.

## 4. Een incident intern melden

Wie iets verkeerds opmerkt, meldt het aan {{contact_email}} zonder eerst te
beoordelen of het ernstig is. Het belang inschatten is niet de taak van wie het
opmerkte, en een organisatie waar het personeel eerst beoordeelt en dan meldt,
komt het te laat te weten.

Meld een verloren of gestolen toestel, een e-mail die u beantwoordde en beter
niet had beantwoord, een bestand dat met de verkeerde persoon werd gedeeld, een
systeem dat zich vreemd gedraagt, een leverancier die u laat weten dat hij een
incident heeft gehad.

## 5. Na de afsluiting

Leg vast wat er gebeurde, wat er werd gedaan en wat er daardoor is veranderd.
Werd het incident gemeld, dan is het eindverslag binnen een maand verschuldigd.
RECOSA bewaart het incidentdossier: de feiten, elke beslissing met haar reden,
elke verstuurde melding met haar referentie, en wie wanneer werd gewaarschuwd.

Een incident evalueren is geen vrijblijvend papierwerk — het is het enige deel
van deze procedure dat de kans op het volgende incident verkleint.
