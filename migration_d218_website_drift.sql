-- D-218 — the website-drift crawl (26 Nov 2026), S67 follow-up.
--
-- client_documents.published_url: where the client publishes this version
--   (privacy and cookie policies), asked when it is put in force. The nightly
--   crawl reads it first; left empty, it looks for the policy on the website.
-- clients.website_drift: what the crawl last saw — per document type, the
--   state (matches, older, differs, not_found, unreadable), the page, the
--   version shown and the score. heartbeat.py turns it into findings, on the
--   action plan and in the nightly job alike.
--
-- Run once (psql -1, ON_ERROR_STOP), then NOTIFY pgrst, 'reload schema'.

ALTER TABLE client_documents ADD COLUMN IF NOT EXISTS published_url text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS website_drift jsonb;
