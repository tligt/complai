-- D-180, 16 Nov 2026: UTM tags on funnel events.
-- The website, the free check and the app already record where a visitor
-- came from as `source` (our own ?src= values). External links (LinkedIn,
-- email, partners) now carry standard utm_* tags as well; they are kept
-- alongside, as one small JSON object, so the back office can tell which
-- campaign led to a check, a sign-up or a trial.
--
-- The function is dropped and recreated rather than overloaded: two
-- versions with the same first three named arguments would make
-- PostgREST's call ambiguous. p_utm defaults to NULL, so callers that
-- don't pass it keep working unchanged.

ALTER TABLE funnel_events ADD COLUMN IF NOT EXISTS utm jsonb;

DROP FUNCTION IF EXISTS public.record_funnel_event(text, text, text);

CREATE OR REPLACE FUNCTION public.record_funnel_event(
    p_event text, p_tool text DEFAULT NULL, p_source text DEFAULT NULL,
    p_utm jsonb DEFAULT NULL)
 RETURNS void
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    INSERT INTO funnel_events (event, tool, source, utm)
    SELECT left(p_event, 40), left(p_tool, 40), left(p_source, 60),
           -- Only the five standard keys, only strings, each cut to 80
           -- characters: the values come from a visitor-controlled URL.
           (SELECT nullif(jsonb_object_agg(key, left(value #>> '{}', 80)), '{}'::jsonb)
              FROM jsonb_each(CASE WHEN jsonb_typeof(p_utm) = 'object' THEN p_utm ELSE '{}'::jsonb END)
             WHERE key IN ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')
               AND jsonb_typeof(value) = 'string')
     WHERE p_event IN ('quiz_completed', 'app_landing', 'signup', 'trial_started',
                       'check_landing', 'scope_completed');
$function$;

REVOKE ALL ON FUNCTION public.record_funnel_event(text, text, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.record_funnel_event(text, text, text, jsonb) TO anon, authenticated, service_role;
