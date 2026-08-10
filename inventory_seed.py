"""
inventory_seed.py — authored source for the S24 reference data.

This file is NOT read at runtime. The app reads reference_values and
vendor_catalogue from Postgres via inventory.py; this module is where the
content is *written*, reviewed and version-controlled, and it emits the
idempotent SQL that loads it.

The split exists because authoring and serving want opposite things. Authoring
wants a diff a reviewer can read in a pull request, comments explaining why a
vendor defaults to `processor` rather than `joint_controller`, and one file to
change. Serving wants a table the S41 scanner can query, per-language label
columns, and per-workspace rows that a module constant cannot express. Keeping
both in one place would mean giving up one of them.

Run:  python inventory_seed.py > seed_s24_reference_data.sql

then paste the result into the Supabase SQL editor, after the migration. The
output is idempotent (ON CONFLICT DO UPDATE against the real UNIQUE
constraints), so re-running after editing this file is the normal workflow for
adding vendors or vocabulary terms.

── Append-only discipline ────────────────────────────────────────────────
Vocabulary codes must never be renamed or deleted. Client rows store them as
plain text in TEXT[] columns, so a rename orphans live compliance data and the
orphan check in the migration is the only thing that would notice. To retire a
term, set active=False here and re-run; existing rows keep resolving, and the
term stops being offered.

── Language scope ────────────────────────────────────────────────────────
EN and FR are populated. NL and DE columns exist and are left NULL pending the
open decision on language scope — inventory.py falls back to English when a
label is missing, so a partial translation degrades to a working app rather
than a blank dropdown.
"""

from __future__ import annotations


# ── Vocabularies ──────────────────────────────────────────────────────────
# (code, label_en, label_fr, note_en, metadata)

VOCABULARIES: dict[str, list[tuple]] = {

    "system_category": [
        ("analytics", "Analytics and measurement", "Analyse et mesure", None, {}),
        ("crm_marketing", "CRM and marketing", "CRM et marketing", None, {}),
        ("email_comms", "Email and communications", "Messagerie et communications", None, {}),
        ("productivity_storage", "Productivity and file storage", "Bureautique et stockage", None, {}),
        ("hosting_infrastructure", "Hosting and infrastructure", "Hébergement et infrastructure", None, {}),
        ("payments", "Payments and billing", "Paiements et facturation", None, {}),
        ("hr_payroll", "HR and payroll", "RH et paie", None, {}),
        ("accounting_finance", "Accounting and finance", "Comptabilité et finance", None, {}),
        ("support_ticketing", "Support and ticketing", "Support et tickets", None, {}),
        ("security", "Security and identity", "Sécurité et identité", None, {}),
        ("ai_assistant", "AI tools and assistants", "Outils et assistants IA", None, {}),
        ("other", "Other", "Autre", None, {}),
    ],

    # Ordinary personal data. Deliberately coarse: these are RoPA row labels,
    # not a data dictionary. Finer granularity belongs in the schema-import
    # tool on the backlog, not in a form an SME fills in by hand.
    "data_category": [
        ("identity", "Identity data", "Données d'identité",
         "Name, date of birth, identifiers you assign.", {}),
        ("contact", "Contact details", "Coordonnées",
         "Email, phone, postal address.", {}),
        ("government_id", "Government identifiers", "Identifiants officiels",
         "National register number, passport, VAT number for sole traders.", {}),
        ("account_credentials", "Account credentials", "Identifiants de connexion", None, {}),
        ("financial", "Financial data", "Données financières",
         "Bank details, salary, credit information.", {}),
        ("transaction", "Transaction and order history", "Historique des transactions", None, {}),
        ("employment", "Employment data", "Données professionnelles",
         "Role, contract terms, performance records.", {}),
        ("education_training", "Education and training records", "Formation et diplômes", None, {}),
        ("location", "Location data", "Données de localisation", None, {}),
        ("device_technical", "Device and technical data", "Données techniques et d'appareil",
         "IP address, browser, device identifiers, cookie IDs.", {}),
        ("usage_behavioural", "Usage and behavioural data", "Données d'usage et de comportement", None, {}),
        ("communications_content", "Content of communications", "Contenu des communications", None, {}),
        ("images_av", "Images, audio and video", "Images, audio et vidéo", None, {}),
        ("contractual", "Contractual and commercial data", "Données contractuelles et commerciales", None, {}),
        ("marketing_preferences", "Marketing preferences and consent records",
         "Préférences marketing et preuves de consentement", None, {}),
    ],

    # Art. 9(1) only. Criminal convictions are Art. 10 and sit separately —
    # a RoPA listing convictions under Art. 9 is wrong on its face and a
    # reviewing DPA will notice.
    "special_category": [
        ("racial_ethnic", "Racial or ethnic origin", "Origine raciale ou ethnique", None, {}),
        ("political_opinions", "Political opinions", "Opinions politiques", None, {}),
        ("religious_philosophical", "Religious or philosophical beliefs",
         "Convictions religieuses ou philosophiques", None, {}),
        ("trade_union", "Trade union membership", "Appartenance syndicale", None, {}),
        ("genetic", "Genetic data", "Données génétiques", None, {}),
        ("biometric_id", "Biometric data for unique identification",
         "Données biométriques d'identification", None, {}),
        ("health", "Health data", "Données de santé",
         "Includes sick leave records and workplace accident reports.", {}),
        ("sex_life_orientation", "Sex life or sexual orientation",
         "Vie sexuelle ou orientation sexuelle", None, {}),
    ],

    "criminal_data": [
        ("criminal_convictions", "Criminal convictions and offences",
         "Condamnations pénales et infractions",
         "Art. 10 — a separate regime requiring official authority or a "
         "specific legal basis in national law.", {}),
    ],

    # Art. 9(2)(a)-(j).
    "art9_condition": [
        ("explicit_consent", "(a) Explicit consent", "(a) Consentement explicite", None, {}),
        ("employment_social_security", "(b) Employment and social security law",
         "(b) Droit du travail et de la sécurité sociale",
         "The usual basis for sick leave and payroll health data.", {}),
        ("vital_interests", "(c) Vital interests", "(c) Intérêts vitaux", None, {}),
        ("nonprofit_body", "(d) Non-profit body activities",
         "(d) Activités d'un organisme sans but lucratif", None, {}),
        ("manifestly_public", "(e) Manifestly made public by the subject",
         "(e) Manifestement rendues publiques par la personne", None, {}),
        ("legal_claims", "(f) Legal claims", "(f) Constatation ou défense de droits en justice", None, {}),
        ("substantial_public_interest", "(g) Substantial public interest",
         "(g) Intérêt public important", None, {}),
        ("occupational_medicine", "(h) Occupational medicine and medical diagnosis",
         "(h) Médecine du travail et diagnostic médical", None, {}),
        ("public_health", "(i) Public health", "(i) Santé publique", None, {}),
        ("archiving_research", "(j) Archiving, research and statistics",
         "(j) Archivage, recherche et statistiques", None, {}),
    ],

    "data_subject_category": [
        ("employees", "Employees", "Employés", None, {}),
        ("job_applicants", "Job applicants", "Candidats", None, {}),
        ("contractors", "Contractors and freelancers", "Indépendants et sous-traitants", None, {}),
        ("customers", "Customers", "Clients", None, {}),
        ("prospects", "Prospects and leads", "Prospects", None, {}),
        ("website_visitors", "Website visitors", "Visiteurs du site web", None, {}),
        ("supplier_contacts", "Supplier and partner contacts", "Contacts fournisseurs et partenaires", None, {}),
        ("shareholders", "Shareholders and directors", "Actionnaires et administrateurs", None, {}),
        ("children", "Children under 16", "Mineurs de moins de 16 ans",
         "Belgium sets the digital consent age at 13; France at 15. Check "
         "the applicable national rule before relying on consent.", {"heightened_risk": True}),
        ("members", "Members", "Membres", None, {}),
        ("other", "Other", "Autre", None, {}),
    ],

    # Art. 6(1)(a)-(f).
    "legal_basis": [
        ("consent", "(a) Consent", "(a) Consentement",
         "Must be freely given, specific, informed and withdrawable.",
         {"requires_evidence": True}),
        ("contract", "(b) Performance of a contract", "(b) Exécution d'un contrat", None, {}),
        ("legal_obligation", "(c) Legal obligation", "(c) Obligation légale",
         "Name the obligation in the retention basis field.", {}),
        ("vital_interests", "(d) Vital interests", "(d) Intérêts vitaux", None, {}),
        ("public_task", "(e) Public interest or official authority",
         "(e) Mission d'intérêt public", None, {}),
        ("legitimate_interests", "(f) Legitimate interests", "(f) Intérêts légitimes",
         "Requires a recorded balancing test. An unevidenced claim of "
         "legitimate interests is the most common RoPA defect.",
         {"requires_balancing_test": True}),
    ],

    # Chapter V. `none_eea` means no transfer occurs; `unknown` means we have
    # not established whether one occurs. One is a finding, the other a gap.
    "transfer_mechanism": [
        ("none_eea", "No transfer outside the EEA", "Aucun transfert hors EEE", None, {}),
        ("adequacy_decision", "Adequacy decision (Art. 45)", "Décision d'adéquation (art. 45)", None, {}),
        ("scc", "Standard Contractual Clauses (Art. 46)",
         "Clauses contractuelles types (art. 46)",
         "A transfer impact assessment is expected alongside the clauses.",
         {"requires_safeguard_doc": True}),
        ("bcr", "Binding Corporate Rules (Art. 47)", "Règles d'entreprise contraignantes (art. 47)",
         None, {"requires_safeguard_doc": True}),
        ("art49_derogation", "Derogation for a specific situation (Art. 49)",
         "Dérogation pour situation particulière (art. 49)",
         "Occasional and non-repetitive transfers only.", {}),
        ("unknown", "Not yet established", "À déterminer", None, {"is_gap": True}),
    ],

    "dpa_status": [
        ("not_required", "Not required", "Non requis",
         "No personal data is processed by this vendor.", {}),
        ("none", "None in place", "Aucun en place", None, {"is_gap": True}),
        ("requested", "Requested, not yet signed", "Demandé, non signé", None, {"is_gap": True}),
        ("signed", "Signed", "Signé", None, {}),
        ("unknown", "Not yet established", "À déterminer", None, {"is_gap": True}),
    ],

    "controller_role": [
        ("controller", "Controller", "Responsable du traitement", None, {}),
        ("joint_controller", "Joint controller (Art. 26)", "Responsable conjoint (art. 26)",
         "Requires an arrangement setting out respective responsibilities.", {}),
        ("processor", "Processor acting for another controller",
         "Sous-traitant pour un autre responsable", None, {}),
    ],

    # The system's role within an activity — the join table's field.
    "system_role": [
        ("processor", "Processor", "Sous-traitant", None, {}),
        ("sub_processor", "Sub-processor", "Sous-traitant ultérieur", None, {}),
        ("joint_controller", "Joint controller", "Responsable conjoint",
         "Ad and analytics platforms are the usual case, following "
         "Fashion ID (C-40/17).", {}),
        ("recipient_controller", "Independent controller receiving the data",
         "Destinataire responsable indépendant", None, {}),
        ("internal", "Internal system", "Système interne",
         "Self-hosted, no third party involved.", {}),
    ],

    # NIS2 Art. 21(2). Drives the supply-chain register on the backlog.
    "criticality": [
        ("low", "Low — no operational impact", "Faible — aucun impact opérationnel", None, {}),
        ("medium", "Medium — degraded operation", "Moyen — fonctionnement dégradé", None, {}),
        ("high", "High — significant disruption", "Élevé — perturbation importante", None, {}),
        ("critical", "Critical — operations stop", "Critique — arrêt des opérations", None, {}),
    ],

    # EU AI Act. Feeds the obligations added in S23; the distinction
    # determines which duties attach, and most SMEs are deployers.
    "ai_role": [
        ("none", "Not an AI system", "Pas un système d'IA", None, {}),
        ("deployer", "Deployer — we use it", "Déployeur — nous l'utilisons", None, {}),
        ("provider", "Provider — we build or brand it",
         "Fournisseur — nous le développons ou le commercialisons", None, {}),
        ("distributor", "Distributor", "Distributeur", None, {}),
        ("importer", "Importer", "Importateur", None, {}),
    ],

    "security_measure": [
        ("access_control", "Role-based access control", "Contrôle d'accès basé sur les rôles", None, {}),
        ("mfa", "Multi-factor authentication", "Authentification multifacteur", None, {}),
        ("encryption_at_rest", "Encryption at rest", "Chiffrement au repos", None, {}),
        ("encryption_in_transit", "Encryption in transit", "Chiffrement en transit", None, {}),
        ("pseudonymisation", "Pseudonymisation", "Pseudonymisation", None, {}),
        ("backup", "Backup and restore procedure", "Sauvegarde et restauration", None, {}),
        ("logging_monitoring", "Logging and monitoring", "Journalisation et supervision", None, {}),
        ("vulnerability_management", "Patching and vulnerability management",
         "Correctifs et gestion des vulnérabilités", None, {}),
        ("penetration_testing", "Penetration testing", "Tests d'intrusion", None, {}),
        ("staff_training", "Staff awareness training", "Sensibilisation du personnel", None, {}),
        ("physical_security", "Physical access security", "Sécurité des accès physiques", None, {}),
        ("least_privilege", "Least-privilege review", "Revue du moindre privilège", None, {}),
        ("incident_response", "Documented incident response", "Procédure d'incident documentée", None, {}),
    ],
}


# ── Vendor catalogue ──────────────────────────────────────────────────────
#
# Three vendors, chosen to exercise every branch of the schema rather than to
# cover the market: one US transfer and one EU-only, one AI-capable and two
# not, one Art. 9 and two ordinary, one many-to-many and two 1:1, one
# cookie-setting and two invisible to the scanner.
#
# Every value here is a defensible default, not a fact. The client's own
# contract, region and configuration override it, which is why nothing is
# written to `systems` without passing through the intake form first.

VENDOR_CATALOGUE = [
    {
        "key": "google_analytics",
        "name": "Google Analytics",
        "vendor_legal_name": "Google Ireland Limited",
        "category": "analytics",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://business.safety.google/gdprprocessorterms/",
        "privacy_policy_url": "https://policies.google.com/privacy",
        "sets_cookies": True,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "low",
        "default_system_role": "processor",
        # Not a settled question. Several DPAs have treated analytics and ad
        # platforms as joint controllers for the collection stage, and the
        # CNIL's position on GA has moved more than once. Default to
        # processor, surface the alternative, let the client decide.
        "role_note_en": (
            "Commonly configured as a processor, but joint controllership is "
            "arguable for the collection stage where advertising features are "
            "enabled. Confirm against your own configuration."
        ),
        "role_note_fr": (
            "Généralement configuré en sous-traitant, mais la responsabilité "
            "conjointe est défendable pour la phase de collecte lorsque les "
            "fonctionnalités publicitaires sont activées. À vérifier selon "
            "votre configuration."
        ),
        "domain_patterns": [
            ("google-analytics.com", "domain", "high"),
            ("googletagmanager.com", "script_src", "medium"),
            ("_ga", "cookie_name", "high"),
        ],
        "activities": [
            {
                "name_en": "Website analytics",
                "name_fr": "Analyse d'audience du site web",
                "purpose_en": "Measuring website traffic and visitor behaviour",
                "purpose_fr": "Mesure du trafic et du comportement des visiteurs",
                "legal_basis": "consent",
                "data_subject_categories": ["website_visitors"],
                "data_categories": ["device_technical", "usage_behavioural", "location"],
                "special_categories": [],
                "art9_condition": None,
                "retention_period_en": "14 months",
                "retention_period_fr": "14 mois",
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "microsoft_365",
        "name": "Microsoft 365",
        "vendor_legal_name": "Microsoft Ireland Operations Limited",
        "category": "productivity_storage",
        "establishment_country": "IE",
        "processing_country": "EU",
        # The EU Data Boundary covers most core services, but sub-processors
        # and support access can still reach outside it. SCCs remain the
        # honest answer for an SME that has not audited its tenant.
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://www.microsoft.com/licensing/docs/view/Microsoft-Products-and-Services-Data-Protection-Addendum-DPA",
        "privacy_policy_url": "https://privacy.microsoft.com/privacystatement",
        "sets_cookies": False,
        "ai_role": "deployer",
        "ai_conditional": True,
        "ai_note_en": (
            "Set to deployer only if Copilot or another AI feature is licensed "
            "and enabled in your tenant. Otherwise leave as 'not an AI system'."
        ),
        "ai_note_fr": (
            "Sélectionnez « déployeur » uniquement si Copilot ou une autre "
            "fonctionnalité d'IA est sous licence et activée dans votre "
            "tenant. Sinon, laissez « pas un système d'IA »."
        ),
        "default_criticality": "critical",
        "default_system_role": "processor",
        "domain_patterns": [
            ("office.com", "domain", "medium"),
            ("outlook.office365.com", "domain", "high"),
        ],
        # Four activities from one vendor. This is the case the join table
        # exists for — a vendor that seeds one activity behaves like a flat
        # table and proves nothing.
        "activities": [
            {
                "name_en": "Business email and calendaring",
                "name_fr": "Messagerie professionnelle et agenda",
                "purpose_en": "Internal and external business correspondence",
                "purpose_fr": "Correspondance professionnelle interne et externe",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["employees", "customers", "prospects", "supplier_contacts"],
                "data_categories": ["identity", "contact", "communications_content"],
                "special_categories": [],
                "art9_condition": None,
                "retention_period_en": "Duration of employment plus 1 year",
                "retention_period_fr": "Durée du contrat de travail plus 1 an",
                "system_role": "processor",
            },
            {
                "name_en": "Document and file storage",
                "name_fr": "Stockage de documents et de fichiers",
                "purpose_en": "Storing and sharing business documents",
                "purpose_fr": "Stockage et partage de documents professionnels",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["employees", "customers", "supplier_contacts"],
                "data_categories": ["identity", "contact", "contractual"],
                "special_categories": [],
                "art9_condition": None,
                "retention_period_en": "Per document retention schedule",
                "retention_period_fr": "Selon le calendrier de conservation documentaire",
                "system_role": "processor",
            },
            {
                # Sick notes and accommodation records land here in practice,
                # which is what makes an ordinary file-storage tool an Art. 9
                # processor without anyone deciding it should be.
                "name_en": "HR record storage",
                "name_fr": "Conservation des dossiers RH",
                "purpose_en": "Storing personnel files and HR documentation",
                "purpose_fr": "Conservation des dossiers du personnel",
                "legal_basis": "legal_obligation",
                "data_subject_categories": ["employees", "job_applicants"],
                "data_categories": ["identity", "contact", "government_id",
                                    "employment", "education_training", "financial"],
                "special_categories": ["health"],
                "art9_condition": "employment_social_security",
                "retention_period_en": "5 years after end of employment",
                "retention_period_fr": "5 ans après la fin du contrat de travail",
                "system_role": "processor",
            },
            {
                "name_en": "Internal collaboration and messaging",
                "name_fr": "Collaboration et messagerie interne",
                "purpose_en": "Team communication via Teams",
                "purpose_fr": "Communication d'équipe via Teams",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["employees", "contractors"],
                "data_categories": ["identity", "communications_content", "images_av"],
                "special_categories": [],
                "art9_condition": None,
                "retention_period_en": "Duration of employment",
                "retention_period_fr": "Durée du contrat de travail",
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "sd_worx",
        "name": "SD Worx",
        "vendor_legal_name": "SD Worx NV",
        "category": "hr_payroll",
        "establishment_country": "BE",
        "processing_country": "BE",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": None,
        "privacy_policy_url": "https://www.sdworx.be/nl-be/privacy",
        "sets_cookies": False,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "high",
        "default_system_role": "processor",
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Payroll administration",
                "name_fr": "Administration de la paie",
                "purpose_en": ("Calculating and paying salaries, and meeting social "
                               "security and tax reporting obligations"),
                "purpose_fr": ("Calcul et paiement des salaires, et respect des "
                               "obligations sociales et fiscales"),
                "legal_basis": "legal_obligation",
                "data_subject_categories": ["employees"],
                "data_categories": ["identity", "contact", "government_id",
                                    "financial", "employment"],
                # Sick leave and work-accident records make this Art. 9.
                "special_categories": ["health"],
                "art9_condition": "employment_social_security",
                "retention_period_en": "5 years (social documents, Belgian law)",
                "retention_period_fr": "5 ans (documents sociaux, droit belge)",
                "system_role": "processor",
            },
        ],
    },
]


# ── SQL emitter ───────────────────────────────────────────────────────────

def _q(value) -> str:
    """Quote a Python value as a SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "'{}'"
        inner = ", ".join(_q(v) for v in value)
        return f"ARRAY[{inner}]::TEXT[]"
    if isinstance(value, dict):
        import json
        return "'" + json.dumps(value).replace("'", "''") + "'::JSONB"
    return "'" + str(value).replace("'", "''") + "'"


def emit_sql() -> str:
    out: list[str] = []
    w = out.append

    w("-- ============================================================================")
    w("-- S24 seed — reference data")
    w("--")
    w("-- GENERATED by inventory_seed.py. Do not edit by hand: edit the Python and")
    w("-- regenerate, or the next regeneration silently reverts the change.")
    w("--")
    w("-- Idempotent. Re-running after adding a vendor or a vocabulary term is the")
    w("-- normal workflow. Codes are never deleted here — retiring a term means")
    w("-- setting active = FALSE in the source, because client rows hold these codes")
    w("-- as plain text and a delete orphans live compliance data.")
    w("-- ============================================================================")
    w("")
    w("BEGIN;")
    w("")

    # Vocabularies
    w("-- ── Vocabularies ──────────────────────────────────────────────────────────")
    for vtype, entries in VOCABULARIES.items():
        w("")
        w(f"-- {vtype}")
        for i, (code, en, fr, note_en, meta) in enumerate(entries):
            w(
                "INSERT INTO reference_values "
                "(value_type, code, workspace_id, label_en, label_fr, note_en, metadata, sort_order, active)"
            )
            w(
                f"VALUES ({_q(vtype)}, {_q(code)}, NULL, {_q(en)}, {_q(fr)}, "
                f"{_q(note_en)}, {_q(meta)}, {i}, TRUE)"
            )
            w("ON CONFLICT (value_type, code, workspace_id) DO UPDATE SET")
            w("    label_en = EXCLUDED.label_en, label_fr = EXCLUDED.label_fr,")
            w("    note_en = EXCLUDED.note_en, metadata = EXCLUDED.metadata,")
            w("    sort_order = EXCLUDED.sort_order, active = EXCLUDED.active;")

    # Catalogue
    w("")
    w("-- ── Vendor catalogue ──────────────────────────────────────────────────────")
    for i, v in enumerate(VENDOR_CATALOGUE):
        w("")
        w(f"-- {v['name']}")
        cols = (
            "key, name, vendor_legal_name, category, establishment_country, "
            "processing_country, transfer_mechanism, dpa_status, dpa_url, "
            "privacy_policy_url, sets_cookies, ai_role, ai_conditional, "
            "ai_note_en, ai_note_fr, default_criticality, default_system_role, "
            "role_note_en, role_note_fr, sort_order, active"
        )
        vals = ", ".join(_q(x) for x in [
            v["key"], v["name"], v.get("vendor_legal_name"), v.get("category"),
            v.get("establishment_country"), v.get("processing_country"),
            v.get("transfer_mechanism"), v.get("dpa_status"), v.get("dpa_url"),
            v.get("privacy_policy_url"), v.get("sets_cookies", False),
            v.get("ai_role", "none"), v.get("ai_conditional", False),
            v.get("ai_note_en"), v.get("ai_note_fr"),
            v.get("default_criticality", "medium"),
            v.get("default_system_role", "processor"),
            v.get("role_note_en"), v.get("role_note_fr"), i, True,
        ])
        w(f"INSERT INTO vendor_catalogue ({cols})")
        w(f"VALUES ({vals})")
        w("ON CONFLICT (key) DO UPDATE SET")
        w("    name = EXCLUDED.name, vendor_legal_name = EXCLUDED.vendor_legal_name,")
        w("    category = EXCLUDED.category,")
        w("    establishment_country = EXCLUDED.establishment_country,")
        w("    processing_country = EXCLUDED.processing_country,")
        w("    transfer_mechanism = EXCLUDED.transfer_mechanism,")
        w("    dpa_status = EXCLUDED.dpa_status, dpa_url = EXCLUDED.dpa_url,")
        w("    privacy_policy_url = EXCLUDED.privacy_policy_url,")
        w("    sets_cookies = EXCLUDED.sets_cookies, ai_role = EXCLUDED.ai_role,")
        w("    ai_conditional = EXCLUDED.ai_conditional,")
        w("    ai_note_en = EXCLUDED.ai_note_en, ai_note_fr = EXCLUDED.ai_note_fr,")
        w("    default_criticality = EXCLUDED.default_criticality,")
        w("    default_system_role = EXCLUDED.default_system_role,")
        w("    role_note_en = EXCLUDED.role_note_en,")
        w("    role_note_fr = EXCLUDED.role_note_fr,")
        w("    sort_order = EXCLUDED.sort_order, active = EXCLUDED.active;")

        for j, a in enumerate(v.get("activities", [])):
            acols = (
                "catalogue_id, name_en, name_fr, purpose_en, purpose_fr, legal_basis, "
                "data_subject_categories, data_categories, special_categories, "
                "art9_condition, retention_period_en, retention_period_fr, "
                "system_role, sort_order"
            )
            avals = ", ".join(_q(x) for x in [
                a["name_en"], a.get("name_fr"), a.get("purpose_en"), a.get("purpose_fr"),
                a.get("legal_basis"), a.get("data_subject_categories", []),
                a.get("data_categories", []), a.get("special_categories", []),
                a.get("art9_condition"), a.get("retention_period_en"),
                a.get("retention_period_fr"), a.get("system_role", "processor"), j,
            ])
            w(f"INSERT INTO vendor_catalogue_activities ({acols})")
            w(f"SELECT id, {avals} FROM vendor_catalogue WHERE key = {_q(v['key'])}")
            w("ON CONFLICT (catalogue_id, name_en) DO UPDATE SET")
            w("    name_fr = EXCLUDED.name_fr, purpose_en = EXCLUDED.purpose_en,")
            w("    purpose_fr = EXCLUDED.purpose_fr, legal_basis = EXCLUDED.legal_basis,")
            w("    data_subject_categories = EXCLUDED.data_subject_categories,")
            w("    data_categories = EXCLUDED.data_categories,")
            w("    special_categories = EXCLUDED.special_categories,")
            w("    art9_condition = EXCLUDED.art9_condition,")
            w("    retention_period_en = EXCLUDED.retention_period_en,")
            w("    retention_period_fr = EXCLUDED.retention_period_fr,")
            w("    system_role = EXCLUDED.system_role, sort_order = EXCLUDED.sort_order;")

        for pattern, match_type, confidence in v.get("domain_patterns", []):
            w("INSERT INTO vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)")
            w(f"SELECT id, {_q(pattern)}, {_q(match_type)}, {_q(confidence)} "
              f"FROM vendor_catalogue WHERE key = {_q(v['key'])}")
            w("ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET")
            w("    confidence = EXCLUDED.confidence;")

    w("")
    w("COMMIT;")
    w("")
    w("-- ── Verification ──────────────────────────────────────────────────────────")
    w("SELECT value_type, COUNT(*) FROM reference_values "
      "WHERE workspace_id IS NULL GROUP BY value_type ORDER BY value_type;")
    w("SELECT v.key, COUNT(a.id) AS activities FROM vendor_catalogue v")
    w("LEFT JOIN vendor_catalogue_activities a ON a.catalogue_id = v.id")
    w("GROUP BY v.key ORDER BY v.key;")
    w("")

    return "\n".join(out)


# ── Self-check ────────────────────────────────────────────────────────────
# Runs before emitting. Catches the seed referencing a vocabulary code that
# does not exist — which the database would also catch, but only after the
# migration has been pasted and half-applied.

def self_check() -> list[str]:
    errors: list[str] = []
    codes = {t: {e[0] for e in entries} for t, entries in VOCABULARIES.items()}

    for v in VENDOR_CATALOGUE:
        for field, vtype in (
            ("category", "system_category"),
            ("transfer_mechanism", "transfer_mechanism"),
            ("dpa_status", "dpa_status"),
            ("default_criticality", "criticality"),
            ("default_system_role", "system_role"),
            ("ai_role", "ai_role"),
        ):
            val = v.get(field)
            if val is not None and val not in codes[vtype]:
                errors.append(f"{v['key']}.{field}: unknown {vtype} {val!r}")

        for a in v.get("activities", []):
            if a.get("legal_basis") not in codes["legal_basis"]:
                errors.append(f"{v['key']}/{a['name_en']}: bad legal_basis")
            for field, vtype in (
                ("data_subject_categories", "data_subject_category"),
                ("data_categories", "data_category"),
                ("special_categories", "special_category"),
            ):
                for c in a.get(field, []):
                    if c not in codes[vtype]:
                        errors.append(f"{v['key']}/{a['name_en']}: unknown {vtype} {c!r}")
            # Mirrors the CHECK constraint, so a bad seed fails here rather
            # than halfway through pasting the file into the SQL editor.
            if a.get("special_categories") and not a.get("art9_condition"):
                errors.append(f"{v['key']}/{a['name_en']}: Art. 9 data without a condition")
            if a.get("art9_condition") and a["art9_condition"] not in codes["art9_condition"]:
                errors.append(f"{v['key']}/{a['name_en']}: unknown art9_condition")

    return errors


if __name__ == "__main__":
    import sys
    problems = self_check()
    if problems:
        for p in problems:
            print(f"SEED ERROR: {p}", file=sys.stderr)
        sys.exit(1)
    print(emit_sql())
