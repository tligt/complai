-- S53 part 2 (D-118): incident team, documented flow, legal gaps.
--
--   incident_contacts — the client's incident team: who is alerted, for
--                       which incidents, and any contractual deadline.
--   incidents         — the GDPR risk test, Art. 34(3) exemption, categories
--                       of data subjects, NIS2 recipients-of-service, the
--                       CSIRT's intermediate-report request.
--   incident_events   — new types: alert (who was told), followup
--                       (supplementary information), request (an authority
--                       asked for something).
--   clients           — breach_notice_hours: what the client's own DPAs
--                       promise its clients (Art. 33(2) "without undue
--                       delay" made concrete by contract).
--
-- Idempotent: safe to run again.

CREATE TABLE IF NOT EXISTS public.incident_contacts (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id    uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    user_id      uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name         text NOT NULL,
    role         text NOT NULL DEFAULT 'other'
                 CHECK (role IN ('lead', 'deputy', 'it', 'external_it', 'dpo', 'management',
                                 'legal', 'communications', 'insurer', 'other')),
    email        text,
    phone        text,
    alert_on     text NOT NULL DEFAULT 'all'
                 CHECK (alert_on IN ('all', 'personal_data', 'significant', 'never')),
    deadline_hours integer CHECK (deadline_hours IS NULL OR deadline_hours > 0),
    notes        text,
    sort_order   integer NOT NULL DEFAULT 100,
    active       boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS incident_contacts_client_idx ON public.incident_contacts (client_id);
ALTER TABLE public.incident_contacts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS incident_contacts_select ON public.incident_contacts;
CREATE POLICY incident_contacts_select ON public.incident_contacts FOR SELECT
    USING (has_client_access(client_id, NULL) OR is_admin_user());
DROP POLICY IF EXISTS incident_contacts_insert ON public.incident_contacts;
CREATE POLICY incident_contacts_insert ON public.incident_contacts FOR INSERT
    WITH CHECK (has_client_access(client_id, NULL) AND user_id = auth.uid());
DROP POLICY IF EXISTS incident_contacts_update ON public.incident_contacts;
CREATE POLICY incident_contacts_update ON public.incident_contacts FOR UPDATE
    USING (has_client_access(client_id, NULL))
    WITH CHECK (has_client_access(client_id, NULL));
-- No DELETE: a contact is deactivated, so past alerts still name them.

ALTER TABLE public.incidents
    ADD COLUMN IF NOT EXISTS gdpr_risk text
        CHECK (gdpr_risk IS NULL OR gdpr_risk IN ('none', 'risk', 'high')),
    ADD COLUMN IF NOT EXISTS subjects_exemption text
        CHECK (subjects_exemption IS NULL OR subjects_exemption IN ('encrypted', 'measures', 'public')),
    ADD COLUMN IF NOT EXISTS subject_categories text,
    ADD COLUMN IF NOT EXISTS affects_recipients boolean,
    ADD COLUMN IF NOT EXISTS intermediate_due timestamptz;

-- high_risk (part 1) becomes gdpr_risk = 'high'. Nothing real was recorded
-- in part 1's single day, but the mapping keeps any row honest.
UPDATE public.incidents SET gdpr_risk = 'high'
 WHERE high_risk IS TRUE AND gdpr_risk IS NULL;

ALTER TABLE public.incident_events DROP CONSTRAINT IF EXISTS incident_events_event_type_check;
ALTER TABLE public.incident_events ADD CONSTRAINT incident_events_event_type_check
    CHECK (event_type IN ('decision', 'notification', 'status', 'note', 'reminder',
                          'alert', 'followup', 'request'));

ALTER TABLE public.clients
    ADD COLUMN IF NOT EXISTS breach_notice_hours integer
        CHECK (breach_notice_hours IS NULL OR breach_notice_hours > 0);
