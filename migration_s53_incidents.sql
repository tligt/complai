-- S53: breach notification workflow (D-117).
--
--   incidents        — one row per incident, per client. The clock starts at
--                      discovered_at. Updatable (the assessment fills in as
--                      it is learned) but never deleted by users: GDPR
--                      Art. 33(5) requires documenting every breach.
--   incident_events  — what happened to it, append-only: decisions with
--                      their reasons, notifications sent (which stop a
--                      clock), status changes, reminders sent.
--
-- Same access rule as the other client tables: has_client_access(client_id,
-- user_id), so workspace members (S38) see and log incidents too. Rows go
-- with the client (CASCADE), which is what S51's account deletion relies on.
--
-- Also: the reporting channels checked on the authorities' own sites on
-- 22 Oct 2026, merged into the jurisdiction metadata (D-83's CSIRT fields).
--
-- Idempotent: safe to run again.

CREATE TABLE IF NOT EXISTS public.incidents (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id            uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    user_id              uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title                text NOT NULL,
    description          text,
    discovered_at        timestamptz NOT NULL,
    reported_by          text,
    system_ids           uuid[] NOT NULL DEFAULT '{}',
    status               text NOT NULL DEFAULT 'open'
                         CHECK (status IN ('open', 'contained', 'closed')),
    -- The assessment. NULL = not assessed yet, which is not the same as no.
    personal_data        boolean,
    data_categories      text,
    approx_subjects      integer CHECK (approx_subjects IS NULL OR approx_subjects >= 0),
    approx_records       integer CHECK (approx_records IS NULL OR approx_records >= 0),
    significant          boolean,      -- NIS2 "significant incident"
    high_risk            boolean,      -- GDPR Art. 34: tell the people affected
    likely_consequences  text,
    measures_taken       text,
    -- The closing review.
    root_cause           text,
    lessons              text,
    closed_at            timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS incidents_client_idx ON public.incidents (client_id, status);
ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS incidents_select ON public.incidents;
CREATE POLICY incidents_select ON public.incidents FOR SELECT
    USING (has_client_access(client_id, user_id) OR is_admin_user());
DROP POLICY IF EXISTS incidents_insert ON public.incidents;
CREATE POLICY incidents_insert ON public.incidents FOR INSERT
    WITH CHECK (has_client_access(client_id, user_id) AND user_id = auth.uid());
DROP POLICY IF EXISTS incidents_update ON public.incidents;
CREATE POLICY incidents_update ON public.incidents FOR UPDATE
    USING (has_client_access(client_id, user_id))
    WITH CHECK (has_client_access(client_id, user_id));
-- No DELETE policy: an incident record is evidence.

CREATE TABLE IF NOT EXISTS public.incident_events (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id  uuid NOT NULL REFERENCES public.incidents(id) ON DELETE CASCADE,
    client_id    uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    user_id      uuid REFERENCES auth.users(id) ON DELETE SET NULL,  -- NULL: the reminder job
    event_type   text NOT NULL
                 CHECK (event_type IN ('decision', 'notification', 'status', 'note', 'reminder')),
    -- notification / reminder: which deadline (incident_rules.KINDS)
    kind         text,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    reference    text,        -- the authority's reference number
    body         text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS incident_events_incident_idx ON public.incident_events (incident_id, occurred_at);
ALTER TABLE public.incident_events ENABLE ROW LEVEL SECURITY;

-- user_id here is the author, which a workspace member is not the owner
-- of — so access goes through the incident's client, not the event's user.
DROP POLICY IF EXISTS incident_events_select ON public.incident_events;
CREATE POLICY incident_events_select ON public.incident_events FOR SELECT
    USING (has_client_access(client_id, NULL) OR is_admin_user());
DROP POLICY IF EXISTS incident_events_insert ON public.incident_events;
CREATE POLICY incident_events_insert ON public.incident_events FOR INSERT
    WITH CHECK (user_id = auth.uid()
                AND has_client_access(client_id, NULL)
                AND EXISTS (SELECT 1 FROM incidents i WHERE i.id = incident_id
                             AND i.client_id = incident_events.client_id));
-- No UPDATE or DELETE: the timeline is append-only.

-- ── Reporting channels (checked 22 Oct 2026) ─────────────────────────────
UPDATE public.reference_values SET metadata = metadata || jsonb_build_object(
    'breach_portal_url', 'https://moncompte.autoriteprotectiondonnees.be/login',
    'breach_portal_note_en', 'Notify through the APD portal; notifications sent by email are not processed. Submit in Dutch, French or German.',
    'breach_portal_note_fr', 'Notifiez via le portail de l''APD ; les notifications envoyées par e-mail ne sont pas traitées. En néerlandais, français ou allemand.',
    'breach_portal_verified_on', '2026-10-22',
    'csirt_report_url', 'https://notif.safeonweb.be/',
    'csirt_report_note_en', 'Choose the option "NIS2 Entity".',
    'csirt_report_note_fr', 'Choisissez l''option « NIS2 Entity ».',
    'csirt_email', 'incident@ccb.belgium.be',
    'csirt_phone', '+32 2 501 05 60',
    'csirt_guide_url', 'https://ccb.belgium.be/cert/report-incident/nis2-notifications-howto',
    'csirt_report_verified_on', '2026-10-22'
) WHERE value_type = 'jurisdiction' AND code = 'BE';

UPDATE public.reference_values SET metadata = metadata || jsonb_build_object(
    'csirt_report_url', 'https://club.ssi.gouv.fr/#/declarations',
    'csirt_report_note_en', 'ANSSI incident declaration, linked as "Incident" from cyber.gouv.fr.',
    'csirt_report_note_fr', 'Déclaration d''incident de l''ANSSI, lien « Incident » sur cyber.gouv.fr.',
    'csirt_report_verified_on', '2026-10-22'
) WHERE value_type = 'jurisdiction' AND code = 'FR';
-- FR breach_portal_url deliberately absent: the CNIL site was in
-- maintenance when checked. The app shows the authority's site and says the
-- channel is unverified, rather than an address nobody confirmed.
