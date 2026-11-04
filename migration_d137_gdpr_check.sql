-- D-137 (4 Nov 2026): the GDPR Quick Check, the public app's fourth free
-- check. Its lead rows carry tool 'gdpr_check' and the ten answers (digits
-- 0-3) in leads.answers.
-- Applied through the Supabase MCP server as d137_gdpr_check.
ALTER TABLE public.leads DROP CONSTRAINT leads_tool_check;
ALTER TABLE public.leads ADD CONSTRAINT leads_tool_check
    CHECK (tool IN ('nis2_quiz', 'website_check', 'ai_act_check', 'gdpr_check'));
