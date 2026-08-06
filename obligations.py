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

── applies_from ──────────────────────────────────────────────────────────
ISO date, or None for "in force, no staged date". Without this, staged
obligations mark every client red today for duties that do not bind for
months or years — the EU AI Act alone has five. A false alarm is the
fastest way to lose a client's trust in a compliance tool, so obligations
that have not yet bitten are shown as forthcoming, not as failures.

── statutory ─────────────────────────────────────────────────────────────
False marks work RECOSA recommends that no article actually requires.
Currently only ai_09, the AI system inventory: the AI Act prescribes no
inventory and no format, but Articles 4, 5, 26 and 50 all presuppose one
and none can be evidenced without it. Displayed distinctly so a client can
tell what the law demands from what we advise.

── review_in ─────────────────────────────────────────────────────────────
Extra document types whose single-document review should also check this
obligation, even though no document *satisfies* it. A privacy policy review
can reasonably ask whether data minimisation is addressed (gdpr_14) without
gdpr_14 being satisfied by publishing a policy. Keeps the assessment rich
while keeping scoring honest.
"""

import datetime as _dt

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
     "doc_type": "privacy_policy", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_02", "regulation": "GDPR", "article": "Art. 6",
     "priority": "high", "kind": "document",
     "title": "Legal basis identified for each processing activity",
     "description": "Every processing activity must have a documented legal basis under Article 6.",
     "doc_type": "ropa", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_03", "regulation": "GDPR", "article": "Art. 30",
     "priority": "high", "kind": "document",
     "title": "Record of Processing Activities (RoPA) maintained",
     "description": "A written record of all processing activities including purposes, categories of data, recipients and retention periods.",
     "doc_type": "ropa", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_04", "regulation": "GDPR", "article": "Art. 37",
     "priority": "high", "kind": "operational",
     "title": "DPO appointed if required",
     "description": "A Data Protection Officer must be appointed if required by GDPR Art. 37.",
     "doc_type": None, "profile_question": "dpo", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_05", "regulation": "GDPR", "article": "Art. 28",
     "priority": "high", "kind": "document",
     "title": "Data Processing Agreements with all processors",
     "description": "A written DPA must be in place with every third-party processor handling personal data.",
     "doc_type": "dpa", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_06", "regulation": "GDPR", "article": "Art. 33-34",
     "priority": "high", "kind": "document",
     "title": "Data breach notification procedure in place",
     "description": "A documented procedure for detecting, reporting and investigating breaches within 72 hours.",
     "doc_type": "incident_response", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_07", "regulation": "GDPR", "article": "Art. 15-22",
     "priority": "high", "kind": "operational",
     "title": "Data subject rights procedure documented",
     "description": "Procedures to handle access, rectification, erasure, portability and objection requests.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy'],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_08", "regulation": "GDPR", "article": "Art. 7",
     "priority": "medium", "kind": "document",
     "title": "Consent mechanism for marketing communications",
     "description": "Valid consent mechanism for marketing where consent is the legal basis.",
     "doc_type": "privacy_policy", "profile_question": "marketing", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_09", "regulation": "GDPR", "article": "Art. 5(1)(e)",
     "priority": "medium", "kind": "document",
     "title": "Retention periods defined and enforced",
     "description": "Retention periods must be defined for each data category.",
     "doc_type": "ropa", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_10", "regulation": "GDPR", "article": "Art. 35",
     "priority": "medium", "kind": "operational",
     "title": "DPIA conducted for high-risk processing",
     "description": "Data Protection Impact Assessment for high-risk processing activities.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_11", "regulation": "GDPR", "article": "Art. 44-49",
     "priority": "medium", "kind": "document",
     "title": "International transfer safeguards in place",
     "description": "Transfers outside the EU/EEA must rely on adequacy decision, SCCs or BCRs.",
     "doc_type": "dpa", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_12", "regulation": "GDPR", "article": "Art. 25",
     "priority": "medium", "kind": "operational",
     "title": "Privacy by design and by default",
     "description": "Data protection must be considered from the outset of system or process design.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_13", "regulation": "GDPR", "article": "Art. 5",
     "priority": "medium", "kind": "operational",
     "title": "Employee privacy and data protection training",
     "description": "Staff handling personal data must receive appropriate training.",
     "doc_type": None, "profile_question": "training", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_14", "regulation": "GDPR", "article": "Art. 5(1)(c)",
     "priority": "medium", "kind": "operational",
     "title": "Data minimisation principles applied",
     "description": "Only necessary personal data should be collected and processed.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy'],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_15", "regulation": "GDPR", "article": "Art. 13",
     "priority": "high", "kind": "operational",
     "title": "Privacy notice provided at point of data collection",
     "description": "Privacy notice must be provided at the time of collection.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy'],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_16", "regulation": "GDPR", "article": "Art. 9",
     "priority": "high", "kind": "operational",
     "title": "Special category data safeguards",
     "description": "Additional legal grounds and safeguards for special category data.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy'],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_17", "regulation": "GDPR", "article": "Art. 26",
     "priority": "low", "kind": "operational",
     "title": "Joint controller arrangement documented",
     "description": "Joint controller arrangement setting out respective responsibilities.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_18", "regulation": "GDPR", "article": "Art. 6(1)(f)",
     "priority": "low", "kind": "operational",
     "title": "Legitimate interest assessment documented",
     "description": "LIA balancing test conducted and documented where legitimate interests is used.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_19", "regulation": "GDPR", "article": "Art. 8",
     "priority": "medium", "kind": "operational",
     "title": "Children's data safeguards implemented",
     "description": "Appropriate safeguards including age verification and parental consent.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "gdpr_20", "regulation": "GDPR", "article": "Art. 32",
     "priority": "medium", "kind": "operational",
     "title": "Technical and organisational security measures documented",
     "description": "Appropriate technical and organisational measures to ensure security of personal data.",
     "doc_type": None, "profile_question": None, "review_in": ['privacy_policy'],
     "applies_from": None, "statutory": True},

    # ── NIS2 ─────────────────────────────────────────────────────
    {"id": "nis2_01", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "document",
     "title": "Cybersecurity risk assessment conducted",
     "description": "Formal risk assessment identifying threats, vulnerabilities and impact on systems.",
     "doc_type": "incident_response", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_02", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "document",
     "title": "Incident response plan documented",
     "description": "Documented incident response plan covering detection, containment, recovery and review.",
     "doc_type": "incident_response", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_03", "regulation": "NIS2", "article": "Art. 23",
     "priority": "high", "kind": "document",
     "title": "Incident reporting procedure (24h/72h)",
     "description": "Procedure for reporting significant incidents within 24h (early warning) and 72h (full notification).",
     "doc_type": "incident_response", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_04", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "document",
     "title": "Business continuity plan in place",
     "description": "Business continuity plan covering backup, disaster recovery and crisis management.",
     "doc_type": "incident_response", "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_05", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "operational",
     "title": "Supply chain security policy",
     "description": "Security policies addressing risks from suppliers and third-party service providers.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_06", "regulation": "NIS2", "article": "Art. 21",
     "priority": "high", "kind": "operational",
     "title": "Access control and authentication policy",
     "description": "Policies governing access control, MFA and privileged access management.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_07", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Encryption policy for data in transit and at rest",
     "description": "Policy requiring encryption of sensitive data both in transit and at rest.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_08", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Vulnerability management process",
     "description": "Process for identifying, assessing and remediating security vulnerabilities.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_09", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Security awareness training for all staff",
     "description": "Regular cybersecurity awareness training for all employees.",
     "doc_type": None, "profile_question": "training", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_10", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Backup and recovery procedures documented",
     "description": "Documented backup procedures including frequency, storage and tested recovery.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_11", "regulation": "NIS2", "article": "Art. 3",
     "priority": "high", "kind": "operational",
     "title": "Registered with national NIS2 authority",
     "description": "Essential and important entities must register with national authority (CCB/ANSSI).",
     "doc_type": None, "profile_question": "nis2_registered", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_12", "regulation": "NIS2", "article": "Art. 20",
     "priority": "high", "kind": "operational",
     "title": "Management body approved cybersecurity policy",
     "description": "Management body must approve and oversee cybersecurity risk management measures.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_13", "regulation": "NIS2", "article": "Art. 21",
     "priority": "medium", "kind": "operational",
     "title": "Network security monitoring in place",
     "description": "Monitoring of network and information systems for cybersecurity events.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_14", "regulation": "NIS2", "article": "Art. 21",
     "priority": "low", "kind": "operational",
     "title": "Penetration testing conducted",
     "description": "Regular penetration testing to identify and address vulnerabilities.",
     "doc_type": None, "profile_question": "pentest", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "nis2_15", "regulation": "NIS2", "article": "Art. 21",
     "priority": "low", "kind": "operational",
     "title": "Security audit trail maintained",
     "description": "Logs of security-relevant events maintained and protected from tampering.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": None, "statutory": True},

    # ── ePrivacy ─────────────────────────────────────────────────
    {"id": "eprivacy_01", "regulation": "EPRIVACY", "article": "Art. 5(3)",
     "priority": "high", "kind": "document",
     "title": "Cookie consent banner implemented",
     "description": "Valid consent must be obtained before placing non-essential cookies.",
     "doc_type": "cookie_policy", "profile_question": "cookies", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "eprivacy_02", "regulation": "EPRIVACY", "article": "Art. 5(3)",
     "priority": "high", "kind": "document",
     "title": "Cookie policy published",
     "description": "Cookie policy explaining cookies used, their purpose, duration and how to manage preferences.",
     "doc_type": "cookie_policy", "profile_question": "cookies", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "eprivacy_03", "regulation": "EPRIVACY", "article": "Art. 13",
     "priority": "high", "kind": "document",
     "title": "Marketing email opt-in mechanism",
     "description": "Prior consent must be obtained before sending marketing emails.",
     "doc_type": "privacy_policy", "profile_question": "marketing", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "eprivacy_04", "regulation": "EPRIVACY", "article": "Art. 13",
     "priority": "medium", "kind": "operational",
     "title": "Opt-out mechanism for marketing communications",
     "description": "Every marketing communication must include a clear unsubscribe mechanism.",
     "doc_type": None, "profile_question": "marketing", "review_in": [],
     "applies_from": None, "statutory": True},

    {"id": "eprivacy_05", "regulation": "EPRIVACY", "article": "Art. 5(3)",
     "priority": "medium", "kind": "operational",
     "title": "Cookie consent records maintained",
     "description": "Records of cookie consents must be maintained to demonstrate valid consent.",
     "doc_type": None, "profile_question": "cookies", "review_in": ['cookie_policy'],
     "applies_from": None, "statutory": True},

    # ── EU AI Act ─────────────────────────────────────────────
    # Deployer-scoped. Full Annex III provider/conformity-assessment duties
    # are deliberately excluded: RECOSA's SME cohort deploys AI, it does not
    # place high-risk systems on the market. Revisit if demand appears.
    #
    # Legal state as at 6 Aug 2026: Regulation (EU) 2024/1689 as amended by
    # Regulation (EU) 2026/1744 (Digital Omnibus on AI, in force 27 Jul 2026).
    {"id": "ai_01", "regulation": "EU_AI_ACT", "article": "Art. 4",
     "priority": "high", "kind": "operational",
     "title": "AI literacy measures in place for staff using AI",
     "description": "Providers and deployers must take measures to support the development of AI literacy among staff and others operating AI systems on their behalf. Since the Digital Omnibus this is an obligation of effort rather than result: no specific level of literacy must be guaranteed for any individual. National supervision of this duty began on 3 August 2026.",
     "doc_type": None, "profile_question": "ai_usage", "review_in": [],
     "applies_from": "2025-02-02", "statutory": True},

    {"id": "ai_02", "regulation": "EU_AI_ACT", "article": "Art. 5",
     "priority": "high", "kind": "operational",
     "title": "No prohibited AI practices in use",
     "description": "Article 5 bans a defined set of practices outright, including emotion recognition in the workplace and in education, social scoring, untargeted scraping of facial images, and exploitation of vulnerabilities. Screening is required before any AI system is put into use. Breach carries the highest penalty tier, up to EUR 35 million or 7% of worldwide annual turnover.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": "2025-02-02", "statutory": True},

    {"id": "ai_03", "regulation": "EU_AI_ACT", "article": "Art. 3(3), 3(4), 25",
     "priority": "high", "kind": "operational",
     "title": "Provider or deployer role determined for each AI system",
     "description": "Obligations differ sharply by role and the distinction is not intuitive. An organisation that puts an AI system into service under its own name, including one built in-house or a third-party system rebranded as its own, becomes a provider and takes on design duties rather than only the deployer's disclosure duties. The role must be established per system and recorded.",
     "doc_type": None, "profile_question": None, "review_in": ["ai_transparency"],
     "applies_from": "2026-08-02", "statutory": True},

    {"id": "ai_04", "regulation": "EU_AI_ACT", "article": "Art. 50(1)",
     "priority": "high", "kind": "document",
     "title": "Users informed they are interacting with an AI system",
     "description": "AI systems interacting directly with people must be designed so those people are informed they are dealing with AI, unless it is obvious to a reasonably well-informed and observant person. Covers chatbots, voice assistants, conversational agents and AI agents acting on someone's behalf. Commission guidance is explicit that placing the disclosure in terms and conditions does not satisfy the duty, and that notice must account for children and people with disabilities.",
     "doc_type": "ai_transparency", "profile_question": "ai_usage", "review_in": [],
     "applies_from": "2026-08-02", "statutory": True},

    {"id": "ai_05", "regulation": "EU_AI_ACT", "article": "Art. 50(3)",
     "priority": "high", "kind": "document",
     "title": "Notice given to people exposed to emotion recognition or biometric categorisation",
     "description": "Deployers must inform individuals exposed to emotion recognition or biometric categorisation systems that the system is operating, whether processing is real-time or after the fact. Note the interaction with ai_02: emotion recognition in the workplace and in education is prohibited outright, so this obligation applies only outside those settings. Personal data collected through such systems remains fully subject to the GDPR.",
     "doc_type": "ai_transparency", "profile_question": None, "review_in": [],
     "applies_from": "2026-08-02", "statutory": True},

    {"id": "ai_06", "regulation": "EU_AI_ACT", "article": "Art. 50(4)",
     "priority": "high", "kind": "operational",
     "title": "AI-generated or manipulated image, audio and video disclosed",
     "description": "Deployers publishing deepfake content, meaning artificially generated or manipulated material resembling real persons, objects, places or events that would falsely appear authentic, must disclose that it is artificially generated. Where the content forms part of an evidently artistic, satirical or fictional work, disclosure is limited to a form that does not hamper enjoyment of the work. Responsibility sits with the deployer publishing the content, not the vendor of the generation tool.",
     "doc_type": None, "profile_question": "ai_generative", "review_in": ["ai_transparency"],
     "applies_from": "2026-08-02", "statutory": True},

    {"id": "ai_07", "regulation": "EU_AI_ACT", "article": "Art. 50(4)",
     "priority": "medium", "kind": "operational",
     "title": "AI-generated text on matters of public interest labelled",
     "description": "Text generated or manipulated by AI and published to inform the public on matters of public interest must be labelled as artificially generated, unless it has undergone human review and a natural or legal person holds editorial responsibility for it.",
     "doc_type": None, "profile_question": "ai_generative", "review_in": [],
     "applies_from": "2026-08-02", "statutory": True},

    {"id": "ai_08", "regulation": "EU_AI_ACT", "article": "Art. 50(2)",
     "priority": "medium", "kind": "operational",
     "title": "Generative AI output marked in machine-readable form",
     "description": "Providers of AI systems generating synthetic image, audio, video or text must mark outputs as artificially generated in a machine-readable, interoperable and robust format, so far as technically feasible. This is a provider duty, so it binds only where the organisation supplies a generative system rather than merely using one. Systems already on the EU market on 2 August 2026 have until 2 December 2026; systems placed on the market after that date must comply on placement.",
     "doc_type": None, "profile_question": "ai_usage", "review_in": [],
     "applies_from": "2026-12-02", "statutory": True},

    {"id": "ai_09", "regulation": "EU_AI_ACT", "article": "RECOSA recommended",
     "priority": "high", "kind": "document",
     "title": "Inventory of AI systems in use maintained",
     "description": "RECOSA-recommended preliminary work rather than a standalone statutory duty: the AI Act prescribes no inventory and no format for one. It is included because Articles 4, 5, 26 and 50 all presuppose that the organisation knows which AI systems it operates, in what role and for what purpose, and because none of those obligations can be evidenced without it. The AI Act analogue of the Article 30 GDPR record.",
     "doc_type": "ai_transparency", "profile_question": "ai_usage", "review_in": [],
     "applies_from": "2026-08-02", "statutory": False},

    {"id": "ai_10", "regulation": "EU_AI_ACT", "article": "Art. 5 (as amended)",
     "priority": "high", "kind": "operational",
     "title": "No AI capability for non-consensual intimate imagery or CSAM",
     "description": "The Digital Omnibus added two prohibitions to Article 5: AI systems used to generate non-consensual intimate imagery, so-called nudification applications, and child sexual abuse material. These apply from 2 December 2026 and carry the highest penalty tier.",
     "doc_type": None, "profile_question": None, "review_in": [],
     "applies_from": "2026-12-02", "statutory": True},

    {"id": "ai_11", "regulation": "EU_AI_ACT", "article": "Annex III",
     "priority": "high", "kind": "operational",
     "title": "Annex III high-risk classification assessed and documented",
     "description": "Annex III lists standalone high-risk uses including recruitment and candidate screening, credit scoring, access to essential public and private services, and worker management and evaluation. Organisations must establish whether any system they operate falls in scope. The obligations themselves bind from 2 December 2027, but the preparation lead time is substantial, so the assessment belongs now. The Digital Omnibus narrowed the safety component definition so that AI merely assisting users or optimising performance is not automatically high-risk.",
     "doc_type": None, "profile_question": "ai_annexiii", "review_in": [],
     "applies_from": "2026-08-02", "statutory": True},

    {"id": "ai_12", "regulation": "EU_AI_ACT", "article": "Art. 26(2)",
     "priority": "high", "kind": "operational",
     "title": "Human oversight assigned for high-risk AI systems",
     "description": "Deployers of high-risk systems must assign human oversight to persons with the necessary competence, training and authority, and must use the system in accordance with the provider's instructions for use.",
     "doc_type": None, "profile_question": "ai_annexiii", "review_in": [],
     "applies_from": "2027-12-02", "statutory": True},

    {"id": "ai_13", "regulation": "EU_AI_ACT", "article": "Art. 26(6)",
     "priority": "medium", "kind": "operational",
     "title": "Logs from high-risk AI systems retained",
     "description": "Deployers must keep logs automatically generated by high-risk AI systems under their control for at least six months, unless a longer retention period is required by other Union or national law.",
     "doc_type": None, "profile_question": "ai_annexiii", "review_in": [],
     "applies_from": "2027-12-02", "statutory": True},

    {"id": "ai_14", "regulation": "EU_AI_ACT", "article": "Art. 26(7)",
     "priority": "high", "kind": "operational",
     "title": "Workers informed before a high-risk AI system is used on them",
     "description": "Before putting a high-risk AI system into service in the workplace, deployers who are employers must inform worker representatives and the affected workers that they will be subject to it. This sits alongside, not instead of, national labour law consultation duties, which in Belgium and France are materially more demanding than the AI Act baseline.",
     "doc_type": None, "profile_question": "ai_annexiii", "review_in": [],
     "applies_from": "2027-12-02", "statutory": True},
]

# ── Profile questions ─────────────────────────────────────────────────────
PROFILE_QUESTIONS = {
    "ai_usage": {
        "question": "How does your organisation use AI systems?",
        "options": [
            "We do not use AI systems",
            "Internal use only — no customer or public interaction",
            "Customer-facing AI (chatbots, assistants, automated responses)",
            "We build or supply AI systems to others",
        ],
        "compliant_answers": ["We do not use AI systems"],
        "na_answers": ["We do not use AI systems"],
    },
    "ai_generative": {
        "question": "Do you publish content generated or edited by AI (images, video, audio or text)?",
        "options": [
            "No",
            "Yes — internally only",
            "Yes — published publicly",
        ],
        "compliant_answers": ["No"],
        "na_answers": ["No"],
    },
    "ai_annexiii": {
        "question": "Do you use AI for recruitment or candidate screening, credit or insurance decisions, worker evaluation, or access to essential services?",
        "options": ["No", "Yes", "Not sure"],
        "compliant_answers": ["No"],
        "na_answers": ["No"],
        # "Not sure" scores partial for now. A guided scoping conversation is
        # queued for a later sprint — until then, partial is the honest answer.
        "partial_answers": ["Not sure"],
    },
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
for _doc_type, _meta in DOC_CATALOG.items():
    for _reg in _meta["regulations"]:
        REG_DOCS.setdefault(_reg, []).append(_doc_type)
del _doc_type, _meta, _reg   # module-level loop vars would otherwise leak


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


# ── Staged obligations ────────────────────────────────────────────────────

def is_in_force(obligation: dict, on: "date | None" = None) -> bool:
    """True if the obligation binds on the given date (default: today)."""
    applies = obligation.get("applies_from")
    if not applies:
        return True
    ref = on or _dt.date.today()
    try:
        return _dt.date.fromisoformat(applies) <= ref
    except ValueError:
        # A malformed date must not silently suppress an obligation.
        return True


def split_by_force(obligations: list, on: "date | None" = None) -> tuple:
    """(in_force, forthcoming). Forthcoming are reported, never scored."""
    live, later = [], []
    for o in obligations:
        (live if is_in_force(o, on) else later).append(o)
    return live, later


def applies_from_label(obligation: dict) -> str:
    """Human-readable date for a forthcoming obligation, '' if in force."""
    applies = obligation.get("applies_from")
    if not applies or is_in_force(obligation):
        return ""
    try:
        d = _dt.date.fromisoformat(applies)
    except ValueError:
        return ""
    return d.strftime("%-d %B %Y")
