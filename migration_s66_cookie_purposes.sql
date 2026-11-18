-- S66 (D-187), 18 Nov 2026: Cookie Policy purpose granularity.
--
-- A vendor that sets cookies often does so for several purposes (Google:
-- analytics, advertising, personalisation, fraud prevention). ePrivacy
-- Art. 5(3) asks for clear information per purpose, and consent must be
-- specific (GDPR Art. 4(11)); one free-text purpose per vendor cannot say
-- that. So the Cookie Policy gets one row per vendor AND purpose.
--
-- Not a copy of systems.purpose. "What you use it for" stays on the system:
-- it describes the tool for every document, not only the Cookie Policy, and
-- a copy here would drift from it the first time either was edited. A
-- cookie-setting system with no rows here renders as it always did, from
-- systems.purpose (template_store._load_vendor_rows).

-- ── The purposes, as reference data ───────────────────────────────────────
-- Not the system_category vocabulary the scope named: that one says what
-- kind of tool a system is (HR and payroll, hosting), and has neither
-- "strictly necessary" — the one purpose exempt from consent — nor
-- "advertising". consent_required drives nothing yet; it records the rule.
--
-- reference_values only accepts a listed value_type. The list is extended
-- from whatever the database has, not retyped, so a type added on one side
-- and not the other is never dropped.
DO $$
DECLARE def text;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO def FROM pg_constraint
     WHERE conname = 'reference_values_type_valid'
       AND conrelid = 'public.reference_values'::regclass;
    IF def IS NOT NULL AND position('''cookie_purpose''' IN def) = 0 THEN
        ALTER TABLE reference_values DROP CONSTRAINT reference_values_type_valid;
        EXECUTE 'ALTER TABLE reference_values ADD CONSTRAINT reference_values_type_valid '
             || replace(def, '])))', ', ''cookie_purpose''::text])))');
    END IF;
END $$;

INSERT INTO reference_values (value_type, code, label_en, label_fr, label_nl, label_de,
                              metadata, sort_order, active)
VALUES
 ('cookie_purpose', 'strictly_necessary', 'Strictly necessary', 'Strictement nécessaire',
  'Strikt noodzakelijk', 'Unbedingt erforderlich', '{"consent_required": false}', 10, true),
 ('cookie_purpose', 'preferences', 'Preferences and functionality', 'Préférences et fonctionnalités',
  'Voorkeuren en functionaliteit', 'Präferenzen und Funktionalität', '{"consent_required": true}', 20, true),
 ('cookie_purpose', 'analytics', 'Analytics and audience measurement', 'Statistiques et mesure d''audience',
  'Analyse en publieksmeting', 'Analyse und Reichweitenmessung', '{"consent_required": true}', 30, true),
 ('cookie_purpose', 'advertising', 'Advertising and targeting', 'Publicité et ciblage',
  'Advertenties en targeting', 'Werbung und Targeting', '{"consent_required": true}', 40, true),
 ('cookie_purpose', 'personalisation', 'Personalisation', 'Personnalisation',
  'Personalisatie', 'Personalisierung', '{"consent_required": true}', 50, true),
 ('cookie_purpose', 'social_media', 'Social media', 'Réseaux sociaux',
  'Sociale media', 'Soziale Medien', '{"consent_required": true}', 60, true),
 ('cookie_purpose', 'security', 'Security and fraud prevention', 'Sécurité et prévention de la fraude',
  'Beveiliging en fraudepreventie', 'Sicherheit und Betrugsprävention', '{"consent_required": true}', 70, true),
 ('cookie_purpose', 'other', 'Other', 'Autre', 'Andere', 'Sonstiges', '{"consent_required": true}', 90, true)
ON CONFLICT DO NOTHING;

-- ── One row per system and purpose ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_cookie_purposes (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id          uuid NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
    -- Carried for RLS, as on systems and activity_systems.
    client_id          uuid,
    user_id            uuid NOT NULL,
    purpose_code       text NOT NULL,
    -- Per document language, like systems.purpose_i18n (S26C).
    description_i18n   jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Cookie names or identifiers where known (_ga, _fbp…); free text until a
    -- scanner records them.
    cookie_names       text,
    sort_order         integer NOT NULL DEFAULT 0,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (system_id, purpose_code)
);

CREATE INDEX IF NOT EXISTS system_cookie_purposes_client_idx
    ON system_cookie_purposes (client_id);

ALTER TABLE system_cookie_purposes ENABLE ROW LEVEL SECURITY;

-- The same four policies as systems.
DROP POLICY IF EXISTS system_cookie_purposes_select ON system_cookie_purposes;
CREATE POLICY system_cookie_purposes_select ON system_cookie_purposes
    FOR SELECT USING (has_client_access(client_id, user_id));
DROP POLICY IF EXISTS system_cookie_purposes_insert ON system_cookie_purposes;
CREATE POLICY system_cookie_purposes_insert ON system_cookie_purposes
    FOR INSERT WITH CHECK (can_edit_client(client_id, user_id) AND user_id = auth.uid());
DROP POLICY IF EXISTS system_cookie_purposes_update ON system_cookie_purposes;
CREATE POLICY system_cookie_purposes_update ON system_cookie_purposes
    FOR UPDATE USING (has_client_access(client_id, user_id))
    WITH CHECK (can_edit_client(client_id, user_id));
DROP POLICY IF EXISTS system_cookie_purposes_delete ON system_cookie_purposes;
CREATE POLICY system_cookie_purposes_delete ON system_cookie_purposes
    FOR DELETE USING (has_client_access(client_id, user_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON system_cookie_purposes TO authenticated;
