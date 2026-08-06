"""
RECOSA — Obligation registry (single source of truth).

Everything that maps a regulatory obligation to a document, a profile
question or an operational practice lives here. Before S23 this was spread
across three constants that disagreed with each other:

  * OBLIGATIONS[].doc_type      in gap_assessment.py
  * DOC_OBLIGATIONS             in gap_assessment.py  (single-document review)
  * OBLIGATION_TO_DOC           in pages/dashboard.py (checklist)

Only gdpr_01 and gdpr_07 appeared in all three, so the same privacy policy
was judged against a different obligation set depending on which screen you
were looking at. dashboard.py also keyed RoPA as "rop" while every other
module used "ropa", so a generated RoPA never matched its checklist row.

The two views are now DERIVED from this file rather than maintained by hand.

── kind ──────────────────────────────────────────────────────────────────
"document"     A document is the primary evidence. Counts toward that
               document's score.
"operational"  A process, practice or arrangement. No document proves it,
               so it must never drag a document's score down — it is
               surfaced in its own section instead. doc_type is always None.

── review_in ─────────────────────────────────────────────────────────────
Extra document types whose single-document review should also check this
obligation, even though no document *satisfies* it. A privacy policy review
can reasonably ask whether data minimisation is addressed (gdpr_14) without
gdpr_14 being satisfied by publishing a policy. Keeps the assessment rich
while keeping scoring honest.
"""

# ── Document types ────────────────────────────────────────────────────────
DOCUMENT_TYPES = {
    "privacy_policy":    "Privacy Policy",
    "cookie_policy":     "Cookie Policy",
    "dpa":               "Data Processing Agreement",
    "ropa":              "Record of Processing Activities",
    "incident_response": "Incident Response Plan",
    "ai_transparency":   "AI System Transparency Notice",
}

# EPRIVACY is not a regulation clients select in their profile; it rides
# along with GDPR. Without this, cookie obligations would vanish from the
# dashboard for every client.
REGULATION_PARENT = {"EPRIVACY": "GDPR"}

REGULATION_LABELS = {
    "GDPR":      "GDPR",
    "NIS2":      "NIS2",
    "EPRIVACY":  "ePrivacy",
    "EU_AI_ACT": "EU AI Act",
}

KIND_DOCUMENT    = "document"
KIND_OPERATIONAL = "operational"


OBLIGATIONS = [
    # ── GDPR ─────────────────────────────────────────────────────
    {"id": "gdpr_01", "regulation": "GDPR", "article": "Art. 13-14",
     "priority": "high", "kind": "document",
     "title": "Privacy policy published and up to date",
     "description": "A privacy policy must explain what data is collected, why, legal basis, retention, rights and contact details.",
     "doc_type": "privacy_policy", "profile_question": None, "review_in": []},

    {"id": "gdpr_02", "regulation": "GDPR", "article": "Art. 6",
     "priority": "high", "kind": "document",
     "title": "Legal basis identified for each processing activity",
     "description": "Every processing activity must have a documented legal basis under Article 6.",
     "doc_type": "ropa", "profile_question": None, "review_in": []},

    {"id": "gdpr_03", "regulation": "GDPR", "article": "Art. 30",
     "priority": "high", "kind": "document",
     "title": "Record of Processing Activities (RoPA) maintained",
     "description": "A written record of all processing activities including purposes, categories of data, recipients and retention periods.",
     "doc_type": "ropa", "profile_question": None, "review_in": []},

    {"id": "gdpr_04", "regulation": "GDPR", "article": "Art. 37",
     "priority": "high", "kind": "operational",
     "title": "DPO appointed if required",
     "description": "A Data Protection Officer must be appointed if required by GDPR Art. 37.",
     "doc_type": None, "profile_question": "dpo", "review_in": []},

    {"id": "gdpr_05", "regulation": "GDPR", "article": "Art. 28",
     "priority": "high", "kind": "document",
     "title": "Data Processing Agreements with all processors",
     "description": "A written DPA must be in place with every third-party processor handling personal data.",
     "doc_type": "dpa", "profile_question": None, "review_in": []},

    {"id": "gdpr_06", "regulation": "GDPR", "article": "Art. 33-34",
     "priority": "high", "kind": "document",
     "title": "Data breach notification procedure in place",
     "description": "A documented procedure for detecting, reporting and investigating breaches within 72 hours.",
     "doc_type": "incident_response", "profile_question": None, "review_in": []},

    {"id": "gdpr_07", "regulation": "GDPR", "article": "Art. 15-22",
     "priority": "high", "kind": "operational",
     "title": "Data subject rights procedure documented",
     "description": "Procedures to handle access, rectification, erasure, portability and objection requests.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy']},

    {"id": "gdpr_08", "regulation": "GDPR", "article": "Art. 7",
     "priority": "medium", "kind": "document",
     "title": "Consent mechanism for marketing communications",
     "description": "Valid consent mechanism for marketing where consent is the legal basis.",
     "doc_type": "privacy_policy", "profile_question": "marketing", "review_in": []},

    {"id": "gdpr_09", "regulation": "GDPR", "article": "Art. 5(1)(e)",
     "priority": "medium", "kind": "document",
     "title": "Retention periods defined and enforced",
     "description": "Retention periods must be defined for each data category.",
     "doc_type": "ropa", "profile_question": None, "review_in": []},

    {"id": "gdpr_10", "regulation": "GDPR", "article": "Art. 35",
     "priority": "medium", "kind": "operational",
     "title": "DPIA conducted for high-risk processing",
     "description": "Data Protection Impact Assessment for high-risk processing activities.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "gdpr_11", "regulation": "GDPR", "article": "Art. 44-49",
     "priority": "medium", "kind": "document",
     "title": "International transfer safeguards in place",
     "description": "Transfers outside the EU/EEA must rely on adequacy decision, SCCs or BCRs.",
     "doc_type": "dpa", "profile_question": None, "review_in": []},

    {"id": "gdpr_12", "regulation": "GDPR", "article": "Art. 25",
     "priority": "medium", "kind": "operational",
     "title": "Privacy by design and by default",
     "description": "Data protection must be considered from the outset of system or process design.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "gdpr_13", "regulation": "GDPR", "article": "Art. 5",
     "priority": "medium", "kind": "operational",
     "title": "Employee privacy and data protection training",
     "description": "Staff handling personal data must receive appropriate training.",
     "doc_type": None, "profile_question": "training", "review_in": []},

    {"id": "gdpr_14", "regulation": "GDPR", "article": "Art. 5(1)(c)",
     "priority": "medium", "kind": "operational",
     "title": "Data minimisation principles applied",
     "description": "Only necessary personal data should be collected and processed.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy']},

    {"id": "gdpr_15", "regulation": "GDPR", "article": "Art. 13",
     "priority": "high", "kind": "operational",
     "title": "Privacy notice provided at point of data collection",
     "description": "Privacy notice must be provided at the time of collection.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy']},

    {"id": "gdpr_16", "regulation": "GDPR", "article": "Art. 9",
     "priority": "high", "kind": "operational",
     "title": "Special category data safeguards",
     "description": "Additional legal grounds and safeguards for special category data.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy']},

    {"id": "gdpr_17", "regulation": "GDPR", "article": "Art. 26",
     "priority": "low", "kind": "operational",
     "title": "Joint controller arrangement documented",
     "description": "Joint controller arrangement setting out respective responsibilities.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "gdpr_18", "regulation": "GDPR", "article": "Art. 6(1)(f)",
     "priority": "low", "kind": "operational",
     "title": "Legitimate interest assessment documented",
     "description": "LIA balancing test conducted and documented where legitimate interests is used.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "gdpr_19", "regulation": "GDPR", "article": "Art. 8",
     "priority": "medium", "kind": "operational",
     "title": "Children's data safeguards implemented",
     "description": "Appropriate safeguards including age verification and parental consent.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "gdpr_20", "regulation": "GDPR", "article": "Art. 32",
     "priority": "medium", "kind": "operational",
     "title": "Technical and organisational security measures documented",
     "description": "Appropriate technical and organisational measures to ensure security of personal data.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy']},

    # ── NIS2 ─────────────────────────────────────────────────────
    {"id": "nis2_01", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "document",
     "title": "Cybersecurity risk assessment conducted",
     "description": "Formal risk assessment identifying threats, vulnerabilities and impact on systems.",
     "doc_type": "incident_response", "profile_question": None, "review_in": []},

    {"id": "nis2_02", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "document",
     "title": "Incident response plan documented",
     "description": "Documented incident response plan covering detection, containment, recovery and review.",
     "doc_type": "incident_response", "profile_question": None, "review_in": []},

    {"id": "nis2_03", "regulation": "NIS2", "article": "Art. 23",
     "priority": "high", "kind": "document",
     "title": "Incident reporting procedure (24h/72h)",
     "description": "Procedure for reporting significant incidents within 24h (early warning) and 72h (full notification).",
     "doc_type": "incident_response", "profile_question": None, "review_in": []},

    {"id": "nis2_04", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "document",
     "title": "Business continuity plan in place",
     "description": "Business continuity plan covering backup, disaster recovery and crisis management.",
     "doc_type": "incident_response", "profile_question": None, "review_in": []},

    {"id": "nis2_05", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "operational",
     "title": "Supply chain security policy",
     "description": "Security policies addressing risks from suppliers and third-party service providers.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "nis2_06", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "operational",
     "title": "Access control and authentication policy",
     "description": "Policies governing access control, MFA and privileged access management.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "nis2_07", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Encryption policy for data in transit and at rest",
     "description": "Policy requiring encryption of sensitive data both in transit and at rest.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "nis2_08", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Vulnerability management process",
     "description": "Process for identifying, assessing and remediating security vulnerabilities.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "nis2_09", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Security awareness training for all staff",
     "description": "Regular cybersecurity awareness training for all employees.",
     "doc_type": None, "profile_question": "training", "review_in": []},

    {"id": "nis2_10", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Backup and recovery procedures documented",
     "description": "Documented backup procedures including frequency, storage and tested recovery.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "nis2_11", "regulation": "NIS2", "article": "Art. 3",
     "priority": "high", "kind": "operational",
     "title": "Registered with national NIS2 authority",
     "description": "Essential and important entities must register with national authority (CCB/ANSSI).",
     "doc_type": None, "profile_question": "nis2_registered", "review_in": []},

    {"id": "nis2_12", "regulation": "NIS2", "article": "Art. 20",
     "priority": "high", "kind": "operational",
     "title": "Management body approved cybersecurity policy",
     "description": "Management body must approve and oversee cybersecurity risk management measures.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "nis2_13", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Network security monitoring in place",
     "description": "Monitoring of network and information systems for cybersecurity events.",
     "doc_type": None, "profile_question": None, "review_in": []},

    {"id": "nis2_14", "regulation": "NIS2", "article": "Art. 21",
     "priority": "low", "kind": "operational",
     "title": "Penetration testing conducted",
     "description": "Regular penetration testing to identify and address vulnerabilities.",
     "doc_type": None, "profile_question": "pentest", "review_in": []},

    {"id": "nis2_15", "regulation": "NIS2", "article": "Art. 21",
     "priority": "low", "kind": "operational",
     "title": "Security audit trail maintained",
     "description": "Logs of security-relevant events maintained and protected from tampering.",
     "doc_type": None, "profile_question": None, "review_in": []},

    # ── ePrivacy ─────────────────────────────────────────────────
    {"id": "eprivacy_01", "regulation": "EPRIVACY", "article": "Art. 5(3)",
     "priority": "high", "kind": "document",
     "title": "Cookie consent banner implemented",
     "description": "Valid consent must be obtained before placing non-essential cookies.",
     "doc_type": "cookie_policy", "profile_question": "cookies", "review_in": []},

    {"id": "eprivacy_02", "regulation": "EPRIVACY", "article": "Art. 5(3)",
     "priority": "high", "kind": "document",
     "title": "Cookie policy published",
     "description": "Cookie policy explaining cookies used, their purpose, duration and how to manage preferences.",
     "doc_type": "cookie_policy", "profile_question": "cookies", "review_in": []},

    {"id": "eprivacy_03", "regulation": "EPRIVACY", "article": "Art. 13",
     "priority": "high", "kind": "document",
     "title": "Marketing email opt-in mechanism",
     "description": "Prior consent must be obtained before sending marketing emails.",
     "doc_type": "privacy_policy", "profile_question": "marketing", "review_in": []},

    {"id": "eprivacy_04", "regulation": "EPRIVACY", "article": "Art. 13",
     "priority": "medium", "kind": "operational",
     "title": "Opt-out mechanism for marketing communications",
     "description": "Every marketing communication must include a clear unsubscribe mechanism.",
     "doc_type": None, "profile_question": "marketing", "review_in": []},

    {"id": "eprivacy_05", "regulation": "EPRIVACY", "article": "Art. 5(3)",
     "priority": "medium", "kind": "operational",
     "title": "Cookie consent records maintained",
     "description": "Records of cookie consents must be maintained to demonstrate valid consent.",
     "doc_type": None, "profile_question": "cookies", "review_in": ['cookie_policy']},
]

# ── Profile questions ─────────────────────────────────────────────────────
PROFILE_QUESTIONS = {
    "dpo": {
        "question": "Have you appointed a Data Protection Officer (DPO)?",
        "options": ["Yes", "No", "Not required for our organisation"],
        "compliant_answers": ["Yes", "Not required for our organisation"],
    },
    "nis2_registered": {
        "question": "Have you registered with your national NIS2 authority (CCB for Belgium, ANSSI for France)?",
        "options": ["Yes", "No", "Not applicable — we are not in scope for NIS2"],
        "compliant_answers": ["Yes", "Not applicable — we are not in scope for NIS2"],
    },
    "training": {
        "question": "Do you conduct regular security and privacy training for all staff?",
        "options": ["Yes — formal training programme", "Partially — some staff or informal", "No"],
        "compliant_answers": ["Yes — formal training programme"],
        "partial_answers": ["Partially — some staff or informal"],
    },
    "pentest": {
        "question": "Have you conducted a penetration test in the last 12 months?",
        "options": ["Yes", "No", "Not applicable"],
        "compliant_answers": ["Yes", "Not applicable"],
    },
    "cookies": {
        "question": "Do you use cookies or tracking technologies on your website?",
        "options": ["Yes — including non-essential cookies", "No — essential cookies only", "We have no website"],
        "compliant_answers": ["No — essential cookies only", "We have no website"],
        "na_answers": ["No — essential cookies only", "We have no website"],
    },
    "marketing": {
        "question": "Do you send marketing emails to prospects or customers?",
        "options": ["Yes", "No"],
        "compliant_answers": ["No"],
        "na_answers": ["No"],
    },
}


# ── Derived views ─────────────────────────────────────────────────────────
# Nothing below is maintained by hand. Edit OBLIGATIONS above instead.

OBLIGATION_BY_ID = {o["id"]: o for o in OBLIGATIONS}

DOCUMENT_OBLIGATIONS = [o for o in OBLIGATIONS if o["kind"] == KIND_DOCUMENT]
OPERATIONAL_OBLIGATIONS = [o for o in OBLIGATIONS if o["kind"] == KIND_OPERATIONAL]

# obligation id -> doc_type, for the document that satisfies it.
OBLIGATION_TO_DOC = {
    o["id"]: o["doc_type"] for o in OBLIGATIONS if o["doc_type"]
}

# doc_type -> obligation ids checked when REVIEWING that document.
# Primary obligations plus anything flagged review_in. Superset of
# OBLIGATION_TO_DOC by design: reviewing a document can legitimately ask
# about more than the document alone can satisfy.
DOC_OBLIGATIONS = {
    dt: [o["id"] for o in OBLIGATIONS
         if o["doc_type"] == dt or dt in o["review_in"]]
    for dt in DOCUMENT_TYPES
}

# doc_type -> obligation ids that document actually SATISFIES. This is what
# scoring must use; DOC_OBLIGATIONS would penalise a document for
# operational gaps it cannot fix.
DOC_SCORING_OBLIGATIONS = {
    dt: [o["id"] for o in OBLIGATIONS if o["doc_type"] == dt]
    for dt in DOCUMENT_TYPES
}


def _client_regulation(reg: str) -> str:
    """Map an obligation's regulation onto the ones clients select."""
    return REGULATION_PARENT.get(reg, reg)


# doc_type -> {"label", "regulations"}, for the dashboard checklist.
DOC_CATALOG = {
    dt: {
        "label": label,
        "regulations": sorted({
            _client_regulation(o["regulation"])
            for o in OBLIGATIONS if o["doc_type"] == dt
        }),
    }
    for dt, label in DOCUMENT_TYPES.items()
}

# client-selectable regulation -> document types relevant to it.
REG_DOCS = {}
for _dt, _meta in DOC_CATALOG.items():
    for _reg in _meta["regulations"]:
        REG_DOCS.setdefault(_reg, []).append(_dt)


def obligations_for_regulations(regulations: list) -> list:
    """Obligations in scope for a client's selected regulations."""
    wanted = set(regulations)
    return [o for o in OBLIGATIONS
            if _client_regulation(o["regulation"]) in wanted
            or o["regulation"] in wanted]


def operational_for_regulations(regulations: list) -> list:
    return [o for o in obligations_for_regulations(regulations)
            if o["kind"] == KIND_OPERATIONAL]


def documents_for_regulations(regulations: list) -> dict:
    """{doc_type: catalog_meta} for the client's selected regulations."""
    wanted = set(regulations)
    return {
        dt: meta for dt, meta in DOC_CATALOG.items()
        if meta["regulations"] and any(r in wanted for r in meta["regulations"])
    }
