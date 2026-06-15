import os
import io
import json
import time
import uuid
import re
import tempfile
import requests
import streamlit as st
from datetime import date, datetime
from pypdf import PdfReader
from docx import Document as DocxDocument

# ── Obligations registry ──────────────────────────────────────

OBLIGATIONS = [
    # ── GDPR ─────────────────────────────────────────────────
    {"id": "gdpr_01", "regulation": "GDPR", "article": "Art. 13-14", "priority": "high",
     "title": "Privacy policy published and up to date",
     "description": "A privacy policy must be made available to data subjects explaining what data is collected, why, legal basis, retention, rights and contact details.",
     "doc_type": "privacy_policy", "profile_question": None},

    {"id": "gdpr_02", "regulation": "GDPR", "article": "Art. 6", "priority": "high",
     "title": "Legal basis identified for each processing activity",
     "description": "Every processing activity must have a documented legal basis under Article 6 (consent, contract, legal obligation, vital interests, public task, or legitimate interests).",
     "doc_type": "ropa", "profile_question": None},

    {"id": "gdpr_03", "regulation": "GDPR", "article": "Art. 30", "priority": "high",
     "title": "Record of Processing Activities (RoPA) maintained",
     "description": "Organisations with 250+ employees or processing sensitive data must maintain a written record of all processing activities including purposes, categories of data, recipients and retention periods.",
     "doc_type": "ropa", "profile_question": None},

    {"id": "gdpr_04", "regulation": "GDPR", "article": "Art. 37", "priority": "high",
     "title": "DPO appointed if required",
     "description": "A Data Protection Officer must be appointed if the organisation is a public body, carries out large-scale systematic monitoring, or processes special category data at scale.",
     "doc_type": None, "profile_question": "dpo"},

    {"id": "gdpr_05", "regulation": "GDPR", "article": "Art. 28", "priority": "high",
     "title": "Data Processing Agreements with all processors",
     "description": "A written Data Processing Agreement must be in place with every third-party processor handling personal data on behalf of the organisation.",
     "doc_type": "dpa", "profile_question": None},

    {"id": "gdpr_06", "regulation": "GDPR", "article": "Art. 33-34", "priority": "high",
     "title": "Data breach notification procedure in place",
     "description": "A documented procedure must exist for detecting, reporting and investigating data breaches, including notifying the supervisory authority within 72 hours.",
     "doc_type": "incident_response", "profile_question": None},

    {"id": "gdpr_07", "regulation": "GDPR", "article": "Art. 15-22", "priority": "high",
     "title": "Data subject rights procedure documented",
     "description": "Procedures must be in place to handle requests from data subjects to access, rectify, erase, port, or object to processing of their personal data within the required timeframes.",
     "doc_type": "privacy_policy", "profile_question": None},

    {"id": "gdpr_08", "regulation": "GDPR", "article": "Art. 7", "priority": "medium",
     "title": "Consent mechanism for marketing communications",
     "description": "Where consent is the legal basis for marketing, a valid, freely given, specific, informed and unambiguous consent mechanism must be implemented.",
     "doc_type": "privacy_policy", "profile_question": "marketing"},

    {"id": "gdpr_09", "regulation": "GDPR", "article": "Art. 5(1)(e)", "priority": "medium",
     "title": "Retention periods defined and enforced",
     "description": "Personal data must not be kept longer than necessary. Retention periods must be defined for each data category and enforced through deletion or anonymisation procedures.",
     "doc_type": "ropa", "profile_question": None},

    {"id": "gdpr_10", "regulation": "GDPR", "article": "Art. 35", "priority": "medium",
     "title": "DPIA conducted for high-risk processing",
     "description": "A Data Protection Impact Assessment must be conducted before processing that is likely to result in high risk to individuals, such as large-scale profiling or systematic monitoring.",
     "doc_type": None, "profile_question": None},

    {"id": "gdpr_11", "regulation": "GDPR", "article": "Art. 44-49", "priority": "medium",
     "title": "International transfer safeguards in place",
     "description": "Transfers of personal data outside the EU/EEA must rely on an adequacy decision, Standard Contractual Clauses, Binding Corporate Rules, or another approved transfer mechanism.",
     "doc_type": "dpa", "profile_question": None},

    {"id": "gdpr_12", "regulation": "GDPR", "article": "Art. 25", "priority": "medium",
     "title": "Privacy by design and by default",
     "description": "Data protection must be considered from the outset of system or process design. Only necessary data should be collected and processed by default.",
     "doc_type": None, "profile_question": None},

    {"id": "gdpr_13", "regulation": "GDPR", "article": "Art. 5", "priority": "medium",
     "title": "Employee privacy and data protection training",
     "description": "Staff who handle personal data must receive appropriate training on data protection obligations and internal policies.",
     "doc_type": None, "profile_question": "training"},

    {"id": "gdpr_14", "regulation": "GDPR", "article": "Art. 5(1)(c)", "priority": "medium",
     "title": "Data minimisation principles applied",
     "description": "Only personal data that is adequate, relevant and limited to what is necessary for the specified purpose should be collected and processed.",
     "doc_type": None, "profile_question": None},

    {"id": "gdpr_15", "regulation": "GDPR", "article": "Art. 13", "priority": "high",
     "title": "Privacy notice provided at point of data collection",
     "description": "When collecting personal data directly from individuals, a privacy notice must be provided at the time of collection covering all required information elements.",
     "doc_type": "privacy_policy", "profile_question": None},

    {"id": "gdpr_16", "regulation": "GDPR", "article": "Art. 9", "priority": "high",
     "title": "Special category data safeguards",
     "description": "If processing health, biometric, racial, political, religious or other special category data, additional legal grounds and safeguards must be documented and implemented.",
     "doc_type": None, "profile_question": None},

    {"id": "gdpr_17", "regulation": "GDPR", "article": "Art. 26", "priority": "low",
     "title": "Joint controller arrangement documented",
     "description": "Where two or more organisations jointly determine the purposes and means of processing, a joint controller arrangement must be documented setting out respective responsibilities.",
     "doc_type": None, "profile_question": None},

    {"id": "gdpr_18", "regulation": "GDPR", "article": "Art. 6(1)(f)", "priority": "low",
     "title": "Legitimate interest assessment documented",
     "description": "Where legitimate interests is used as legal basis, a legitimate interest assessment (LIA) balancing test must be conducted and documented.",
     "doc_type": None, "profile_question": None},

    {"id": "gdpr_19", "regulation": "GDPR", "article": "Art. 8", "priority": "medium",
     "title": "Children's data safeguards implemented",
     "description": "If services are directed at or likely to be accessed by children, appropriate safeguards must be in place including age verification and parental consent mechanisms.",
     "doc_type": None, "profile_question": None},

    {"id": "gdpr_20", "regulation": "GDPR", "article": "Art. 32", "priority": "medium",
     "title": "Technical and organisational security measures documented",
     "description": "Appropriate technical and organisational measures must be implemented and documented to ensure security of personal data, including encryption, pseudonymisation and access controls.",
     "doc_type": None, "profile_question": None},

    # ── NIS2 ─────────────────────────────────────────────────
    {"id": "nis2_01", "regulation": "NIS2", "article": "Art. 21", "priority": "high",
     "title": "Cybersecurity risk assessment conducted",
     "description": "A formal risk assessment identifying cybersecurity threats, vulnerabilities and their potential impact on network and information systems must be conducted and documented.",
     "doc_type": "incident_response", "profile_question": None},

    {"id": "nis2_02", "regulation": "NIS2", "article": "Art. 21", "priority": "high",
     "title": "Incident response plan documented",
     "description": "A documented incident response plan must exist covering detection, containment, eradication, recovery and post-incident review procedures.",
     "doc_type": "incident_response", "profile_question": None},

    {"id": "nis2_03", "regulation": "NIS2", "article": "Art. 23", "priority": "high",
     "title": "Incident reporting procedure (24h/72h)",
     "description": "A procedure must exist for reporting significant cybersecurity incidents to the national authority within 24 hours (early warning) and 72 hours (full notification).",
     "doc_type": "incident_response", "profile_question": None},

    {"id": "nis2_04", "regulation": "NIS2", "article": "Art. 21", "priority": "high",
     "title": "Business continuity plan in place",
     "description": "A business continuity plan addressing cybersecurity incidents must be documented, covering backup management, disaster recovery and crisis management procedures.",
     "doc_type": "incident_response", "profile_question": None},

    {"id": "nis2_05", "regulation": "NIS2", "article": "Art. 21", "priority": "high",
     "title": "Supply chain security policy",
     "description": "Security policies addressing risks from suppliers and third-party service providers must be documented, including security requirements in contracts.",
     "doc_type": None, "profile_question": None},

    {"id": "nis2_06", "regulation": "NIS2", "article": "Art. 21", "priority": "high",
     "title": "Access control and authentication policy",
     "description": "Policies governing access control, user authentication (including multi-factor authentication) and privileged access management must be documented and implemented.",
     "doc_type": None, "profile_question": None},

    {"id": "nis2_07", "regulation": "NIS2", "article": "Art. 21", "priority": "medium",
     "title": "Encryption policy for data in transit and at rest",
     "description": "A policy requiring encryption of personal and sensitive data both in transit and at rest must be documented and implemented.",
     "doc_type": None, "profile_question": None},

    {"id": "nis2_08", "regulation": "NIS2", "article": "Art. 21", "priority": "medium",
     "title": "Vulnerability management process",
     "description": "A process for identifying, assessing and remediating security vulnerabilities in systems, software and networks must be established.",
     "doc_type": None, "profile_question": None},

    {"id": "nis2_09", "regulation": "NIS2", "article": "Art. 21", "priority": "medium",
     "title": "Security awareness training for all staff",
     "description": "Regular cybersecurity awareness training must be provided to all employees covering threats, phishing, password hygiene and incident reporting.",
     "doc_type": None, "profile_question": "training"},

    {"id": "nis2_10", "regulation": "NIS2", "article": "Art. 21", "priority": "medium",
     "title": "Backup and recovery procedures documented",
     "description": "Documented backup procedures must exist including backup frequency, storage locations, retention periods and tested recovery procedures.",
     "doc_type": None, "profile_question": None},

    {"id": "nis2_11", "regulation": "NIS2", "article": "Art. 3", "priority": "high",
     "title": "Registered with national NIS2 authority",
     "description": "Essential and important entities must register with their national competent authority (CCB in Belgium, ANSSI in France) as required under NIS2.",
     "doc_type": None, "profile_question": "nis2_registered"},

    {"id": "nis2_12", "regulation": "NIS2", "article": "Art. 20", "priority": "high",
     "title": "Management body approved cybersecurity policy",
     "description": "The management body must approve the organisation's cybersecurity risk management measures and oversee their implementation.",
     "doc_type": None, "profile_question": None},

    {"id": "nis2_13", "regulation": "NIS2", "article": "Art. 21", "priority": "medium",
     "title": "Network security monitoring in place",
     "description": "Monitoring of network and information systems for cybersecurity events, anomalies and incidents must be implemented.",
     "doc_type": None, "profile_question": None},

    {"id": "nis2_14", "regulation": "NIS2", "article": "Art. 21", "priority": "low",
     "title": "Penetration testing conducted",
     "description": "Regular penetration testing of critical systems and networks to identify and address vulnerabilities before they can be exploited.",
     "doc_type": None, "profile_question": "pentest"},

    {"id": "nis2_15", "regulation": "NIS2", "article": "Art. 21", "priority": "low",
     "title": "Security audit trail maintained",
     "description": "Logs of security-relevant events must be maintained, protected from tampering and retained for a sufficient period for incident investigation.",
     "doc_type": None, "profile_question": None},

    # ── ePrivacy ─────────────────────────────────────────────
    {"id": "eprivacy_01", "regulation": "EPRIVACY", "article": "Art. 5(3)", "priority": "high",
     "title": "Cookie consent banner implemented",
     "description": "A cookie consent mechanism must be implemented that obtains valid consent before placing non-essential cookies, with clear accept/reject options.",
     "doc_type": "cookie_policy", "profile_question": "cookies"},

    {"id": "eprivacy_02", "regulation": "EPRIVACY", "article": "Art. 5(3)", "priority": "high",
     "title": "Cookie policy published",
     "description": "A cookie policy explaining what cookies are used, their purpose, duration and how users can manage their preferences must be published on the website.",
     "doc_type": "cookie_policy", "profile_question": "cookies"},

    {"id": "eprivacy_03", "regulation": "EPRIVACY", "article": "Art. 13", "priority": "high",
     "title": "Marketing email opt-in mechanism",
     "description": "Prior consent must be obtained before sending marketing emails. The consent mechanism must be clear and separate from other terms.",
     "doc_type": "privacy_policy", "profile_question": "marketing"},

    {"id": "eprivacy_04", "regulation": "EPRIVACY", "article": "Art. 13", "priority": "medium",
     "title": "Opt-out mechanism for marketing communications",
     "description": "Every marketing communication must include a clear and easy unsubscribe mechanism allowing recipients to opt out at any time.",
     "doc_type": None, "profile_question": "marketing"},

    {"id": "eprivacy_05", "regulation": "EPRIVACY", "article": "Art. 5(3)", "priority": "medium",
     "title": "Cookie consent records maintained",
     "description": "Records of cookie consents must be maintained to demonstrate that valid consent was obtained, including what was consented to and when.",
     "doc_type": None, "profile_question": "cookies"},
]

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
        "options": ["Yes", "No — essential cookies only", "We have no website"],
        "compliant_answers": ["No — essential cookies only", "We have no website"],
        "triggers_check": True,
    },
    "marketing": {
        "question": "Do you send marketing emails to prospects or customers?",
        "options": ["Yes", "No"],
        "compliant_answers": ["No"],
        "triggers_check": True,
    },
}

DOCUMENT_TYPE_LABELS = {
    "privacy_policy": "Privacy Policy",
    "cookie_policy": "Cookie Policy",
    "dpa": "Data Processing Agreement",
    "ropa": "Record of Processing Activities",
    "incident_response": "Incident Response Plan",
    "ai_transparency": "AI Transparency Notice",
}


# ── Document text extraction ──────────────────────────────────

def extract_text_from_upload(uploaded_file) -> str:
    """Extract text from an uploaded PDF or DOCX file."""
    name = uploaded_file.name.lower()
    content = uploaded_file.read()

    if name.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [p.extract_text() for p in reader.pages if p.extract_text()]
            return "\n\n".join(pages)
        except Exception as e:
            return ""

    elif name.endswith(".docx"):
        try:
            doc = DocxDocument(io.BytesIO(content))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            return ""

    elif name.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")

    return ""


# ── AI analysis engine ────────────────────────────────────────

def analyse_obligation(
    obligation: dict,
    document_text: str,
    profile_answers: dict,
    api_key: str,
) -> dict:
    """
    Analyse a single obligation against uploaded documents and profile answers.
    Returns: {id, status: compliant/partial/missing, explanation, recommendation}
    """
    ob_id = obligation["id"]

    # Profile-based obligations — no Mistral call needed
    if obligation["profile_question"]:
        q_key = obligation["profile_question"]
        answer = profile_answers.get(q_key, "")
        q_config = PROFILE_QUESTIONS.get(q_key, {})

        compliant = q_config.get("compliant_answers", [])
        partial = q_config.get("partial_answers", [])
        triggers = q_config.get("triggers_check", False)

        # If question doesn't apply (e.g. no cookies, no marketing)
        if triggers and answer in q_config.get("compliant_answers", []) and answer.startswith("No"):
            return {
                "id": ob_id,
                "status": "not_applicable",
                "explanation": f"Not applicable based on your profile: {answer}",
                "recommendation": "",
            }

        if answer in compliant:
            status = "compliant"
            explanation = f"Confirmed compliant: {answer}"
            recommendation = ""
        elif answer in partial:
            status = "partial"
            explanation = f"Partially compliant: {answer}"
            recommendation = "Formalise your training programme with documented evidence of completion."
        else:
            status = "missing"
            explanation = f"Not in place: {answer}"
            recommendation = f"Address this obligation: {obligation['title']}"

        return {"id": ob_id, "status": status,
                "explanation": explanation, "recommendation": recommendation}

    # Document-based obligations — use Mistral
    if not document_text.strip():
        return {
            "id": ob_id,
            "status": "missing",
            "explanation": "No documents uploaded to assess this obligation.",
            "recommendation": f"Generate a compliant {DOCUMENT_TYPE_LABELS.get(obligation.get('doc_type',''), 'document')} using COMPLAI.",
        }

    # Truncate document text for context (max ~3000 chars per obligation)
    doc_excerpt = document_text[:3000] if len(document_text) > 3000 else document_text

    system_prompt = """You are a EU compliance expert assessing whether an organisation's documents 
satisfy a specific regulatory obligation. Analyse the provided document excerpt and determine:
- compliant: the document clearly and adequately addresses this obligation
- partial: the document mentions the topic but incompletely or inadequately  
- missing: the document does not address this obligation at all

Respond ONLY with valid JSON in this exact format, no other text:
{
  "status": "compliant" | "partial" | "missing",
  "explanation": "one sentence explaining your assessment",
  "recommendation": "one sentence action recommendation (empty string if compliant)"
}"""

    user_prompt = f"""OBLIGATION: {obligation['title']}
REGULATION: {obligation['regulation']} {obligation['article']}
REQUIREMENT: {obligation['description']}

DOCUMENT EXCERPT:
{doc_excerpt}

Assess whether this document satisfies the obligation."""

    for attempt in range(3):
        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": "mistral-large-latest",
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 300,
                },
                timeout=30,
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
            result["id"] = ob_id
            return result
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
            else:
                return {
                    "id": ob_id,
                    "status": "missing",
                    "explanation": "Could not assess — analysis error.",
                    "recommendation": f"Manually verify: {obligation['title']}",
                }


def run_gap_assessment(
    document_texts: dict,
    profile_answers: dict,
    client: dict,
    language: str = "en",
) -> dict:
    """
    Run full gap assessment across all obligations.
    document_texts: {filename: text} — combined text used for analysis
    Returns structured assessment results.
    """
    api_key = os.environ.get("MISTRAL_API_KEY", "")

    # Combine all document texts
    combined_text = "\n\n===\n\n".join(document_texts.values()) if document_texts else ""

    results = []
    total = len(OBLIGATIONS)

    progress = st.progress(0, text="Starting gap assessment...")

    for i, obligation in enumerate(OBLIGATIONS):
        progress.progress(
            (i + 1) / total,
            text=f"Analysing {i+1}/{total}: {obligation['title'][:50]}..."
        )

        # Skip ePrivacy obligations if client doesn't use cookies/marketing
        if obligation["regulation"] == "EPRIVACY":
            if obligation["profile_question"] == "cookies":
                cookies_ans = profile_answers.get("cookies", "")
                if "No" in cookies_ans or "no website" in cookies_ans.lower():
                    results.append({
                        "id": obligation["id"],
                        "status": "not_applicable",
                        "explanation": "Not applicable — no non-essential cookies used.",
                        "recommendation": "",
                    })
                    continue
            if obligation["profile_question"] == "marketing":
                marketing_ans = profile_answers.get("marketing", "")
                if marketing_ans == "No":
                    results.append({
                        "id": obligation["id"],
                        "status": "not_applicable",
                        "explanation": "Not applicable — no marketing emails sent.",
                        "recommendation": "",
                    })
                    continue

        result = analyse_obligation(obligation, combined_text, profile_answers, api_key)
        results.append(result)

        # Small delay to avoid rate limiting
        if obligation["profile_question"] is None:
            time.sleep(0.5)

    progress.empty()

    # Calculate scores
    def calc_score(reg: str) -> int:
        reg_results = [
            r for r, o in zip(results, OBLIGATIONS)
            if o["regulation"] == reg and r["status"] != "not_applicable"
        ]
        if not reg_results:
            return 100
        compliant = sum(1 for r in reg_results if r["status"] == "compliant")
        partial = sum(1 for r in reg_results if r["status"] == "partial")
        total_reg = len(reg_results)
        return int((compliant + partial * 0.5) / total_reg * 100)

    score_gdpr = calc_score("GDPR")
    score_nis2 = calc_score("NIS2")
    score_eprivacy = calc_score("EPRIVACY")

    # Weight overall: GDPR 50%, NIS2 35%, ePrivacy 15%
    score_overall = int(score_gdpr * 0.5 + score_nis2 * 0.35 + score_eprivacy * 0.15)

    return {
        "results": results,
        "score_gdpr": score_gdpr,
        "score_nis2": score_nis2,
        "score_eprivacy": score_eprivacy,
        "score_overall": score_overall,
    }


# ── PDF report generation ─────────────────────────────────────

def generate_gap_report_pdf(
    assessment: dict,
    client: dict,
    profile_answers: dict,
) -> bytes:
    """Generate a PDF gap assessment report."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2*cm,
    )

    # Colors
    NAVY   = HexColor("#1B2A4A")
    PURPLE = HexColor("#4A3B8C")
    TEAL   = HexColor("#0F6E56")
    RED    = HexColor("#C0392B")
    AMBER  = HexColor("#E67E22")
    GREEN  = HexColor("#27AE60")
    LGRAY  = HexColor("#F4F3F0")
    MGRAY  = HexColor("#888888")

    styles = getSampleStyleSheet()

    def style(name, **kwargs):
        return ParagraphStyle(name, parent=styles["Normal"], **kwargs)

    S_TITLE    = style("title",    fontSize=22, textColor=NAVY,   leading=28, spaceAfter=6)
    S_SUBTITLE = style("subtitle", fontSize=12, textColor=PURPLE, leading=16, spaceAfter=4)
    S_DATE     = style("date",     fontSize=10, textColor=MGRAY,  leading=14, spaceAfter=16)
    S_H1       = style("h1",       fontSize=14, textColor=NAVY,   leading=20, spaceBefore=16, spaceAfter=6, fontName="Helvetica-Bold")
    S_H2       = style("h2",       fontSize=11, textColor=PURPLE, leading=16, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")
    S_BODY     = style("body",     fontSize=9,  textColor=black,  leading=14, spaceAfter=4)
    S_SMALL    = style("small",    fontSize=8,  textColor=MGRAY,  leading=12, spaceAfter=2)
    S_GAP      = style("gap",      fontSize=9,  textColor=black,  leading=13, spaceAfter=2)
    S_REC      = style("rec",      fontSize=9,  textColor=TEAL,   leading=13, spaceAfter=6, leftIndent=12)

    today = date.today().strftime("%d %B %Y")
    company = client.get("company_name", "")
    country = client.get("country", "")

    results_by_id = {r["id"]: r for r in assessment["results"]}

    story = []

    # ── Header ────────────────────────────────────────────────
    story.append(Paragraph("Gap Assessment Report", S_TITLE))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY))
    story.append(Spacer(1, 6))
    story.append(Paragraph(company, S_SUBTITLE))
    story.append(Paragraph(f"Generated by COMPLAI · {today}", S_DATE))

    # ── Executive summary ─────────────────────────────────────
    story.append(Paragraph("Executive Summary", S_H1))
    story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))
    story.append(Spacer(1, 8))

    def score_color(s):
        if s >= 75: return GREEN
        if s >= 50: return AMBER
        return RED

    score_data = [
        ["Regulation", "Score", "Status"],
        ["GDPR", f"{assessment['score_gdpr']}/100",
         "Good" if assessment['score_gdpr'] >= 75 else "Needs work" if assessment['score_gdpr'] >= 50 else "Critical gaps"],
        ["NIS2", f"{assessment['score_nis2']}/100",
         "Good" if assessment['score_nis2'] >= 75 else "Needs work" if assessment['score_nis2'] >= 50 else "Critical gaps"],
        ["ePrivacy", f"{assessment['score_eprivacy']}/100",
         "Good" if assessment['score_eprivacy'] >= 75 else "Needs work" if assessment['score_eprivacy'] >= 50 else "Critical gaps"],
        ["OVERALL", f"{assessment['score_overall']}/100",
         "Good" if assessment['score_overall'] >= 75 else "Needs work" if assessment['score_overall'] >= 50 else "Critical gaps"],
    ]

    score_table = Table(score_data, colWidths=[8*cm, 4*cm, 5*cm])
    score_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), NAVY),
        ("TEXTCOLOR",    (0,0), (-1,0), white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("BACKGROUND",   (0,-1), (-1,-1), LGRAY),
        ("FONTNAME",     (0,-1), (-1,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,1), (-1,-2), [white, HexColor("#F9F9F9")]),
        ("GRID",         (0,0), (-1,-1), 0.5, HexColor("#DDDDDD")),
        ("PADDING",      (0,0), (-1,-1), 8),
        ("ALIGN",        (1,0), (1,-1), "CENTER"),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 16))

    # Stats
    statuses = [r["status"] for r in assessment["results"]]
    n_compliant = statuses.count("compliant")
    n_partial   = statuses.count("partial")
    n_missing   = statuses.count("missing")
    n_na        = statuses.count("not_applicable")
    n_total     = len([s for s in statuses if s != "not_applicable"])

    story.append(Paragraph(
        f"Out of <b>{n_total}</b> applicable obligations assessed: "
        f"<font color='#27AE60'><b>{n_compliant} compliant</b></font>, "
        f"<font color='#E67E22'><b>{n_partial} partial</b></font>, "
        f"<font color='#C0392B'><b>{n_missing} missing</b></font>."
        + (f" {n_na} obligations were not applicable to your organisation." if n_na else ""),
        S_BODY
    ))

    story.append(PageBreak())

    # ── Gap analysis by regulation ────────────────────────────
    for regulation in ["GDPR", "NIS2", "EPRIVACY"]:
        reg_labels = {"GDPR": "GDPR", "NIS2": "NIS2 Directive", "EPRIVACY": "ePrivacy Directive"}
        reg_obligations = [o for o in OBLIGATIONS if o["regulation"] == regulation]

        story.append(Paragraph(reg_labels[regulation], S_H1))
        story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))

        for priority in ["high", "medium", "low"]:
            priority_obs = [o for o in reg_obligations if o["priority"] == priority]
            if not priority_obs:
                continue

            priority_results = [results_by_id.get(o["id"], {}) for o in priority_obs]
            has_issues = any(r.get("status") in ["partial","missing"]
                           for r in priority_results)
            if not has_issues:
                continue

            priority_labels = {"high": "🔴 High Priority", "medium": "🟡 Medium Priority", "low": "🔵 Low Priority"}
            story.append(Paragraph(priority_labels[priority], S_H2))

            for ob, result in zip(priority_obs, priority_results):
                status = result.get("status", "missing")
                if status in ("compliant", "not_applicable"):
                    continue

                status_icon = "⚠️" if status == "partial" else "❌"
                story.append(Paragraph(
                    f"{status_icon} <b>{ob['title']}</b> <font color='#888888'>({ob['article']})</font>",
                    S_GAP
                ))
                story.append(Paragraph(result.get("explanation", ""), S_SMALL))
                if result.get("recommendation"):
                    story.append(Paragraph(f"→ {result['recommendation']}", S_REC))
                if ob.get("doc_type"):
                    doc_label = DOCUMENT_TYPE_LABELS.get(ob["doc_type"], ob["doc_type"])
                    story.append(Paragraph(
                        f"📄 Generate a compliant {doc_label} in COMPLAI → Documents page",
                        S_REC
                    ))

        story.append(Spacer(1, 8))

    story.append(PageBreak())

    # ── What's compliant ──────────────────────────────────────
    story.append(Paragraph("What's Compliant", S_H1))
    story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))
    story.append(Spacer(1, 6))

    compliant_obs = [
        o for o in OBLIGATIONS
        if results_by_id.get(o["id"], {}).get("status") == "compliant"
    ]
    if compliant_obs:
        for ob in compliant_obs:
            story.append(Paragraph(f"✅ <b>{ob['title']}</b> ({ob['regulation']} {ob['article']})", S_GAP))
    else:
        story.append(Paragraph("No fully compliant obligations identified based on uploaded documents.", S_BODY))

    story.append(Spacer(1, 16))

    # ── Next steps ────────────────────────────────────────────
    story.append(Paragraph("Recommended Next Steps", S_H1))
    story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))
    story.append(Spacer(1, 6))

    # Prioritised action list
    step = 1
    for priority in ["high", "medium", "low"]:
        for ob in OBLIGATIONS:
            if ob["priority"] != priority:
                continue
            result = results_by_id.get(ob["id"], {})
            if result.get("status") not in ["partial", "missing"]:
                continue
            story.append(Paragraph(
                f"{step}. <b>{ob['title']}</b> ({ob['regulation']} {ob['article']})",
                S_GAP
            ))
            if result.get("recommendation"):
                story.append(Paragraph(f"   {result['recommendation']}", S_REC))
            step += 1
            if step > 10:
                break
        if step > 10:
            break

    story.append(Spacer(1, 24))

    # Footer
    story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Generated by COMPLAI · complai.be · {today} · "
        "This report is based on AI analysis of provided documents and self-reported information. "
        "It is a starting point and should be reviewed by a qualified legal or cybersecurity professional.",
        S_SMALL
    ))

    doc.build(story)
    return buf.getvalue()


# ── Supabase persistence ──────────────────────────────────────

def save_gap_assessment(
    user_id: str,
    client_id: str | None,
    assessment: dict,
    profile_answers: dict,
    pdf_bytes: bytes,
) -> str | None:
    """Save gap assessment to Supabase and upload PDF to storage."""
    from database import get_supabase, upload_file
    import re

    try:
        supabase = get_supabase()
        res = supabase.table("gap_assessments").insert({
            "user_id": user_id,
            "client_id": client_id,
            "regulations": ["GDPR", "NIS2", "EPRIVACY"],
            "score_gdpr": assessment["score_gdpr"],
            "score_nis2": assessment["score_nis2"],
            "score_eprivacy": assessment["score_eprivacy"],
            "score_overall": assessment["score_overall"],
            "gaps": assessment["results"],
            "profile_answers": profile_answers,
        }).execute()
        assessment_id = res.data[0]["id"] if res.data else None
    except Exception as e:
        st.warning(f"Could not save assessment record: {e}")
        return None

    # Upload PDF
    if pdf_bytes and assessment_id:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"{user_id}/{client_id or 'advisory'}/gap_reports/COMPLAI_gap_{timestamp}.pdf"
        stored = upload_file("compliance-files", path, pdf_bytes, "application/pdf")
        if stored:
            try:
                supabase.table("gap_assessments") \
                    .update({"file_path_pdf": path}) \
                    .eq("id", assessment_id) \
                    .execute()
            except Exception:
                pass

    return assessment_id


def load_gap_assessment_history(user_id: str, client_id: str | None) -> list[dict]:
    """Load past gap assessments for a client."""
    from database import get_supabase
    try:
        supabase = get_supabase()
        q = supabase.table("gap_assessments") \
            .select("id, created_at, score_overall, score_gdpr, score_nis2, score_eprivacy, file_path_pdf") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(10)
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception:
        return []
