-- S48: keep every website scan, with its date and findings.
--
-- A scan is a record of what was observed on a given day ("scanned
-- 30 Sept 2026: Microsoft 365 email, Meta Pixel via Tag Manager"), so rows
-- are append-only for users: SELECT and INSERT policies, no UPDATE or
-- DELETE. They go when the client goes (ON DELETE CASCADE), which is also
-- what S40's account deletion relies on.
--
-- Same access rule as the other client tables (systems, activities):
-- has_client_access(client_id, user_id), so workspace members (S38) see
-- and create scans for the clients they can access.
--
-- Idempotent: safe to run again.

CREATE TABLE IF NOT EXISTS public.website_scans (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    -- CASCADE like systems/activities/client_documents: deleting an account
    -- must never be blocked by rows it created (S40).
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    website         text NOT NULL,
    domain          text NOT NULL,
    scanned_at      timestamptz NOT NULL DEFAULT now(),
    -- [{catalogue_key, name, confidence, evidence: [..]}]
    detected        jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- [{host, how}]
    other_services  jsonb NOT NULL DEFAULT '[]'::jsonb,
    errors          jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS website_scans_client_scanned_idx
    ON public.website_scans (client_id, scanned_at DESC);

ALTER TABLE public.website_scans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS website_scans_select ON public.website_scans;
CREATE POLICY website_scans_select ON public.website_scans
    FOR SELECT USING (has_client_access(client_id, user_id));

DROP POLICY IF EXISTS website_scans_insert ON public.website_scans;
CREATE POLICY website_scans_insert ON public.website_scans
    FOR INSERT WITH CHECK (has_client_access(client_id, user_id) AND user_id = auth.uid());
