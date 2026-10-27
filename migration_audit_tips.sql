-- Usability audit batch 3 (27 Oct 2026): which page tips a user has closed,
-- so "What is this page for?" panels stay closed across sessions.
-- Additive, idempotent. profiles RLS already lets a user update their own row.
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS dismissed_tips text[] NOT NULL DEFAULT '{}';
