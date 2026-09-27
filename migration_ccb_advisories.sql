-- CCB advisories feed, with cross-source duplicate filtering.
--
-- skip_if_covered: the monitor drops an item from this source when
-- another source already covers it (shared CVE, or same product names
-- within 14 days), and drops repeats within the source's own feed. For
-- title-only feeds like CCB's, whose articles are behind a bot wall:
-- the other source's copy has the full text. One-way: full-text sources
-- are never dropped in favour of a flagged one.
--
-- Idempotent: safe to run again.

ALTER TABLE public.monitoring_sources
    ADD COLUMN IF NOT EXISTS skip_if_covered boolean NOT NULL DEFAULT false;

INSERT INTO public.monitoring_sources
    (name, url, fetch_type, monitor_type, category, regulations, countries,
     filter_keywords, active, skip_if_covered)
SELECT 'CCB (Advisories)', 'https://ccb.belgium.be/advisories.xml', 'rss',
       'regulatory', 'Authority', ARRAY['NIS2'], ARRAY['BE'],
       ARRAY[]::text[], true, true
WHERE NOT EXISTS (
    SELECT 1 FROM public.monitoring_sources
    WHERE url = 'https://ccb.belgium.be/advisories.xml'
);
