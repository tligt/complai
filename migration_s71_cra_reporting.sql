-- S71 (D-189), 18 Nov 2026: CRA Art. 14 reporting on the incident clock.
--
-- Since 11 Sept 2026 (CRA Art. 71(2)) a manufacturer of products with digital
-- elements reports actively exploited vulnerabilities and severe incidents
-- through ENISA's Single Reporting Platform: early warning 24 h, notification
-- 72 h, final report 14 days after a fix (vulnerability) or one month after
-- the notification (incident). One more track on the S53 clock.

-- ── Is the company a manufacturer? (NULL = not answered, as nis2_in_scope) ─
ALTER TABLE clients ADD COLUMN IF NOT EXISTS cra_manufacturer boolean;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS cra_scope_note text;

-- ── The CRA assessment of an incident ─────────────────────────────────────
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS cra_type text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS cra_product text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS cra_member_states text;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS cra_fix_available_at timestamptz;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS cra_intermediate_due timestamptz;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'incidents_cra_type_check') THEN
        ALTER TABLE incidents ADD CONSTRAINT incidents_cra_type_check
            CHECK (cra_type IS NULL OR cra_type IN ('vulnerability', 'severe_incident', 'none'));
    END IF;
END $$;
