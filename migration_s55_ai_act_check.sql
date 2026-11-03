-- S55 (D-132, 3 Nov 2026): the AI Act Quick Check, the public app's third
-- free check. Its lead rows carry tool 'ai_act_check' and the eight answers
-- (digits 0-3) in leads.answers. record_funnel_event takes any tool name
-- already; only the leads constraint needs widening.
-- Applied through the Supabase MCP server as s55_ai_act_check.
ALTER TABLE public.leads DROP CONSTRAINT leads_tool_check;
ALTER TABLE public.leads ADD CONSTRAINT leads_tool_check
    CHECK (tool IN ('nis2_quiz', 'website_check', 'ai_act_check'));
