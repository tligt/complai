-- D-208, 25 Nov: an English title for regulatory updates whose source is in
-- French or Dutch. The summary and "what to do" were already English; the
-- title was the source's own, so emails, the client app, LinkedIn (post and
-- image) and the Pulse mixed two languages. "title" keeps the original;
-- "title_en" is shown everywhere outside the admin review. NULL for English
-- sources. Later FR and NL versions of the Pulse add title_fr / title_nl
-- (and summaries) the same way. Idempotent; run on dev and production, then
-- backfill_title_en.py for the rows already there.

alter table public.regulatory_updates add column if not exists title_en text;

notify pgrst, 'reload schema';
