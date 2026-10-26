-- S53: the CNIL's breach notification channel, checked on cnil.fr on
-- 26 Oct 2026 (the site was in maintenance on 22 Oct, so FR shipped without
-- it — migration_s53_incidents.sql). Applied 26 Oct. Idempotent.
UPDATE public.reference_values SET metadata = metadata || jsonb_build_object(
    'breach_portal_url', 'https://notifications.cnil.fr/notifications/',
    'breach_portal_note_en', 'Notify through the CNIL''s online service ("Démarrer une notification"). A preparatory document listing the steps is on the CNIL''s page. If the breach follows a cyberattack, the CNIL also advises filing a police complaint.',
    'breach_portal_note_fr', 'Notifiez via le téléservice de la CNIL (« Démarrer une notification »). Un document préparatoire reprenant les étapes est disponible sur la page de la CNIL. Si la violation fait suite à une cyberattaque, la CNIL conseille aussi de porter plainte.',
    'breach_portal_verified_on', '2026-10-26'
) WHERE value_type = 'jurisdiction' AND code = 'FR';
