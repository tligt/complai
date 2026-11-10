-- S64 (D-163): what is done, per country, for RECOSA to serve it.
--
-- The ten items of the localization scope note (3b). One row per country and
-- item, edited in the back office (pages_admin/countries.py). Admin only: it is
-- RECOSA's own work plan, not client data.
--
-- Statuses as assessed on 10 Nov 2026 from the sprint log. "todo" where
-- nothing has been done or nothing is known; the note says which.
-- Idempotent: re-running keeps any status edited since (ON CONFLICT DO NOTHING).

create table if not exists public.country_checklists (
    country     text not null check (country ~ '^[A-Z]{2}$'),
    item        text not null check (item in ('languages', 'regulators', 'law', 'breach',
                    'sources', 'company_data', 'templates', 'interface', 'commercial', 'support')),
    status      text not null default 'todo' check (status in ('done', 'partial', 'todo', 'n_a')),
    note        text check (note is null or char_length(note) <= 2000),
    updated_by  uuid references auth.users (id) on delete set null,
    updated_at  timestamptz not null default now(),
    primary key (country, item)
);
alter table public.country_checklists enable row level security;
drop policy if exists country_checklists_admin on public.country_checklists;
create policy country_checklists_admin on public.country_checklists for all
    using (is_admin_user()) with check (is_admin_user());

insert into public.country_checklists (country, item, status, note) values
 ('BE', 'languages', 'partial', 'Documents: fr-BE and en; nl-BE templates drafted 10 Nov (not reviewed by a lawyer); no de-BE. Interface English only.'),
 ('BE', 'regulators', 'partial', 'GDPR authority (APD/GBA) and CSIRT (CCB) with reporting channels, checked 22 Oct (D-83). AI Act market-surveillance and notifying authorities not recorded.'),
 ('BE', 'law', 'partial', 'NIS2 and GDPR in the obligation catalogue at EU level. Belgian NIS2 law, registration duty and national retention periods not recorded per country.'),
 ('BE', 'breach', 'done', 'APD/GBA breach portal and CCB notification channel verified (S53, D-117/D-118).'),
 ('BE', 'sources', 'partial', 'APD/GBA news monitored (S49). Belgian Official Journal and CCB advisories not monitored.'),
 ('BE', 'company_data', 'done', 'CBE/KBO lookup at company setup (S48, D-156).'),
 ('BE', 'templates', 'partial', 'All 14 templates in fr and en, drafts for legal review; none reviewed by a Belgian lawyer. nl-BE drafts 10 Nov; Dutch DPA waits for the official SCC text.'),
 ('BE', 'interface', 'todo', 'Interface, free check and emails in English (some French). No translation layer yet.'),
 ('BE', 'commercial', 'todo', 'Not assessed here: currency, VAT, prices and RECOSA''s own terms per country.'),
 ('BE', 'support', 'todo', 'Not assessed here: languages support is offered in.'),
 ('FR', 'languages', 'partial', 'Documents: fr-FR (one French text for BE and FR, D-163) and en. Interface English only.'),
 ('FR', 'regulators', 'partial', 'CNIL and CERT-FR/ANSSI channels, CNIL checked 26 Oct (S53). AI Act authorities not recorded.'),
 ('FR', 'law', 'partial', 'EU-level obligations only. French NIS2 transposition, registration duty and national retention periods not recorded.'),
 ('FR', 'breach', 'done', 'CNIL notification channel verified 26 Oct (S53).'),
 ('FR', 'sources', 'partial', 'ENISA monitored; CNIL news and the Journal officiel not monitored.'),
 ('FR', 'company_data', 'done', 'SIRENE lookup finished (D-156).'),
 ('FR', 'templates', 'partial', 'All 14 templates in fr and en, drafts for legal review; none reviewed by a French lawyer.'),
 ('FR', 'interface', 'todo', 'Interface, free check and emails in English (some French). No translation layer yet.'),
 ('FR', 'commercial', 'todo', 'Not assessed here.'),
 ('FR', 'support', 'todo', 'Not assessed here.'),
 ('NL', 'languages', 'todo', 'nl-NL: no text. The nl-BE templates do not serve Dutch companies (D-163).'),
 ('NL', 'regulators', 'todo', 'Autoriteit Persoonsgegevens, NCSC-NL / sector CSIRTs, RDI (AI Act) not recorded; no NL jurisdiction row.'),
 ('NL', 'law', 'todo', 'UAVG, Cyberbeveiligingswet (NIS2), retention periods not recorded.'),
 ('NL', 'breach', 'todo', 'AP meldloket and NCSC channel not recorded.'),
 ('NL', 'sources', 'todo', 'Not monitored.'),
 ('NL', 'company_data', 'partial', 'Lookup by VAT number (VIES), D-156. KvK lookup not built.'),
 ('NL', 'templates', 'todo', 'No nl-NL templates.'),
 ('NL', 'interface', 'todo', 'No Dutch interface.'),
 ('NL', 'commercial', 'todo', 'Not assessed.'),
 ('NL', 'support', 'todo', 'Not assessed.'),
 ('LU', 'languages', 'todo', 'Business documents mostly fr or de: fr-LU and de-LU have no text yet (the French text is valid for BE and FR only).'),
 ('LU', 'regulators', 'todo', 'CNPD, ILR / GOVCERT.LU, AI Act authorities not recorded; no LU jurisdiction row.'),
 ('LU', 'law', 'todo', 'Luxembourg GDPR law and NIS2 transposition not recorded.'),
 ('LU', 'breach', 'todo', 'CNPD notification channel not recorded.'),
 ('LU', 'sources', 'todo', 'Not monitored.'),
 ('LU', 'company_data', 'partial', 'Lookup by VAT number (VIES), D-156. RCS/LBR lookup not built.'),
 ('LU', 'templates', 'todo', 'No fr-LU or de-LU templates.'),
 ('LU', 'interface', 'todo', 'No French or German interface.'),
 ('LU', 'commercial', 'todo', 'Not assessed.'),
 ('LU', 'support', 'todo', 'Not assessed.')
on conflict do nothing;
