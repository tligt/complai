-- D-129 (28 Oct 2026): two more funnel events from the public free check —
-- check_landing (a visit, with the deep link's check and src) and
-- scope_completed (the four "which rules apply" answers given).
-- Applied through the Supabase MCP server as d129_free_check_events.
CREATE OR REPLACE FUNCTION public.record_funnel_event(p_event text, p_tool text DEFAULT NULL::text, p_source text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    INSERT INTO funnel_events (event, tool, source)
    SELECT left(p_event, 40), left(p_tool, 40), left(p_source, 60)
     WHERE p_event IN ('quiz_completed', 'app_landing', 'signup', 'trial_started',
                       'check_landing', 'scope_completed');
$function$;
