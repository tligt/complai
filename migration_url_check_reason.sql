-- D-174, 13 Nov: production was missing url_check_reason on
-- regulatory_updates, so every URL-flagged item failed to save
-- ("Could not find the 'url_check_reason' column of 'regulatory_updates'
-- in the schema cache", PGRST204) — a schema drift from the 12 Nov
-- reference-data copy (migrate_reference.sh dumps schema once; it was
-- added to regulatory_updates in dev sometime after that). marketing_updates
-- already had it, predating the copy. Applied directly on production via
-- psql on 13 Nov; kept here for the record and for dev, idempotent either way.

alter table public.regulatory_updates add column if not exists url_check_reason text;
alter table public.marketing_updates add column if not exists url_check_reason text;
