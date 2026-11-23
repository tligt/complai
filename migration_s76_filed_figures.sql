-- S76 — a Belgian company's size from its filed annual accounts (23 Nov 2026)
--
-- clients.filed_figures: what nbb_accounts.py read from the National Bank's
-- Authentic Data service for the latest filing — average FTE, turnover,
-- financial year end, filing reference and date, model, when checked.
-- A fact with its source, shown next to the size the company declared.
--
-- Run once (psql -1, ON_ERROR_STOP), then NOTIFY pgrst, 'reload schema'.

ALTER TABLE clients ADD COLUMN IF NOT EXISTS filed_figures jsonb;
