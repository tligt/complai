-- S64 (D-163): the locales each template version is valid for.
--
-- A document's locale is its language plus the company's country (nl + BE =
-- nl-BE). A version is used only for the locales it lists: generation never
-- borrows a Belgian text for a Dutch company. 'en' is valid for any country.
-- Idempotent.
alter table public.document_template_versions add column if not exists locales text[];
update public.document_template_versions set locales = '{en}' where language = 'en' and locales is null;
update public.document_template_versions set locales = '{fr-BE,fr-FR}' where language = 'fr' and locales is null;
update public.document_template_versions set locales = '{nl-BE}' where language = 'nl' and locales is null;
update public.document_template_versions set locales = '{de-BE}' where language = 'de' and locales is null;
