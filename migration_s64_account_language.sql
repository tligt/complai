-- S64 (D-167): the language RECOSA writes to an account in (contract and
-- billing). Null: the owner's interface language (profiles.ui_language).
-- A person's own language is profiles.ui_language: their interface and the
-- language we write to them in. Idempotent.
alter table public.accounts add column if not exists language text
    check (language is null or language in ('en', 'fr', 'nl', 'de'));
