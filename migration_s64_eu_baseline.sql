-- S64 (D-171): the EU baseline on the Countries page.
--
-- English documents carry the locale "en" with no country: one text valid for
-- every country (template_store.document_locale). Rather than an "en-EU"
-- locale, which would only fit companies set to "EU", the baseline is a
-- country_checklists row "EU": what every country falls back to. Each country
-- row is what is added on top. Applied 11 Nov; kept here for the record.

insert into public.country_checklists (country, item, status, note) values
 ('EU','languages','done','The baseline every country falls back to: English documents (locale "en", valid for every country) and the English interface.'),
 ('EU','regulators','done','EU bodies known and monitored: EDPB, ENISA, CERT-EU, EU AI Office. Notification channels are national (see each country).'),
 ('EU','law','done','GDPR, NIS2 Directive, AI Act and ePrivacy Directive in the obligation catalogue at EU level, with the AI Act''s staged application dates. National acts are per country.'),
 ('EU','breach','n_a','No EU-level channel: breaches and incidents are always notified to a national authority or CSIRT.'),
 ('EU','sources','partial','EDPB, ENISA, CERT-EU and EU AI Office feeds deliver. Euractiv and Politico configured, nothing saved yet. EUR-Lex / Official Journal not monitored.'),
 ('EU','company_data','done','Lookup by VAT number in the EU register (VIES) for the 25 member states without their own lookup (D-156); BE and FR use their national registers.'),
 ('EU','templates','partial','All 14 templates in English, drafts for legal review; none reviewed by a lawyer.'),
 ('EU','interface','done','English is the source language of every screen and email.'),
 ('EU','commercial','todo','Not assessed.'),
 ('EU','support','todo','Not assessed.')
on conflict (country, item) do update set status = excluded.status, note = excluded.note, updated_at = now();

-- The source notes of 10 Nov were wrong: CNIL and the CCB feeds are monitored.
update public.country_checklists set note = 'APD/GBA and CCB news monitored. CCB advisories feed configured, nothing saved from it yet. Belgian Official Journal not monitored.', updated_at = now()
 where country = 'BE' and item = 'sources';
update public.country_checklists set note = 'CNIL news monitored (with ENISA and the EU sources). Journal officiel and CERT-FR not monitored.', updated_at = now()
 where country = 'FR' and item = 'sources';
