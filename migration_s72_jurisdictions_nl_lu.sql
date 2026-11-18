-- S72 (D-190), 18 Nov 2026: the Netherlands' and Luxembourg's own country data.
--
-- Until now only BE and FR had a jurisdiction row, so a Dutch or Luxembourg
-- company got no supervisory authority, breach channel, NIS2 recipient or
-- national cookie rules — its incident drafts said "[to complete]" and its
-- Cookie Policy fell back to the generic text. Nothing is borrowed from
-- Belgium (S64's rule). Every value below was read on the authority's own
-- site on 18 Nov 2026; the pages are in links_note.
--
-- Cookie rules follow the shape BE/FR use (template_renderer: NULL numeric =
-- no published national limit; booleans true = stricter). Where an authority
-- RECOMMENDS rather than requires, the rule is recorded and *_advisory marks
-- it, as FR's consent renewal is.

INSERT INTO reference_values (value_type, code, label_en, label_fr, label_nl, label_de,
                              metadata, sort_order, active)
VALUES
('jurisdiction', 'NL', 'Netherlands', 'Pays-Bas', 'Nederland', 'Niederlande', $json${
  "confidence": "high",
  "links_verified_on": "2026-11-18",
  "links_note": "Read 18 Nov 2026: AP 'Zo meldt u een datalek' (melden alleen via het Meldformulier datalekken, niet per telefoon, post of e-mail; binnen 72 uur), the form itself (Dutch, 30-60 min, a session can be saved), AP 'Vuistregels heldere cookiebanners' (vuistregel 2: weigeren net zo makkelijk als accepteren; Telecommunicatiewet art. 11.7a), AP 'Trackingcookies' (cookiewall zonder redelijk alternatief: geen geldige toestemming, verboden), NCSC 'Cyberbeveiligingswet' (in werking 15 augustus 2026) and 'Meldplicht' (centraal meldpunt MijnNCSC: één melding bereikt het sectorale CSIRT en de toezichthouder; 24 u / 72 u / 1 maand).",

  "supervisory_authority_en": "Dutch Data Protection Authority",
  "supervisory_authority_fr": "Autorité néerlandaise de protection des données",
  "supervisory_authority_nl": "Autoriteit Persoonsgegevens",
  "supervisory_authority_de": "Niederländische Datenschutzbehörde",
  "supervisory_authority_short": "AP",
  "supervisory_authority_url": "https://www.autoriteitpersoonsgegevens.nl",
  "supervisory_authority_url_nl": "https://www.autoriteitpersoonsgegevens.nl",
  "supervisory_authority_url_en": "https://www.autoriteitpersoonsgegevens.nl/en",
  "breach_portal_url": "https://datalekken.autoriteitpersoonsgegevens.nl/",
  "breach_guide_url": "https://www.autoriteitpersoonsgegevens.nl/themas/beveiliging/datalekken/zo-meldt-u-een-datalek",
  "breach_guide_url_nl": "https://www.autoriteitpersoonsgegevens.nl/themas/beveiliging/datalekken/zo-meldt-u-een-datalek",
  "breach_guide_url_en": "https://www.autoriteitpersoonsgegevens.nl/en/themes/security/data-breaches/this-is-how-you-report-a-data-breach",
  "breach_portal_note_en": "Notify only through the AP's breach form (Meldformulier datalekken) — not by phone, post or email. The form is in Dutch and takes 30 to 60 minutes; you can save a session and finish later. The AP publishes the form's questions in English to prepare.",
  "breach_portal_note_fr": "Notifiez uniquement via le formulaire de l'AP (Meldformulier datalekken) — pas par téléphone, courrier ou e-mail. Le formulaire est en néerlandais et prend 30 à 60 minutes ; vous pouvez enregistrer une session et la reprendre. L'AP publie les questions du formulaire en anglais pour vous préparer.",
  "breach_portal_note_nl": "Meld alleen via het Meldformulier datalekken van de AP — niet per telefoon, post of e-mail. Het invullen duurt 30 tot 60 minuten; u kunt een sessie opslaan en later verdergaan. De AP publiceert de vragenlijst van het formulier om u voor te bereiden.",
  "breach_portal_verified_on": "2026-11-18",

  "csirt_en": "National Cyber Security Centre (NCSC)",
  "csirt_fr": "Centre national de cybersécurité (NCSC)",
  "csirt_nl": "Nationaal Cyber Security Centrum (NCSC)",
  "csirt_de": "Nationales Zentrum für Cybersicherheit (NCSC)",
  "csirt_short": "NCSC",
  "csirt_url": "https://www.ncsc.nl/cyberbeveiligingswet-nis2",
  "csirt_report_url": "https://mijn.ncsc.nl/",
  "csirt_guide_url": "https://www.ncsc.nl/cyberbeveiligingswet-nis2/meldplicht",
  "csirt_report_note_en": "Report through the central reporting point on MijnNCSC: one report reaches your sector's CSIRT and your supervisor. The Cyberbeveiligingswet (NIS2) has applied since 15 August 2026, and your organisation must be registered with the NCSC.",
  "csirt_report_note_fr": "Signalez via le point de notification central sur MijnNCSC : une seule notification parvient au CSIRT de votre secteur et à votre autorité de contrôle. La Cyberbeveiligingswet (NIS2) s'applique depuis le 15 août 2026, et votre organisation doit être enregistrée auprès du NCSC.",
  "csirt_report_note_nl": "Meld via het centrale meldpunt op MijnNCSC: één melding bereikt uw sectorale CSIRT en uw toezichthouder. De Cyberbeveiligingswet (NIS2) geldt sinds 15 augustus 2026, en uw organisatie moet geregistreerd zijn bij het NCSC.",
  "csirt_report_verified_on": "2026-11-18",

  "eprivacy_instrument": "Telecommunicatiewet, Art. 11.7a",
  "reject_parity_required": true,
  "cookie_walls_prohibited": true,
  "numeric_limits_published": false,
  "cookie_max_lifetime_months": null,
  "cookie_data_retention_months": null,
  "consent_renewal_months": null
}$json$::jsonb, 30, true),

('jurisdiction', 'LU', 'Luxembourg', 'Luxembourg', 'Luxemburg', 'Luxemburg', $json${
  "confidence": "high",
  "links_verified_on": "2026-11-18",
  "links_note": "Read 18 Nov 2026: CNPD 'Violations de données (RGPD)' (72 h; formulaire Word à télécharger, à renvoyer en .docx à databreach@cnpd.lu, clé GPG proposée), CNPD 'Lignes directrices en matière de cookies' §3 (cookie wall pour cookies non essentiels : pas de consentement valide ; « recommande fortement » d'offrir les mêmes possibilités pour refuser ; consentement à renouveler après 12 mois maximum, recommandé ; loi modifiée du 30 mai 2005, art. 4.3 e)), ILR 'Notification incident' (loi du 5 mai 2026 ; notification à l'ILR dans les 24 h via SERIMA pour les secteurs qu'il supervise ; 24 h / 72 h / rapport final un mois après).",

  "supervisory_authority_en": "National Commission for Data Protection",
  "supervisory_authority_fr": "Commission nationale pour la protection des données",
  "supervisory_authority_nl": "Nationale Commissie voor gegevensbescherming",
  "supervisory_authority_de": "Nationale Kommission für den Datenschutz",
  "supervisory_authority_short": "CNPD",
  "supervisory_authority_url": "https://cnpd.public.lu/fr.html",
  "supervisory_authority_url_fr": "https://cnpd.public.lu/fr.html",
  "supervisory_authority_url_en": "https://cnpd.public.lu/en.html",
  "supervisory_authority_url_de": "https://cnpd.public.lu/de.html",
  "breach_portal_url": "mailto:databreach@cnpd.lu",
  "breach_guide_url": "https://cnpd.public.lu/fr/professionnels/obligations/obligations-rgpd/violation-de-donnees/violation-donnees-rgpd.html",
  "breach_portal_note_en": "No online portal: download the CNPD's notification form (Word) from its page, fill it in and email the .docx to databreach@cnpd.lu. The CNPD offers a GPG key to encrypt it. Attach any relevant document.",
  "breach_portal_note_fr": "Pas de portail en ligne : téléchargez le formulaire de notification de la CNPD (Word) sur sa page, complétez-le et envoyez le .docx à databreach@cnpd.lu. La CNPD propose une clé GPG pour le chiffrer. Joignez tout document pertinent.",
  "breach_portal_note_nl": "Geen online portaal: download het meldformulier van de CNPD (Word) op haar pagina, vul het in en mail het .docx-bestand naar databreach@cnpd.lu. De CNPD biedt een GPG-sleutel aan om het te versleutelen. Voeg relevante documenten toe.",
  "breach_portal_verified_on": "2026-11-18",

  "csirt_en": "Luxembourg Regulatory Institute (ILR)",
  "csirt_fr": "Institut Luxembourgeois de Régulation (ILR)",
  "csirt_nl": "Luxemburgs Instituut voor Regulering (ILR)",
  "csirt_de": "Luxemburger Regulierungsinstitut (ILR)",
  "csirt_short": "ILR",
  "csirt_url": "https://www.ilr.lu/secteurs-activites/niss/",
  "csirt_report_url": "https://serima.lu/notification",
  "csirt_guide_url": "https://www.ilr.lu/secteurs-activites/niss/notification-incident/",
  "csirt_report_note_en": "Under the NIS2 law of 5 May 2026, entities in the sectors the ILR supervises notify it through its SERIMA platform. An entity supervised by another authority (for example the financial sector) notifies that authority instead. For help resolving the incident itself, contact your CSIRT.",
  "csirt_report_note_fr": "Selon la loi NIS 2 du 5 mai 2026, les entités des secteurs supervisés par l'ILR lui notifient l'incident via sa plateforme SERIMA. Une entité supervisée par une autre autorité (par exemple le secteur financier) notifie cette autorité. Pour de l'aide dans la résolution de l'incident, contactez votre CSIRT.",
  "csirt_report_note_nl": "Volgens de NIS2-wet van 5 mei 2026 melden entiteiten in de sectoren onder toezicht van het ILR het incident via zijn platform SERIMA. Een entiteit onder toezicht van een andere autoriteit (bijvoorbeeld de financiële sector) meldt aan die autoriteit. Voor hulp bij het oplossen van het incident zelf: contacteer uw CSIRT.",
  "csirt_report_verified_on": "2026-11-18",

  "eprivacy_instrument": "Loi modifiée du 30 mai 2005, Art. 4(3)(e)",
  "reject_parity_required": true,
  "reject_parity_advisory": true,
  "cookie_walls_prohibited": true,
  "numeric_limits_published": false,
  "cookie_max_lifetime_months": null,
  "cookie_data_retention_months": null,
  "consent_renewal_months": 12,
  "consent_renewal_advisory": true
}$json$::jsonb, 40, true)
ON CONFLICT (value_type, code, workspace_id) DO UPDATE
   SET metadata = EXCLUDED.metadata,
       label_en = EXCLUDED.label_en, label_fr = EXCLUDED.label_fr,
       label_nl = EXCLUDED.label_nl, label_de = EXCLUDED.label_de,
       updated_at = now();
