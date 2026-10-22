-- S49: free checks to subscription funnel (D-115).
--
-- Three pieces:
--   1. leads         — an email given on the public quiz or website check,
--                      with what it was given for and the marketing consent.
--   2. funnel_events — counts for measurement, and the per-IP limit on free
--                      website checks.
--   3. profiles      — subscription_status / trial_ends_at / signup_source /
--                      pending_result, so a registered account sees its
--                      result and the trial gates the rest.
--
-- The public app holds only the anon key. Both tables have RLS on and NO
-- policies: the anon role cannot read or write them directly. All public
-- writes go through the SECURITY DEFINER functions below, which validate,
-- rate-limit and insert — and never return a row.
--
-- Idempotent: safe to run again.

-- ── 1. leads ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.leads (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tool                 text NOT NULL CHECK (tool IN ('nis2_quiz', 'website_check')),
    email                text NOT NULL,
    answers              text,        -- nis2_quiz: ten digits 0-3
    site_domain          text,        -- website_check: the checked site
    score                integer,
    marketing_consent    boolean NOT NULL DEFAULT false,
    consent_version      text,        -- wording shown when consent was given
    source               text,
    ip_address           text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    -- Set when the same email signs up. SET NULL, not CASCADE: deleting the
    -- account (S51) must not be blocked, and the lead row is purged on its
    -- own schedule below.
    converted_profile_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS leads_email_idx ON public.leads (lower(email));
CREATE INDEX IF NOT EXISTS leads_site_idx  ON public.leads (site_domain);
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;

-- ── 2. funnel_events ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.funnel_events (
    id          bigserial PRIMARY KEY,
    event       text NOT NULL,   -- quiz_completed, website_check_run, app_landing, signup, trial_started
    tool        text,
    source      text,
    ip_address  text,            -- website_check_run only; cleared after 7 days
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS funnel_events_ip_idx ON public.funnel_events (ip_address, created_at)
    WHERE ip_address IS NOT NULL;
ALTER TABLE public.funnel_events ENABLE ROW LEVEL SECURITY;

-- ── 3. profiles ───────────────────────────────────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS subscription_status text NOT NULL DEFAULT 'registered',
    ADD COLUMN IF NOT EXISTS trial_ends_at  timestamptz,
    ADD COLUMN IF NOT EXISTS signup_source  text,
    ADD COLUMN IF NOT EXISTS pending_result jsonb;

ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_subscription_status_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_subscription_status_check
    CHECK (subscription_status IN ('registered', 'trial', 'active', 'expired'));

-- Accounts that existed before S49 keep full access. Only rows created
-- before this migration are touched, and only once (they would otherwise
-- all have taken the new 'registered' default).
UPDATE public.profiles SET subscription_status = 'active'
 WHERE subscription_status = 'registered'
   AND created_at < '2026-10-22 13:50:00+00';

-- ── Functions ─────────────────────────────────────────────────────────────

-- Counts only. Called by the public app (quiz_completed) and the client app
-- (app_landing, signup, trial_started).
CREATE OR REPLACE FUNCTION public.record_funnel_event(
    p_event text, p_tool text DEFAULT NULL, p_source text DEFAULT NULL
) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    INSERT INTO funnel_events (event, tool, source)
    SELECT left(p_event, 40), left(p_tool, 40), left(p_source, 60)
     WHERE p_event IN ('quiz_completed', 'app_landing', 'signup', 'trial_started');
$$;

-- A free website check crawls a site, which costs real time even without an
-- email. At most 3 per IP per 24 h (S41's numbers). Unknown IP fails open,
-- as S41's check does. Returns whether this check may run, and records it.
CREATE OR REPLACE FUNCTION public.start_website_check(p_ip text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    UPDATE funnel_events SET ip_address = NULL
     WHERE ip_address IS NOT NULL AND created_at < now() - interval '7 days';

    IF p_ip IS NOT NULL AND (
        SELECT count(*) FROM funnel_events
         WHERE event = 'website_check_run' AND ip_address = p_ip
           AND created_at > now() - interval '24 hours') >= 3 THEN
        RETURN false;
    END IF;

    INSERT INTO funnel_events (event, tool, ip_address)
    VALUES ('website_check_run', 'website_check', left(p_ip, 64));
    RETURN true;
END;
$$;

-- Records a lead, after the checks that make the form safe to leave public.
-- Returns 'ok' or the reason it refused; the caller sends the result email
-- only on 'ok'.
--   invalid       — malformed input
--   domain        — website_check: email not at the checked site's domain (S43)
--   already_sent  — website_check: this site's report was already emailed (S43)
--   rate_limited  — same email and tool within 24 h, or 5 leads from this IP
--                   within 24 h: the form cannot be used to flood an inbox
CREATE OR REPLACE FUNCTION public.submit_lead(
    p_tool text, p_email text, p_answers text, p_site_domain text,
    p_score integer, p_marketing_consent boolean, p_consent_version text,
    p_source text, p_ip text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_email  text := lower(trim(p_email));
    v_domain text := split_part(lower(trim(p_email)), '@', 2);
    v_site   text := lower(trim(p_site_domain));
BEGIN
    -- Unconverted leads are kept 24 months (D-115). Purged here, lazily,
    -- rather than by a cron nobody would notice failing.
    DELETE FROM leads
     WHERE converted_profile_id IS NULL AND created_at < now() - interval '24 months';

    IF p_tool NOT IN ('nis2_quiz', 'website_check')
       OR v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' OR length(v_email) > 254 THEN
        RETURN 'invalid';
    END IF;
    IF p_tool = 'nis2_quiz' AND (p_answers IS NULL OR p_answers !~ '^[0-3]{10}$') THEN
        RETURN 'invalid';
    END IF;
    IF p_tool = 'website_check' THEN
        IF v_site IS NULL OR v_site = '' THEN
            RETURN 'invalid';
        END IF;
        IF NOT (v_domain = v_site OR v_domain LIKE '%.' || v_site
                OR v_site LIKE '%.' || v_domain) THEN
            RETURN 'domain';
        END IF;
        IF EXISTS (SELECT 1 FROM leads WHERE tool = 'website_check' AND site_domain = v_site) THEN
            RETURN 'already_sent';
        END IF;
    END IF;

    IF EXISTS (SELECT 1 FROM leads WHERE lower(email) = v_email AND tool = p_tool
                AND created_at > now() - interval '24 hours')
       OR (p_ip IS NOT NULL AND (SELECT count(*) FROM leads WHERE ip_address = p_ip
                AND created_at > now() - interval '24 hours') >= 5) THEN
        RETURN 'rate_limited';
    END IF;

    INSERT INTO leads (tool, email, answers, site_domain, score, marketing_consent,
                       consent_version, source, ip_address)
    VALUES (p_tool, v_email, p_answers, NULLIF(v_site, ''), p_score,
            coalesce(p_marketing_consent, false),
            CASE WHEN p_marketing_consent THEN left(p_consent_version, 40) END,
            left(p_source, 60), left(p_ip, 64));
    RETURN 'ok';
END;
$$;

REVOKE ALL ON FUNCTION public.record_funnel_event(text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.start_website_check(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.submit_lead(text, text, text, text, integer, boolean, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.record_funnel_event(text, text, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.start_website_check(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.submit_lead(text, text, text, text, integer, boolean, text, text, text) TO anon, authenticated;

-- Measurement (D-115): daily counts per step and tool, for the admin.
CREATE OR REPLACE VIEW public.funnel_daily
WITH (security_invoker = true) AS
SELECT date_trunc('day', created_at)::date AS day, event AS step, tool, source, count(*) AS n
  FROM funnel_events GROUP BY 1, 2, 3, 4
UNION ALL
SELECT date_trunc('day', created_at)::date, 'lead', tool, source, count(*)
  FROM leads GROUP BY 1, 2, 3, 4;
