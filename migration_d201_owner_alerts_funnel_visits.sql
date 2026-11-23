-- D-201 — owner alerts and free-check funnel counted per visit (23 Nov 2026)
--
-- 1. funnel_events.visit: an anonymous id per free-check visit (a random
--    value the page keeps in its own address, no cookie), so the funnel can
--    count visitors, not just events. Older rows have none.
-- 2. record_funnel_event takes it, and two event names it silently dropped
--    until now: results_viewed (new: the free check's last page reached) and
--    invite_redeemed (D-200, recorded by the app but refused here).
-- 3. owner_alerts: what owner_alerts.py has already emailed about, so each
--    finished check, new account or paying client is announced once.
--
-- Run once (psql -1, ON_ERROR_STOP), then NOTIFY pgrst, 'reload schema'.

ALTER TABLE funnel_events ADD COLUMN IF NOT EXISTS visit text;
CREATE INDEX IF NOT EXISTS funnel_events_created_idx ON funnel_events (created_at);

-- The old four-argument version would stay as an overload; drop it so there
-- is one function, which PostgREST then picks by the named arguments.
DROP FUNCTION IF EXISTS public.record_funnel_event(text, text, text, jsonb);

CREATE OR REPLACE FUNCTION public.record_funnel_event(
    p_event text, p_tool text DEFAULT NULL, p_source text DEFAULT NULL,
    p_utm jsonb DEFAULT NULL, p_visit text DEFAULT NULL)
 RETURNS void
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    INSERT INTO funnel_events (event, tool, source, utm, visit)
    SELECT left(p_event, 40), left(p_tool, 40), left(p_source, 60),
           (SELECT nullif(jsonb_object_agg(key, left(value #>> '{}', 80)), '{}'::jsonb)
              FROM jsonb_each(CASE WHEN jsonb_typeof(p_utm) = 'object' THEN p_utm ELSE '{}'::jsonb END)
             WHERE key IN ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')
               AND jsonb_typeof(value) = 'string'),
           CASE WHEN p_visit ~ '^[A-Za-z0-9_-]{8,32}$' THEN p_visit END
     WHERE p_event IN ('quiz_completed', 'app_landing', 'signup', 'trial_started',
                       'check_landing', 'scope_completed', 'results_viewed', 'invite_redeemed');
$function$;

REVOKE ALL ON FUNCTION public.record_funnel_event(text, text, text, jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.record_funnel_event(text, text, text, jsonb, text)
    TO anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS owner_alerts (
    key      text PRIMARY KEY,           -- e.g. 'check:1234', 'account:<uuid>', 'paid:<period uuid>'
    sent_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE owner_alerts ENABLE ROW LEVEL SECURITY;   -- service role only; no policies
