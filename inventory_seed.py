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

    # ── Retention basis (S26C) ────────────────────────────────────────────
    # Art. 30(1)(f) asks for the envisaged erasure time limits. The PERIOD is
    # the client's number, in retention_value; this vocabulary is the REASON.
    #
    # D-50: NO CODE STATES A PERIOD.
    #
    # Belgium is why. Art. III.86 of the Code de droit economique requires
    # accounting books to be kept seven years. The law of 20 November 2022
    # extended tax and VAT retention to ten years from 1 January 2023,
    # aligning it with the fraud limitation period. VAT revision on immovable
    # property runs longer again. Published sources disagree with each other
    # because they are describing different obligations — so a code reading
    # "accounting, 7 years" would be right under the CDE and wrong under the
    # CIR. Hence statutory_accounting and statutory_tax_vat are separate.
    #
    # D-51: notes are GENERIC. They describe the category and tell the client
    # to check the period that applies to them. They do not cite articles.
    # A cited note is RECOSA asserting what national law requires, inside a
    # filed register, in a product sold as a compliance tool — the same risk
    # class as D-42, and it needs counsel review before it ships.
    #
    # metadata carries:
    #   jurisdiction  — where the rule comes from; absent means general
    #   statutory     — imposed by law, as opposed to chosen or recommended.
    #                   CNIL's RH retention referentiel of 2 April 2026 draws
    #                   the same line between obligatory and recommended
    #                   durations, and readiness()/S26B need it to tell a
    #                   period a client may shorten from one it may not.
    #   requires_text — the form reveals the free-text field for this code
    "retention_basis": [
        ("statutory_social_documents",
         "Statutory — social documents",
         "Obligation légale — documents sociaux",
         "Employment records the law requires you to keep, such as the "
         "personnel register and individual accounts. Check the period that "
         "applies to your situation.",
         {"jurisdiction": ["BE"], "statutory": True},
         "Documents liés à l'emploi que la loi impose de conserver, tels que "
         "le registre du personnel et le compte individuel. Vérifiez le délai "
         "applicable à votre situation."),

        ("statutory_payroll",
         "Statutory — payroll records",
         "Obligation légale — documents de paie",
         "Pay slips, salary calculations and the supporting records "
         "legislation requires you to retain.",
         {"jurisdiction": ["BE", "FR"], "statutory": True},
         "Fiches de paie, calculs de rémunération et pièces justificatives "
         "que la législation impose de conserver."),

        ("statutory_accounting",
         "Statutory — accounting records",
         "Obligation légale — documents comptables",
         "Books and supporting records kept under accounting law. The "
         "accounting period may differ from the tax one — record them "
         "separately where they do.",
         {"jurisdiction": ["BE", "FR"], "statutory": True},
         "Livres et pièces justificatives conservés au titre du droit "
         "comptable. Le délai comptable peut différer du délai fiscal : "
         "enregistrez-les séparément le cas échéant."),

        ("statutory_tax_vat",
         "Statutory — tax and VAT records",
         "Obligation légale — documents fiscaux et TVA",
         "Records kept for tax or VAT purposes. This period is often longer "
         "than the accounting one and may be longer again for property.",
         {"jurisdiction": ["BE", "FR"], "statutory": True},
         "Documents conservés à des fins fiscales ou de TVA. Ce délai est "
         "souvent plus long que le délai comptable, et davantage encore pour "
         "les biens immobiliers."),

        ("statutory_health_safety",
         "Statutory — occupational health and safety",
         "Obligation légale — santé et sécurité au travail",
         "Records on workplace accidents, exposure or occupational health "
         "that legislation requires you to keep.",
         {"jurisdiction": ["BE", "FR"], "statutory": True},
         "Documents relatifs aux accidents du travail, aux expositions ou à "
         "la santé au travail que la législation impose de conserver."),

        ("statutory_other",
         "Other statutory requirement",
         "Autre obligation légale",
         "A retention period set by legislation not covered by the options "
         "above. Say which in the activity notes.",
         {"statutory": True},
         "Un délai de conservation fixé par une législation non couverte par "
         "les options ci-dessus. Précisez laquelle dans les notes."),

        ("limitation_period",
         "Limitation period for potential claims",
         "Délai de prescription applicable",
         "Kept so the data is still available if a claim is brought. Use the "
         "limitation period that applies to the relationship.",
         {},
         "Conservé afin que les données restent disponibles en cas de "
         "réclamation. Utilisez le délai de prescription applicable à la "
         "relation concernée."),

        ("contract_duration",
         "Duration of the contractual relationship",
         "Durée de la relation contractuelle",
         "Kept for as long as the relationship lasts. Usually the ACTIVE "
         "phase, with an archive phase recorded separately below.",
         {},
         "Conservé pendant toute la durée de la relation. Généralement la "
         "phase ACTIVE, la phase d'archivage étant enregistrée séparément "
         "ci-dessous."),

        ("contract_plus_limitation",
         "Contract duration plus limitation period",
         "Durée du contrat, puis délai de prescription",
         "Use only where the two phases genuinely cannot be separated. "
         "Recording them as an active and an archive phase is clearer.",
         {},
         "À n'utiliser que si les deux phases ne peuvent réellement pas être "
         "distinguées. Les enregistrer comme phase active et phase "
         "d'archivage est plus clair."),

        ("until_procedure_concluded",
         "Until the procedure or investigation concludes",
         "Jusqu'à la clôture de la procédure",
         "For reports, investigations and disputes, where the end point is "
         "the final decision rather than a fixed period.",
         {},
         "Pour les signalements, enquêtes et litiges, dont le terme est la "
         "décision définitive plutôt qu'un délai fixe."),

        ("consent_until_withdrawn",
         "Until consent is withdrawn",
         "Jusqu'au retrait du consentement",
         "Only where consent is the legal basis. If the basis is anything "
         "else, withdrawal does not end the retention.",
         {},
         "Uniquement lorsque le consentement est la base légale. Si la base "
         "est autre, le retrait ne met pas fin à la conservation."),

        ("regulatory_guidance",
         "Period recommended by supervisory authority guidance",
         "Durée recommandée par l'autorité de contrôle",
         "A period a supervisory authority recommends rather than one the law "
         "imposes. Name the guidance in the activity notes.",
         {},
         "Une durée recommandée par une autorité de contrôle plutôt "
         "qu'imposée par la loi. Indiquez la référence dans les notes."),

        ("business_need_reviewed",
         "Business need, reviewed periodically",
         "Besoin opérationnel, réexaminé périodiquement",
         "No legal requirement — the period is your own decision, and the "
         "review is what makes it defensible. State a period, not 'as long "
         "as necessary'.",
         {},
         "Aucune exigence légale : le délai est votre propre décision, et le "
         "réexamen est ce qui la rend défendable. Indiquez une durée, et non "
         "« aussi longtemps que nécessaire »."),

        ("other",
         "Other — describe below",
         "Autre — à préciser",
         "Use only when no option above fits. A described reason is "
         "acceptable; a blank one is not.",
         {"requires_text": True},
         "À n'utiliser que si aucune option ci-dessus ne convient. Un motif "
         "décrit est acceptable ; un motif vide ne l'est pas."),
    ],

    # ── Retention unit ────────────────────────────────────────────────────
    # SEEDED FOR LABELS ONLY — never read to render a period.
    #
    # format_retention() carries its own table because "1 an" / "2 ans" needs
    # singular/plural agreement that one label column cannot express, and
    # because a client must never be able to add a unit. These rows exist so
    # the form's dropdown and the admin vocabulary page show the same set the
    # CHECK constraint enforces.
    "retention_unit": [
        ("days",       "Days",       "Jours",       None, {}, None),
        ("months",     "Months",     "Mois",        None, {}, None),
        ("years",      "Years",      "Années",      None, {}, None),
        ("indefinite", "Indefinite", "Indéterminée",
         "No fixed end point. Requires a basis explaining why, and is the "
         "hardest period to defend to a supervisory authority.",
         {},
         "Pas de terme fixe. Exige un motif expliquant pourquoi, et constitue "
         "la durée la plus difficile à justifier devant une autorité de "
         "contrôle."),
    ],

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
                # S26C. Structured, not prose. 14 months is Google's own
                # default retention setting — a vendor fact, which is why the
                # catalogue states it at all.
                #
                # No basis code. WHY a client keeps analytics data 14 months is
                # a client fact nobody has decided yet, and no code fits
                # honestly: business_need_reviewed would assert a periodic
                # review that is not happening, and regulatory_guidance would
                # be wrong because CNIL's cookie guidance is 13 months, not 14.
                # Left null so it surfaces as a gap the client fills, which is
                # the same rule the catalogue already applies to every period a
                # vendor does not determine.
                "retention_value": 14,
                "retention_unit": "months",
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
                # Client policy, not a Microsoft fact. Blank by principle.
                "retention_value": None,
                "retention_unit": None,
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
                # Not a period at all — a pointer to a schedule the client
                # may not have written. Blank by principle.
                "retention_value": None,
                "retention_unit": None,
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
                # Deliberately blank. Personnel-file retention is set by
                # national law, not by Microsoft — 5 years in Belgium, other
                # periods elsewhere — so a catalogue default would be wrong
                # for some clients. See CATALOGUE_PRINCIPLES["retention"].
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
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
                # Client policy, not a Microsoft fact. Blank by principle.
                "retention_value": None,
                "retention_unit": None,
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
                # Belgian social-document retention is 5 years, but a French
                # client on a French payroll bureau has a different period.
                # Statutory, therefore not a vendor default.
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    # ── Marketing and CRM ─────────────────────────────────────────────────

    {
        "key": "hubspot",
        "name": "HubSpot",
        "vendor_legal_name": "HubSpot Ireland Limited",
        "category": "crm_marketing",
        "establishment_country": "IE",
        "processing_country": "US",
        # EU data hosting is available on some plans. SCCs are the safe
        # default for a client who has not checked which region their
        # portal sits in.
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://legal.hubspot.com/dpa",
        "privacy_policy_url": "https://legal.hubspot.com/privacy-policy",
        "sets_cookies": True,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "medium",
        "default_system_role": "processor",
        "role_note_en": (
            "If your portal is hosted in the EU region, the transfer basis may "
            "be 'no transfer outside the EEA'. Check your account settings."
        ),
        "role_note_fr": (
            "Si votre portail est hébergé dans la région UE, la base de "
            "transfert peut être « aucun transfert hors EEE ». Vérifiez les "
            "paramètres de votre compte."
        ),
        "domain_patterns": [
            ("hs-scripts.com", "script_src", "high"),
            ("hubspot.com", "domain", "medium"),
            ("__hstc", "cookie_name", "high"),
        ],
        "activities": [
            {
                "name_en": "Customer and prospect management",
                "name_fr": "Gestion des clients et prospects",
                "purpose_en": "Recording and managing commercial relationships",
                "purpose_fr": "Enregistrement et gestion des relations commerciales",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["customers", "prospects", "supplier_contacts"],
                "data_categories": ["identity", "contact", "employment",
                                    "contractual", "usage_behavioural"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
            {
                "name_en": "Marketing email",
                "name_fr": "Emailing marketing",
                "purpose_en": "Sending commercial communications to contacts who opted in",
                "purpose_fr": "Envoi de communications commerciales aux contacts inscrits",
                "legal_basis": "consent",
                "data_subject_categories": ["prospects", "customers"],
                "data_categories": ["identity", "contact", "marketing_preferences",
                                    "usage_behavioural"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "brevo",
        "name": "Brevo",
        "vendor_legal_name": "Brevo SAS",
        "category": "email_comms",
        "establishment_country": "FR",
        "processing_country": "FR",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": "https://www.brevo.com/legal/termsofuse/",
        "privacy_policy_url": "https://www.brevo.com/legal/privacypolicy/",
        # Brevo rewrites links for click tracking on transactional sends and
        # this cannot be disabled. Anonymous tracking is the mitigation.
        "sets_cookies": True,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "medium",
        "default_system_role": "processor",
        "role_note_en": (
            "Click tracking rewrites links through a Brevo domain and cannot "
            "be turned off for transactional email. Enabling anonymous "
            "tracking in Brevo's settings stops clicks being tied to a contact."
        ),
        "role_note_fr": (
            "Le suivi des clics réécrit les liens via un domaine Brevo et ne "
            "peut pas être désactivé pour les emails transactionnels. Le suivi "
            "anonyme dans les paramètres Brevo évite de lier les clics à un contact."
        ),
        "domain_patterns": [
            ("sendinblue.com", "domain", "medium"),
            ("sibautomation.com", "script_src", "high"),
        ],
        "activities": [
            {
                "name_en": "Transactional email",
                "name_fr": "Emails transactionnels",
                "purpose_en": "Sending service notifications triggered by user actions",
                "purpose_fr": "Envoi de notifications de service déclenchées par l'utilisateur",
                "legal_basis": "contract",
                "data_subject_categories": ["customers"],
                "data_categories": ["identity", "contact"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "meta_pixel",
        "name": "Meta Pixel",
        "vendor_legal_name": "Meta Platforms Ireland Limited",
        "category": "crm_marketing",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://www.facebook.com/legal/terms/dataprocessing",
        "privacy_policy_url": "https://www.facebook.com/privacy/policy/",
        "sets_cookies": True,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "low",
        # Joint controller, not processor. Following Fashion ID (C-40/17),
        # the site operator and the platform jointly determine the purposes
        # of the collection stage, and Meta's own controller addendum says
        # so. This is the entry that exercises the vocabulary.
        "default_system_role": "joint_controller",
        "role_note_en": (
            "Meta is a joint controller for the collection and transmission "
            "stage, not a processor. You need a joint controller arrangement "
            "under Art. 26 and your privacy notice must say so."
        ),
        "role_note_fr": (
            "Meta est responsable conjoint pour la collecte et la "
            "transmission, et non sous-traitant. Un accord de responsabilité "
            "conjointe (art. 26) est requis et votre politique de "
            "confidentialité doit le mentionner."
        ),
        "domain_patterns": [
            ("connect.facebook.net", "script_src", "high"),
            ("facebook.com/tr", "domain", "high"),
            ("_fbp", "cookie_name", "high"),
        ],
        "activities": [
            {
                "name_en": "Advertising measurement and audiences",
                "name_fr": "Mesure publicitaire et audiences",
                "purpose_en": "Measuring advertising performance and building audiences",
                "purpose_fr": "Mesure des performances publicitaires et création d'audiences",
                "legal_basis": "consent",
                "data_subject_categories": ["website_visitors", "prospects"],
                "data_categories": ["device_technical", "usage_behavioural"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "joint_controller",
            },
        ],
    },

    {
        "key": "linkedin_insight",
        "name": "LinkedIn Insight Tag",
        "vendor_legal_name": "LinkedIn Ireland Unlimited Company",
        "category": "crm_marketing",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://legal.linkedin.com/dpa",
        "privacy_policy_url": "https://www.linkedin.com/legal/privacy-policy",
        "sets_cookies": True,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "low",
        "default_system_role": "joint_controller",
        "role_note_en": (
            "LinkedIn operates as a joint controller for conversion tracking "
            "and audience building. An Art. 26 arrangement applies."
        ),
        "role_note_fr": (
            "LinkedIn agit en responsable conjoint pour le suivi des "
            "conversions et la constitution d'audiences. Un accord au titre "
            "de l'art. 26 s'applique."
        ),
        "domain_patterns": [
            ("snap.licdn.com", "script_src", "high"),
            ("li_sugr", "cookie_name", "medium"),
        ],
        "activities": [
            {
                "name_en": "Advertising conversion tracking",
                "name_fr": "Suivi des conversions publicitaires",
                "purpose_en": "Measuring campaign conversions and building audiences",
                "purpose_fr": "Mesure des conversions et création d'audiences",
                "legal_basis": "consent",
                "data_subject_categories": ["website_visitors", "prospects"],
                "data_categories": ["device_technical", "usage_behavioural", "employment"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "joint_controller",
            },
        ],
    },

    # ── Payments ──────────────────────────────────────────────────────────

    {
        "key": "stripe",
        "name": "Stripe",
        "vendor_legal_name": "Stripe Payments Europe, Limited",
        "category": "payments",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://stripe.com/legal/dpa",
        "privacy_policy_url": "https://stripe.com/privacy",
        "sets_cookies": True,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "high",
        "default_system_role": "processor",
        # The nuance that catches people out: Stripe is a processor for the
        # payment you asked it to take, and an independent controller for
        # its own anti-money-laundering and fraud duties. Both are true at
        # once, and only the first belongs in your DPA.
        "role_note_en": (
            "Stripe acts as your processor for payment processing, but as an "
            "independent controller for its own fraud prevention and "
            "anti-money-laundering obligations. Record the processor role here."
        ),
        "role_note_fr": (
            "Stripe agit comme sous-traitant pour le traitement des paiements, "
            "mais comme responsable indépendant pour ses propres obligations "
            "de lutte contre la fraude et le blanchiment. Enregistrez ici le "
            "rôle de sous-traitant."
        ),
        "domain_patterns": [
            ("js.stripe.com", "script_src", "high"),
            ("__stripe_mid", "cookie_name", "high"),
        ],
        "activities": [
            {
                "name_en": "Payment processing",
                "name_fr": "Traitement des paiements",
                "purpose_en": "Taking and reconciling customer payments",
                "purpose_fr": "Encaissement et rapprochement des paiements clients",
                "legal_basis": "contract",
                "data_subject_categories": ["customers"],
                "data_categories": ["identity", "contact", "financial", "transaction"],
                "special_categories": [],
                "art9_condition": None,
                # Accounting retention is statutory and differs by country
                # (7 years in Belgium, 10 in France for some records).
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "mollie",
        "name": "Mollie",
        "vendor_legal_name": "Mollie B.V.",
        "category": "payments",
        "establishment_country": "NL",
        "processing_country": "NL",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": "https://www.mollie.com/legal/data-processing-agreement",
        "privacy_policy_url": "https://www.mollie.com/privacy",
        "sets_cookies": False,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "high",
        "default_system_role": "processor",
        "role_note_en": (
            "As with other payment providers, Mollie is an independent "
            "controller for its own regulatory obligations alongside its "
            "processor role for your transactions."
        ),
        "role_note_fr": (
            "Comme les autres prestataires de paiement, Mollie est "
            "responsable indépendant pour ses obligations réglementaires, en "
            "plus de son rôle de sous-traitant pour vos transactions."
        ),
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Payment processing",
                "name_fr": "Traitement des paiements",
                "purpose_en": "Taking and reconciling customer payments",
                "purpose_fr": "Encaissement et rapprochement des paiements clients",
                "legal_basis": "contract",
                "data_subject_categories": ["customers"],
                "data_categories": ["identity", "contact", "financial", "transaction"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    # ── Accounting and ERP ────────────────────────────────────────────────

    {
        "key": "odoo",
        "name": "Odoo",
        "vendor_legal_name": "Odoo S.A.",
        "category": "accounting_finance",
        "establishment_country": "BE",
        "processing_country": "EU",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": "https://www.odoo.com/gdpr",
        "privacy_policy_url": "https://www.odoo.com/privacy",
        "sets_cookies": False,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "high",
        "default_system_role": "processor",
        "role_note_en": (
            "Odoo Online hosts in the EU by default. A self-hosted or "
            "partner-hosted instance may sit elsewhere — record where yours runs."
        ),
        "role_note_fr": (
            "Odoo Online héberge par défaut dans l'UE. Une instance "
            "auto-hébergée ou hébergée par un partenaire peut se trouver "
            "ailleurs — indiquez où se trouve la vôtre."
        ),
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Invoicing and accounts receivable",
                "name_fr": "Facturation et comptabilité clients",
                "purpose_en": "Issuing invoices and tracking payment",
                "purpose_fr": "Émission des factures et suivi des paiements",
                "legal_basis": "legal_obligation",
                "data_subject_categories": ["customers", "supplier_contacts"],
                "data_categories": ["identity", "contact", "financial",
                                    "transaction", "contractual"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "exact_online",
        "name": "Exact Online",
        "vendor_legal_name": "Exact Group B.V.",
        "category": "accounting_finance",
        "establishment_country": "NL",
        "processing_country": "NL",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": None,
        "privacy_policy_url": "https://www.exact.com/privacy-statement",
        "sets_cookies": False,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "high",
        "default_system_role": "processor",
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Bookkeeping and financial records",
                "name_fr": "Comptabilité et pièces financières",
                "purpose_en": "Maintaining statutory accounting records",
                "purpose_fr": "Tenue des documents comptables obligatoires",
                "legal_basis": "legal_obligation",
                "data_subject_categories": ["customers", "supplier_contacts", "employees"],
                "data_categories": ["identity", "contact", "financial", "transaction"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    # ── Hosting and infrastructure ────────────────────────────────────────

    {
        "key": "ovhcloud",
        "name": "OVHcloud",
        "vendor_legal_name": "OVH SAS",
        "category": "hosting_infrastructure",
        "establishment_country": "FR",
        "processing_country": "FR",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": "https://www.ovhcloud.com/en/terms-and-conditions/contracts/",
        "privacy_policy_url": "https://www.ovhcloud.com/en/personal-data-protection/",
        "sets_cookies": False,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "critical",
        "default_system_role": "processor",
        "role_note_en": (
            "Confirm which datacentre region your services run in. OVHcloud "
            "operates outside the EU as well as inside it."
        ),
        "role_note_fr": (
            "Vérifiez la région du datacentre utilisé. OVHcloud opère "
            "également hors de l'UE."
        ),
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Website and application hosting",
                "name_fr": "Hébergement du site et des applications",
                "purpose_en": "Running the infrastructure your services depend on",
                "purpose_fr": "Exploitation de l'infrastructure de vos services",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["website_visitors", "customers"],
                "data_categories": ["device_technical", "usage_behavioural"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "aws",
        "name": "Amazon Web Services",
        "vendor_legal_name": "Amazon Web Services EMEA SARL",
        "category": "hosting_infrastructure",
        "establishment_country": "LU",
        # Region-dependent. SCCs are the conservative default because AWS
        # support and some managed services can reach across regions even
        # when the workload itself is pinned to eu-west-1.
        "processing_country": "EU",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://aws.amazon.com/compliance/gdpr-center/",
        "privacy_policy_url": "https://aws.amazon.com/privacy/",
        "sets_cookies": False,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "critical",
        "default_system_role": "processor",
        "role_note_en": (
            "Record the specific region your workloads run in. Pinning "
            "storage to an EU region does not by itself remove every transfer "
            "— support access and some managed services can still cross."
        ),
        "role_note_fr": (
            "Indiquez la région où s'exécutent vos charges de travail. "
            "Limiter le stockage à une région UE ne supprime pas à soi seul "
            "tout transfert — l'accès support et certains services gérés "
            "peuvent encore en générer."
        ),
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Cloud infrastructure and storage",
                "name_fr": "Infrastructure et stockage cloud",
                "purpose_en": "Running and storing your applications and data",
                "purpose_fr": "Exécution et stockage de vos applications et données",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["customers", "website_visitors", "employees"],
                "data_categories": ["identity", "contact", "device_technical"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },

    # ── Productivity ──────────────────────────────────────────────────────

    {
        "key": "google_workspace",
        "name": "Google Workspace",
        "vendor_legal_name": "Google Ireland Limited",
        "category": "productivity_storage",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://workspace.google.com/terms/dpa_terms.html",
        "privacy_policy_url": "https://policies.google.com/privacy",
        "sets_cookies": False,
        "ai_role": "deployer",
        "ai_conditional": True,
        "ai_note_en": (
            "Set to deployer only if Gemini for Workspace is licensed and "
            "enabled. Otherwise leave as 'not an AI system'."
        ),
        "ai_note_fr": (
            "Sélectionnez « déployeur » uniquement si Gemini for Workspace est "
            "sous licence et activé. Sinon, laissez « pas un système d'IA »."
        ),
        "default_criticality": "critical",
        "default_system_role": "processor",
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Business email and calendaring",
                "name_fr": "Messagerie professionnelle et agenda",
                "purpose_en": "Internal and external business correspondence",
                "purpose_fr": "Correspondance professionnelle interne et externe",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["employees", "customers", "prospects",
                                            "supplier_contacts"],
                "data_categories": ["identity", "contact", "communications_content"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
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
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
            {
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
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "slack",
        "name": "Slack",
        "vendor_legal_name": "Slack Technologies Limited",
        "category": "email_comms",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://slack.com/trust/compliance/data-processing-addendum",
        "privacy_policy_url": "https://slack.com/trust/privacy/privacy-policy",
        "sets_cookies": False,
        "ai_role": "deployer",
        "ai_conditional": True,
        "ai_note_en": (
            "Set to deployer only if Slack AI is enabled on your workspace."
        ),
        "ai_note_fr": (
            "Sélectionnez « déployeur » uniquement si Slack AI est activé sur "
            "votre espace de travail."
        ),
        "default_criticality": "medium",
        "default_system_role": "processor",
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "Internal collaboration and messaging",
                "name_fr": "Collaboration et messagerie interne",
                "purpose_en": "Team communication and coordination",
                "purpose_fr": "Communication et coordination d'équipe",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["employees", "contractors"],
                "data_categories": ["identity", "contact", "communications_content"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },

    # ── Support ───────────────────────────────────────────────────────────

    {
        "key": "zendesk",
        "name": "Zendesk",
        "vendor_legal_name": "Zendesk International Ltd.",
        "category": "support_ticketing",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://www.zendesk.com/company/data-processing-form/",
        "privacy_policy_url": "https://www.zendesk.com/company/privacy-and-data-protection/",
        "sets_cookies": True,
        "ai_role": "none",
        "ai_conditional": False,
        "default_criticality": "medium",
        "default_system_role": "processor",
        "role_note_en": (
            "Support tickets frequently contain whatever the customer chose to "
            "put in them, including health or financial details. Review "
            "whether special category data reaches this system in practice."
        ),
        "role_note_fr": (
            "Les tickets de support contiennent souvent tout ce que le client "
            "y a écrit, y compris des données de santé ou financières. "
            "Vérifiez si des données sensibles y parviennent en pratique."
        ),
        "domain_patterns": [
            ("zdassets.com", "script_src", "high"),
        ],
        "activities": [
            {
                "name_en": "Customer support",
                "name_fr": "Support client",
                "purpose_en": "Handling and tracking customer enquiries",
                "purpose_fr": "Traitement et suivi des demandes clients",
                "legal_basis": "contract",
                "data_subject_categories": ["customers"],
                "data_categories": ["identity", "contact", "communications_content",
                                    "contractual"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },

    # ── HR and payroll ────────────────────────────────────────────────────

    {
        "key": "partena",
        "name": "Partena Professional",
        "vendor_legal_name": "Partena Professional",
        "category": "hr_payroll",
        "establishment_country": "BE",
        "processing_country": "BE",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": None,
        "privacy_policy_url": "https://www.partena-professional.be/en/privacy-policy",
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
                "special_categories": ["health"],
                "art9_condition": "employment_social_security",
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "payfit",
        "name": "PayFit",
        "vendor_legal_name": "PayFit SAS",
        "category": "hr_payroll",
        "establishment_country": "FR",
        "processing_country": "FR",
        "transfer_mechanism": "none_eea",
        "dpa_status": "signed",
        "dpa_url": None,
        "privacy_policy_url": "https://payfit.com/fr/politique-de-confidentialite/",
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
                "special_categories": ["health"],
                "art9_condition": "employment_social_security",
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": True,
                "system_role": "processor",
            },
        ],
    },

    # ── AI assistants ─────────────────────────────────────────────────────
    # Unconditional deployers, unlike the AI features bundled into
    # productivity suites: nobody has ChatGPT or Claude switched off by
    # default, so these attach AI Act deployer duties from the moment the
    # client confirms they use them.

    {
        "key": "openai",
        "name": "ChatGPT (OpenAI)",
        "vendor_legal_name": "OpenAI Ireland Limited",
        "category": "ai_assistant",
        "establishment_country": "IE",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "signed",
        "dpa_url": "https://openai.com/policies/data-processing-addendum/",
        "privacy_policy_url": "https://openai.com/policies/privacy-policy/",
        "sets_cookies": False,
        "ai_role": "deployer",
        "ai_conditional": False,
        "ai_note_en": (
            "As a deployer you have transparency duties under Art. 50 where "
            "outputs reach customers, and staff-training duties under Art. 4."
        ),
        "ai_note_fr": (
            "En tant que déployeur, vous avez des obligations de transparence "
            "(art. 50) lorsque les résultats atteignent vos clients, et des "
            "obligations de formation du personnel (art. 4)."
        ),
        "default_criticality": "low",
        "default_system_role": "processor",
        "role_note_en": (
            "Consumer ChatGPT accounts are not covered by a business DPA and "
            "may train on your inputs. Only the Team, Enterprise and API "
            "tiers carry processor terms — record which one you actually use."
        ),
        "role_note_fr": (
            "Les comptes ChatGPT grand public ne sont pas couverts par un DPA "
            "professionnel et peuvent servir à l'entraînement. Seules les "
            "offres Team, Enterprise et API prévoient des clauses de "
            "sous-traitance — indiquez celle que vous utilisez réellement."
        ),
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "AI-assisted drafting and analysis",
                "name_fr": "Rédaction et analyse assistées par IA",
                "purpose_en": "Drafting, summarising and analysing business content",
                "purpose_fr": "Rédaction, synthèse et analyse de contenus professionnels",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["employees", "customers"],
                "data_categories": ["communications_content"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },

    {
        "key": "anthropic_claude",
        "name": "Claude (Anthropic)",
        # Anthropic contracts through more than one entity depending on plan
        # and region. Left for the client to confirm from their own order
        # form rather than asserted here.
        "vendor_legal_name": "Anthropic PBC",
        "category": "ai_assistant",
        "establishment_country": "US",
        "processing_country": "US",
        "transfer_mechanism": "scc",
        "dpa_status": "unknown",
        "dpa_url": None,
        "privacy_policy_url": "https://www.anthropic.com/legal/privacy",
        "sets_cookies": False,
        "ai_role": "deployer",
        "ai_conditional": False,
        "ai_note_en": (
            "As a deployer you have transparency duties under Art. 50 where "
            "outputs reach customers, and staff-training duties under Art. 4."
        ),
        "ai_note_fr": (
            "En tant que déployeur, vous avez des obligations de transparence "
            "(art. 50) lorsque les résultats atteignent vos clients, et des "
            "obligations de formation du personnel (art. 4)."
        ),
        "default_criticality": "low",
        "default_system_role": "processor",
        "role_note_en": (
            "Confirm the contracting entity and whether a processing "
            "agreement is in place — this varies by plan and region, so no "
            "default is asserted here."
        ),
        "role_note_fr": (
            "Confirmez l'entité contractante et l'existence d'un accord de "
            "sous-traitance — cela varie selon l'offre et la région, aucune "
            "valeur par défaut n'est donc proposée ici."
        ),
        "domain_patterns": [],
        "activities": [
            {
                "name_en": "AI-assisted drafting and analysis",
                "name_fr": "Rédaction et analyse assistées par IA",
                "purpose_en": "Drafting, summarising and analysing business content",
                "purpose_fr": "Rédaction, synthèse et analyse de contenus professionnels",
                "legal_basis": "legitimate_interests",
                "data_subject_categories": ["employees", "customers"],
                "data_categories": ["communications_content"],
                "special_categories": [],
                "art9_condition": None,
                "retention_value": None,
                "retention_unit": None,
                "retention_is_statutory": False,
                "system_role": "processor",
            },
        ],
    },
]


# ── Catalogue principles ──────────────────────────────────────────────────
#
# The rules behind the catalogue defaults, written down where they can be
# read rather than inferred from the values themselves. Two audiences:
#
#   audience="client"   rendered on the inventory page, so a client can see
#                       why a field is pre-filled or deliberately blank
#   audience="internal" the reasoning behind a design decision, kept beside
#                       the content it governs so it is findable later
#
# Both are seeded into catalogue_principles and read at runtime, so revising
# a principle is a seed re-run rather than a redeploy.

CATALOGUE_PRINCIPLES = [
    {
        "key": "defaults_not_facts",
        "audience": "client",
        "title_en": "Catalogue values are starting points, not findings",
        "title_fr": "Les valeurs du catalogue sont des points de départ",
        "body_en": (
            "When you add a tool from our list, we pre-fill what is typically "
            "true of that vendor. Your own contract, region and configuration "
            "override it. Nothing is recorded as fact until you confirm it."
        ),
        "body_fr": (
            "Lorsque vous ajoutez un outil depuis notre liste, nous "
            "pré-remplissons ce qui est généralement vrai pour ce "
            "fournisseur. Votre contrat, votre région et votre configuration "
            "priment. Rien n'est enregistré comme fait tant que vous ne "
            "l'avez pas confirmé."
        ),
        "rationale_en": (
            "A catalogue row is a compliance assertion made on the client's "
            "behalf. Framing it as a default rather than a finding is what "
            "makes it defensible when a vendor changes its terms."
        ),
    },
    {
        "key": "retention",
        "audience": "client",
        "title_en": "Retention periods come from the law, not the vendor",
        "title_fr": "Les durées de conservation viennent de la loi",
        "body_en": (
            "We pre-fill a retention period only where the vendor genuinely "
            "determines it — an analytics tool's own data expiry, for "
            "example. Where the period is set by national law, such as "
            "payroll and accounting records, we leave it blank for you to "
            "complete, because it differs between Belgium and France."
        ),
        "body_fr": (
            "Nous pré-remplissons une durée de conservation uniquement "
            "lorsque le fournisseur la détermine réellement — par exemple "
            "l'expiration des données d'un outil d'analyse. Lorsque la durée "
            "est fixée par la loi nationale, comme pour la paie et la "
            "comptabilité, nous la laissons vide car elle diffère entre la "
            "Belgique et la France."
        ),
        "rationale_en": (
            "The first draft carried '5 years after end of employment' on the "
            "Microsoft 365 HR activity. That is Belgian social-document law, "
            "not a Microsoft fact, and shipping it to a French client would "
            "put a wrong period into a filed RoPA."
        ),
    },
    {
        "key": "processor_default",
        "audience": "client",
        "title_en": "Processor by default, joint controller where it is arguable",
        "title_fr": "Sous-traitant par défaut, responsable conjoint si discutable",
        "body_en": (
            "Most vendors act as your processor. Advertising and social "
            "platforms are different: following the Fashion ID judgment, you "
            "and the platform jointly decide the purpose of the data "
            "collection, which needs an Art. 26 arrangement. Where the "
            "position is contested we say so rather than choosing for you."
        ),
        "body_fr": (
            "La plupart des fournisseurs agissent comme sous-traitants. Les "
            "plateformes publicitaires et sociales font exception : depuis "
            "l'arrêt Fashion ID, vous et la plateforme déterminez "
            "conjointement la finalité de la collecte, ce qui exige un accord "
            "au titre de l'art. 26. Lorsque la qualification est discutée, "
            "nous le signalons plutôt que de choisir à votre place."
        ),
        "rationale_en": (
            "Meta Pixel and LinkedIn Insight Tag ship as joint_controller; "
            "Google Analytics ships as processor with the counter-argument "
            "surfaced, because the supervisory authorities have not settled it."
        ),
    },
    {
        "key": "ai_off_by_default",
        "audience": "client",
        "title_en": "AI features are assumed off until you say otherwise",
        "title_fr": "Les fonctions d'IA sont supposées désactivées",
        "body_en": (
            "Where an AI capability depends on a licence or a setting — "
            "Copilot in Microsoft 365, Gemini in Google Workspace — we record "
            "the tool as not an AI system and ask you. Dedicated AI tools such "
            "as ChatGPT or Claude are recorded as AI from the start."
        ),
        "body_fr": (
            "Lorsqu'une fonction d'IA dépend d'une licence ou d'un paramètre — "
            "Copilot dans Microsoft 365, Gemini dans Google Workspace — nous "
            "enregistrons l'outil comme n'étant pas un système d'IA et nous "
            "vous posons la question. Les outils d'IA dédiés comme ChatGPT ou "
            "Claude sont enregistrés comme tels d'emblée."
        ),
        "rationale_en": (
            "Assuming Copilot is enabled would attach AI Act deployer duties "
            "to a tenant that has never touched it. An over-broad compliance "
            "obligation is still a wrong answer."
        ),
    },
    {
        "key": "gap_vs_error",
        "audience": "client",
        "title_en": "An unanswered question is a gap, not a mistake",
        "title_fr": "Une question sans réponse est une lacune, pas une erreur",
        "body_en": (
            "Fields left as 'not yet established' are recorded as gaps and "
            "shown in your readiness figures. We only block you where the "
            "record would otherwise be wrong — for example, special category "
            "data with no Art. 9(2) condition, or a claim of no international "
            "transfer alongside a non-EEA country."
        ),
        "body_fr": (
            "Les champs laissés « à déterminer » sont enregistrés comme "
            "lacunes et apparaissent dans vos indicateurs. Nous ne bloquons "
            "que lorsque le registre serait sinon inexact — par exemple des "
            "données sensibles sans condition de l'art. 9(2), ou l'absence "
            "déclarée de transfert avec un pays hors EEE."
        ),
        "rationale_en": (
            "Blocking on incompleteness produces abandoned forms. Blocking on "
            "contradiction prevents a document that is evidence against the "
            "client."
        ),
    },
    {
        "key": "deleting_a_system",
        "audience": "client",
        "title_en": "Removing a tool keeps the record of what it did",
        "title_fr": "Supprimer un outil conserve le registre associé",
        "body_en": (
            "Deleting a system unlinks it from your processing activities but "
            "leaves those activities in place. Stopping use of a tool does not "
            "erase the fact that the processing happened."
        ),
        "body_fr": (
            "La suppression d'un système le dissocie de vos traitements mais "
            "conserve ces traitements. Cesser d'utiliser un outil n'efface pas "
            "le fait que le traitement a eu lieu."
        ),
        "rationale_en": (
            "The join cascades, the activities do not. A client who swaps "
            "payroll providers should not silently lose their payroll RoPA row."
        ),
    },
    {
        "key": "cookie_detail",
        "audience": "client",
        "title_en": "Cookies are recorded per vendor for now",
        "title_fr": "Les cookies sont enregistrés par fournisseur",
        "body_en": (
            "We record which vendors set cookies, not the individual cookie "
            "names and durations. Those are impractical to enter by hand and "
            "will be filled automatically once website scanning is available."
        ),
        "body_fr": (
            "Nous enregistrons les fournisseurs qui déposent des cookies, "
            "sans détailler chaque nom et durée. Ces informations sont peu "
            "praticables à saisir manuellement et seront complétées "
            "automatiquement dès que l'analyse de site sera disponible."
        ),
        "rationale_en": (
            "Vendor-level detail is enough for the S25 Cookie Policy vendor "
            "table. Cookie-level rows arrive with the S41 scanner."
        ),
    },
    {
        "key": "append_only_vocabulary",
        "audience": "internal",
        "title_en": "Vocabulary codes are append-only",
        "title_fr": None,
        "body_en": (
            "Never rename or delete a reference code. Client rows hold them as "
            "plain text in TEXT[] columns, so a rename orphans live compliance "
            "data and only the orphan check would notice. Retire a term by "
            "setting active = False."
        ),
        "body_fr": None,
        "rationale_en": (
            "The cost of the denormalised array columns. Accepted because "
            "normalising would turn one RoPA row into three joins."
        ),
    },
    {
        "key": "authored_in_python_served_from_postgres",
        "audience": "internal",
        "title_en": "Reference data is authored in Python, served from Postgres",
        "title_fr": None,
        "body_en": (
            "inventory_seed.py is the authored source and is never read at "
            "runtime; inventory.py reads the tables. Authoring wants a "
            "reviewable diff, serving wants a queryable table with per-language "
            "labels and per-workspace rows."
        ),
        "body_fr": None,
        "rationale_en": (
            "Three roadmap items force the Postgres side: the S41 scanner "
            "resolves domains by query, labels need translating, and S45 "
            "Enterprise taxonomies are per-workspace by definition."
        ),
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
        for i, entry in enumerate(entries):
            # S26C: the tuple grew a sixth element, note_fr.
            #
            # reference_values has carried note_fr since the table was created
            # and get_vocabulary() selects it, but nothing ever wrote it — so
            # note_for(..., lang="fr") silently fell back to English for every
            # code. Invisible while notes were unused; not invisible once the
            # activity form shows them beside a French label.
            #
            # Read positionally with a default rather than by widening every
            # existing 5-tuple: 200-odd entries edited to add a trailing None
            # is 200 chances to shift a column.
            code, en, fr, note_en, meta = entry[:5]
            note_fr = entry[5] if len(entry) > 5 else None
            w(
                "INSERT INTO reference_values "
                "(value_type, code, workspace_id, label_en, label_fr, "
                "note_en, note_fr, metadata, sort_order, active)"
            )
            w(
                f"VALUES ({_q(vtype)}, {_q(code)}, NULL, {_q(en)}, {_q(fr)}, "
                f"{_q(note_en)}, {_q(note_fr)}, {_q(meta)}, {i}, TRUE)"
            )
            w("ON CONFLICT (value_type, code, workspace_id) DO UPDATE SET")
            w("    label_en = EXCLUDED.label_en, label_fr = EXCLUDED.label_fr,")
            w("    note_en = EXCLUDED.note_en, note_fr = EXCLUDED.note_fr,")
            w("    metadata = EXCLUDED.metadata,")
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
                "art9_condition, retention_value, retention_unit, "
                "retention_is_statutory, system_role, sort_order"
            )
            avals = ", ".join(_q(x) for x in [
                a["name_en"], a.get("name_fr"), a.get("purpose_en"), a.get("purpose_fr"),
                a.get("legal_basis"), a.get("data_subject_categories", []),
                a.get("data_categories", []), a.get("special_categories", []),
                a.get("art9_condition"), a.get("retention_value"),
                a.get("retention_unit"), a.get("retention_is_statutory", False),
                a.get("system_role", "processor"), j,
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
            w("    retention_value = EXCLUDED.retention_value,")
            w("    retention_unit = EXCLUDED.retention_unit,")
            w("    retention_is_statutory = EXCLUDED.retention_is_statutory,")
            w("    system_role = EXCLUDED.system_role, sort_order = EXCLUDED.sort_order;")

        for pattern, match_type, confidence in v.get("domain_patterns", []):
            w("INSERT INTO vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)")
            w(f"SELECT id, {_q(pattern)}, {_q(match_type)}, {_q(confidence)} "
              f"FROM vendor_catalogue WHERE key = {_q(v['key'])}")
            w("ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET")
            w("    confidence = EXCLUDED.confidence;")

    w("")
    w("-- ── Catalogue principles ──────────────────────────────────────────────────")
    w("-- The reasoning behind the defaults, stored rather than left in comments.")
    for i, p in enumerate(CATALOGUE_PRINCIPLES):
        pcols = ("key, audience, title_en, title_fr, body_en, body_fr, "
                 "rationale_en, sort_order, active")
        pvals = ", ".join(_q(x) for x in [
            p["key"], p["audience"], p["title_en"], p.get("title_fr"),
            p["body_en"], p.get("body_fr"), p.get("rationale_en"), i, True,
        ])
        w(f"INSERT INTO catalogue_principles ({pcols})")
        w(f"VALUES ({pvals})")
        w("ON CONFLICT (key) DO UPDATE SET")
        w("    audience = EXCLUDED.audience, title_en = EXCLUDED.title_en,")
        w("    title_fr = EXCLUDED.title_fr, body_en = EXCLUDED.body_en,")
        w("    body_fr = EXCLUDED.body_fr, rationale_en = EXCLUDED.rationale_en,")
        w("    sort_order = EXCLUDED.sort_order, active = EXCLUDED.active;")

    w("")
    w("COMMIT;")
    w("")
    w("-- ── Verification ──────────────────────────────────────────────────────────")
    w("SELECT value_type, COUNT(*) FROM reference_values "
      "WHERE workspace_id IS NULL GROUP BY value_type ORDER BY value_type;")
    w("SELECT v.key, COUNT(a.id) AS activities FROM vendor_catalogue v")
    w("LEFT JOIN vendor_catalogue_activities a ON a.catalogue_id = v.id")
    w("GROUP BY v.key ORDER BY v.key;")
    w("SELECT audience, COUNT(*) FROM catalogue_principles GROUP BY audience;")
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
            # The retention principle, enforced rather than merely stated: an
            # activity cannot both declare its period statutory and carry a
            # hardcoded default, or the default silently wins for every client
            # regardless of country.
            if a.get("retention_is_statutory") and a.get("retention_unit"):
                errors.append(
                    f"{v['key']}/{a['name_en']}: retention marked statutory but "
                    f"a default period is set"
                )
            # S26C. Structured retention can be half-set in ways prose could
            # not, and a half-set period is worse than none: it renders as a
            # bare number or vanishes, and the register is where that shows up.
            if a.get("retention_value") is not None and not a.get("retention_unit"):
                errors.append(
                    f"{v['key']}/{a['name_en']}: retention_value without a unit"
                )
            if (a.get("retention_unit") not in (None, "indefinite")
                    and a.get("retention_value") is None):
                errors.append(
                    f"{v['key']}/{a['name_en']}: retention_unit without a value"
                )
            if a.get("retention_unit") and a["retention_unit"] not in codes["retention_unit"]:
                errors.append(
                    f"{v['key']}/{a['name_en']}: unknown retention_unit "
                    f"{a['retention_unit']!r}"
                )

    seen_keys = set()
    for p in CATALOGUE_PRINCIPLES:
        if p["key"] in seen_keys:
            errors.append(f"principle {p['key']}: duplicate key")
        seen_keys.add(p["key"])
        if p["audience"] not in ("client", "internal"):
            errors.append(f"principle {p['key']}: bad audience {p['audience']!r}")
        if p["audience"] == "client" and not p.get("body_fr"):
            errors.append(f"principle {p['key']}: client-facing but no French text")

    return errors


if __name__ == "__main__":
    import sys
    problems = self_check()
    if problems:
        for p in problems:
            print(f"SEED ERROR: {p}", file=sys.stderr)
        sys.exit(1)
    print(emit_sql())
