-- Human-readable regulatory alert references: RA-YYYY-NNNN.
--
-- Assigned by the database the first time an update becomes 'approved',
-- so every approval path gets one, rejected/pending items never use a
-- number, and the numbers clients see have no gaps. The counter restarts
-- each year (year of approval). A reference, once assigned, never changes.
--
-- Idempotent: safe to run again.

ALTER TABLE public.regulatory_updates
    ADD COLUMN IF NOT EXISTS alert_ref text;

ALTER TABLE public.regulatory_updates
    DROP CONSTRAINT IF EXISTS regulatory_updates_alert_ref_key;
ALTER TABLE public.regulatory_updates
    ADD CONSTRAINT regulatory_updates_alert_ref_key UNIQUE (alert_ref);

-- One row per year. UPDATE ... RETURNING takes a row lock, so two
-- approvals at the same moment are serialised and cannot share a number.
CREATE TABLE IF NOT EXISTS public.alert_ref_counters (
    year      integer PRIMARY KEY,
    last_seq  integer NOT NULL DEFAULT 0
);
ALTER TABLE public.alert_ref_counters ENABLE ROW LEVEL SECURITY;
-- No policies: only the service role (and this trigger) touch it.

CREATE OR REPLACE FUNCTION public.next_alert_ref(p_year integer)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_seq integer;
BEGIN
    INSERT INTO alert_ref_counters (year, last_seq) VALUES (p_year, 0)
        ON CONFLICT (year) DO NOTHING;
    UPDATE alert_ref_counters SET last_seq = last_seq + 1
        WHERE year = p_year
        RETURNING last_seq INTO v_seq;
    RETURN 'RA-' || p_year || '-' || lpad(v_seq::text, 4, '0');
END;
$$;
REVOKE ALL ON FUNCTION public.next_alert_ref(integer) FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.assign_alert_ref()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NEW.status = 'approved' AND NEW.alert_ref IS NULL THEN
        NEW.alert_ref := next_alert_ref(
            extract(year FROM coalesce(NEW.approved_at, now()) AT TIME ZONE 'UTC')::integer
        );
    END IF;
    RETURN NEW;
END;
$$;

-- Backfill existing approved updates in approval order, per year,
-- before the trigger exists (so it cannot double-assign).
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT id, coalesce(approved_at, detected_at, now()) AS ts
        FROM public.regulatory_updates
        WHERE status = 'approved' AND alert_ref IS NULL
        ORDER BY coalesce(approved_at, detected_at, now()), id
    LOOP
        UPDATE public.regulatory_updates
            SET alert_ref = public.next_alert_ref(
                extract(year FROM r.ts AT TIME ZONE 'UTC')::integer)
            WHERE id = r.id;
    END LOOP;
END;
$$;

DROP TRIGGER IF EXISTS trg_assign_alert_ref ON public.regulatory_updates;
CREATE TRIGGER trg_assign_alert_ref
    BEFORE INSERT OR UPDATE OF status ON public.regulatory_updates
    FOR EACH ROW EXECUTE FUNCTION public.assign_alert_ref();
