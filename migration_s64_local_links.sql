-- S64 (D-165): links in the reader's language, Belgium.
--
-- The APD/GBA runs one site per language, and its breach portal per language
-- is the one that language version of the site links to. Verified 11 Nov 2026
-- by loading the home and breach pages; the portals refuse automated visits,
-- so their hosts are taken from the authority's own links. CCB pages refuse
-- automated visits too: not localized until checked by hand.
-- Read through <key>_<lang>, falling back to <key> (template_store.build_values,
-- incident_rules.authorities).
update public.reference_values set metadata = metadata || jsonb_build_object(
  'supervisory_authority_url_nl', 'https://www.gegevensbeschermingsautoriteit.be',
  'supervisory_authority_url_fr', 'https://www.autoriteprotectiondonnees.be',
  'supervisory_authority_url_de', 'https://www.datenschutzbehorde.be',
  'supervisory_authority_url_en', 'https://www.dataprotectionauthority.be',
  'breach_portal_url_nl', 'https://mijnaccount.gegevensbeschermingsautoriteit.be/login',
  'breach_portal_url_fr', 'https://moncompte.autoriteprotectiondonnees.be/login',
  'breach_portal_url_de', 'https://meinkonto.datenschutzbehörde.be/login',
  'breach_guide_url_nl', 'https://www.gegevensbeschermingsautoriteit.be/professioneel/acties/gegevensinbreuk',
  'breach_guide_url_fr', 'https://www.autoriteprotectiondonnees.be/professionnel/actions/violation-de-donnees-personnelles',
  'breach_portal_note_nl', 'Meld via het portaal van de GBA; meldingen per e-mail worden niet behandeld. In het Nederlands, Frans of Duits.',
  'csirt_report_note_nl', 'Kies de optie "NIS2 Entity".',
  'links_verified_on', '2026-11-11'
) where value_type = 'jurisdiction' and code = 'BE';

update public.reference_values set metadata = metadata || jsonb_build_object(
  'supervisory_authority_url_en', 'https://www.cnil.fr/en/home',
  'links_verified_on', '2026-11-11'
) where value_type = 'jurisdiction' and code = 'FR';
