import os
import io
import json
import uuid
import subprocess
import tempfile
import requests
import streamlit as st
from datetime import date
from rag import retrieve, Chunk
from database import get_supabase

# ── Constants ─────────────────────────────────────────────────

DOCUMENT_TYPES = {
    "privacy_policy": "Privacy Policy",
    "cookie_policy": "Cookie Policy",
    "dpa": "Data Processing Agreement (DPA)",
    "ropa": "Record of Processing Activities (RoPA)",
    "incident_response": "Incident Response Plan",
    "ai_transparency": "AI System Transparency Notice",
}

LEGAL_FORMS = {
    "BE": ["SRL", "SA", "SNC", "SCS", "SC", "ASBL", "Fondation", "Other"],
    "FR": ["SARL", "SAS", "SASU", "SA", "SNC", "Auto-entrepreneur", "Association", "Other"],
    "NL": ["BV", "NV", "VOF", "Eenmanszaak", "Other"],
    "DE": ["GmbH", "AG", "UG", "OHG", "Other"],
    "LU": ["SARL", "SA", "SNC", "Other"],
    "EU": ["SRL", "SARL", "GmbH", "Ltd", "Other"],
}

DPA_CONTACTS = {
    "BE": "Autorité de protection des données (APD) — apd-gba.be",
    "FR": "Commission Nationale de l'Informatique et des Libertés (CNIL) — cnil.fr",
    "NL": "Autoriteit Persoonsgegevens (AP) — autoriteitpersoonsgegevens.nl",
    "DE": "Bundesdatenschutzbeauftragter (BfDI) — bfdi.bund.de",
    "LU": "Commission Nationale pour la Protection des Données (CNPD) — cnpd.public.lu",
    "EU": "The relevant national data protection authority in your country of establishment",
}


# ── Supabase helpers ──────────────────────────────────────────

def load_intake(client_id: str, user_id: str, document_type: str) -> dict:
    """Load previously saved intake data for this client + document type."""
    try:
        supabase = get_supabase()
        res = supabase.table("document_intake") \
            .select("*") \
            .eq("client_id", client_id) \
            .eq("user_id", user_id) \
            .eq("document_type", document_type) \
            .execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


def save_intake(client_id: str, user_id: str, document_type: str, fields: dict) -> bool:
    """Save intake data — upsert on client_id + document_type."""
    try:
        supabase = get_supabase()
        record = {
            "user_id": user_id,
            "client_id": client_id,
            "document_type": document_type,
            **fields,
        }
        supabase.table("document_intake").upsert(
            record,
            on_conflict="client_id,document_type"
        ).execute()
        return True
    except Exception as e:
        st.error(f"Could not save intake data: {e}")
        return False


def update_client_profile(client_id: str, user_id: str, fields: dict) -> bool:
    """Update universal profile fields on the clients table."""
    try:
        supabase = get_supabase()
        supabase.table("clients") \
            .update(fields) \
            .eq("id", client_id) \
            .eq("user_id", user_id) \
            .execute()
        return True
    except Exception as e:
        st.error(f"Could not update client profile: {e}")
        return False


def save_document_record(user_id: str, client_id: str | None,
                          document_type: str, language: str,
                          company_name: str) -> bool:
    """Save a document generation record."""
    try:
        supabase = get_supabase()
        supabase.table("documents").insert({
            "user_id": user_id,
            "client_id": client_id,
            "document_type": document_type,
            "language": language,
            "company_name": company_name,
        }).execute()
        return True
    except Exception as e:
        return False


def load_document_history(user_id: str, client_id: str | None) -> list:
    """Load document generation history for a client."""
    try:
        supabase = get_supabase()
        q = supabase.table("documents") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("generated_at", desc=True) \
            .limit(20)
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception:
        return []




# ── AI suggestion engine ──────────────────────────────────────

def save_document_with_files(
    user_id: str,
    client_id: str | None,
    document_type: str,
    language: str,
    company_name: str,
    docx_bytes: bytes,
    pdf_bytes: bytes | None = None,
    odt_bytes: bytes | None = None,
) -> str | None:
    """Save document record and upload files to Supabase Storage. Returns document ID."""
    import re
    from datetime import datetime
    from database import upload_file, update_document_paths

    try:
        supabase = get_supabase()
        res = supabase.table("documents").insert({
            "user_id": user_id,
            "client_id": client_id,
            "document_type": document_type,
            "language": language,
            "company_name": company_name,
        }).execute()
        doc_id = res.data[0]["id"] if res.data else None
    except Exception as e:
        st.error(f"Could not save document record: {e}")
        return None

    if not doc_id:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = re.sub(r"[^a-zA-Z0-9_-]", "_", company_name)[:30]
    base_path = f"{user_id}/{client_id or 'advisory'}/COMPLAI_{document_type}_{safe_company}_{timestamp}"

    docx_path = upload_file(
        "compliance-files", f"{base_path}.docx", docx_bytes,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    pdf_path = None
    if pdf_bytes:
        pdf_path = upload_file(
            "compliance-files", f"{base_path}.pdf", pdf_bytes, "application/pdf"
        )

    # Upload ODT if available
    odt_path = None
    if odt_bytes:
        odt_path = upload_file(
            "compliance-files", f"{base_path}.odt", odt_bytes,
            "application/vnd.oasis.opendocument.text"
        )

    update_document_paths(doc_id, user_id, docx_path, pdf_path, odt_path)

    # Auto-register in client document repository as current version
    if client_id and docx_path:
        from database import register_client_document
        register_client_document(
            user_id=user_id,
            client_id=client_id,
            document_type=document_type,
            file_path=docx_path,
            source="complai_generated",
            change_comment=f"Generated by COMPLAI on {datetime.now().strftime('%Y-%m-%d')}",
        )

    return doc_id



def suggest_processing_activities(client: dict) -> dict:
    """
    Use Mistral to suggest likely processing activities, third-party processors
    and retention periods based on the client profile.
    Returns a dict with keys: activities, processors, retention.
    """
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not set")

    sector = client.get("sector", "Unknown")
    size = client.get("company_size", "Unknown")
    country = client.get("country", "BE")
    regulations = client.get("regulations", ["GDPR"])
    company_name = client.get("company_name", "the company")

    country_names = {"BE": "Belgium", "FR": "France", "NL": "Netherlands",
                     "DE": "Germany", "LU": "Luxembourg"}
    country_name = country_names.get(country, country)

    reg_str = ", ".join(regulations) if isinstance(regulations, list) else str(regulations)

    system_prompt = """You are a GDPR compliance expert helping SMEs identify their personal data processing activities.
Based on the company profile provided, generate a realistic and comprehensive list of:
1. Processing activities (what personal data they likely collect and process)
2. Third-party processors (tools and services they likely use)
3. Retention periods (how long they should keep each data type)

IMPORTANT:
- Be realistic and sector-specific — think about what a real company in this sector actually does
- Cover the obvious activities but also less obvious ones (employee data, security logs, etc.)
- For legal basis, choose the most appropriate GDPR Article 6 basis
- For processors, include common tools used in this sector
- Retention periods should follow Belgian/French legal requirements where applicable
- Return ONLY valid JSON, no other text

Return exactly this JSON structure:
{
  "activities": [
    {
      "name": "activity name",
      "subjects": "who the data is about",
      "data": "what personal data",
      "purpose": "why you collect it",
      "legal_basis": "one of: Contract performance (Art. 6(1)(b)) / Consent (Art. 6(1)(a)) / Legal obligation (Art. 6(1)(c)) / Legitimate interests (Art. 6(1)(f)) / Vital interests (Art. 6(1)(d)) / Public task (Art. 6(1)(e))"
    }
  ],
  "processors": [
    {
      "name": "service name",
      "country": "country of the service",
      "purpose": "what it does",
      "data": "what data is shared"
    }
  ],
  "retention": [
    {
      "data_type": "type of data",
      "duration": "how long to keep it"
    }
  ]
}"""

    user_prompt = f"""Company profile:
- Name: {company_name}
- Sector: {sector}
- Size: {size} employees
- Country: {country_name}
- Applicable regulations: {reg_str}

Generate a realistic list of GDPR processing activities for this company.
Include 5-8 processing activities, 3-6 processors, and 4-6 retention rules.
Cover: customer/client data, employee data, marketing, website analytics, and any sector-specific processing."""

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "mistral-large-latest",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 2048,
            "temperature": 0.3,
        },
        timeout=60,
    )
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    result = json.loads(raw)

    # Validate structure
    if "activities" not in result:
        result["activities"] = []
    if "processors" not in result:
        result["processors"] = []
    if "retention" not in result:
        result["retention"] = []

    return result

# ── RAG retrieval for document generation ────────────────────

def get_regulatory_context(document_type: str, language: str, country: str) -> str:
    """Retrieve relevant regulatory chunks for document generation."""
    query_map = {
        "privacy_policy": "GDPR privacy policy data controller obligations Articles 13 14 rights",
        "cookie_policy": "ePrivacy cookie consent tracking obligations",
        "dpa": "GDPR data processing agreement Article 28 processor obligations",
        "ropa": "GDPR record of processing activities Article 30",
        "incident_response": "NIS2 incident response plan cybersecurity measures Article 21 23",
        "ai_transparency": "EU AI Act transparency obligations Article 50 AI system disclosure",
    }
    query = query_map.get(document_type, "compliance obligations")

    try:
        chunks = retrieve(
            query=query,
            chunks=[],
            embeddings=None,
            top_k=12,
            language=language,
            country=country,
        )
        parts = [f"[{c.source}]\n{c.text}" for c in chunks]
        return "\n\n---\n\n".join(parts)
    except Exception:
        return ""


# ── Mistral document generation ───────────────────────────────

def generate_document_text(
    document_type: str,
    intake: dict,
    client: dict,
    language: str,
    regulatory_context: str,
) -> str:
    """Call Mistral to generate the document text."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not set")

    today_str = date.today().strftime("%d %B %Y")
    country = intake.get("country") or client.get("country", "BE")
    dpa_contact = DPA_CONTACTS.get(country, DPA_CONTACTS["EU"])

    lang_instructions = {
        "en": "Write in clear, professional British English.",
        "fr": "Rédigez en français juridique professionnel et clair.",
        "nl": "Schrijf in helder, professioneel juridisch Nederlands.",
    }
    lang_instr = lang_instructions.get(language, lang_instructions["en"])

    doc_prompts = {
        "privacy_policy": _privacy_policy_prompt(intake, client, today_str, dpa_contact),
        "cookie_policy": _cookie_policy_prompt(intake, client, today_str),
        "dpa": _dpa_prompt(intake, client, today_str),
        "ropa": _ropa_prompt(intake, client, today_str),
        "incident_response": _incident_response_prompt(intake, client, today_str),
        "ai_transparency": _ai_transparency_prompt(intake, client, today_str),
    }
    doc_prompt = doc_prompts.get(document_type, "")

    system_prompt = f"""You are an expert EU compliance lawyer drafting professional legal documents for SMEs.
{lang_instr}

IMPORTANT RULES:
- Write complete, legally sound documents ready for immediate use
- Use numbered section headings: "1. Title", "2. Title", "1.1 Sub-section" etc.
- Write in flowing legal prose paragraphs
- Use "- item" for bullet lists where needed
- Do NOT use markdown ## headers — use numbered headings only
- Do NOT use **bold** markers — write plain text
- Do NOT use [text](url) markdown links — write plain email addresses
- Do not include placeholder text like [INSERT NAME] — use the actual data provided
- Base all legal references on the regulatory context provided
- Include specific article references where relevant
- Today's date: {today_str}
- Data Protection Authority for this company: {dpa_contact}

REGULATORY CONTEXT:
{regulatory_context}
"""

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "mistral-large-latest",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": doc_prompt},
            ],
            "max_tokens": 8000,
        },
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()
    content_text = result["choices"][0]["message"]["content"]
    finish_reason = result["choices"][0].get("finish_reason", "")

    # If truncated, continue generation
    if finish_reason == "length":
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": doc_prompt},
            {"role": "assistant", "content": content_text},
            {"role": "user", "content": "Continue the document from where you left off. Do not repeat what you already wrote. Continue with the next section."},
        ]
        cont_response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistral-large-latest",
                "temperature": 0.3,
                "messages": messages,
                "max_tokens": 4000,
            },
            timeout=120,
        )
        if cont_response.status_code == 200:
            content_text += "\n" + cont_response.json()["choices"][0]["message"]["content"]

    return content_text


def _privacy_policy_prompt(intake: dict, client: dict, today: str, dpa: str) -> str:
    company = f"{intake.get('legal_name') or client.get('company_name', 'The Company')} {intake.get('legal_form', '')}".strip()
    country = intake.get('country') or client.get('country', 'BE')
    return f"""Draft a complete GDPR-compliant Privacy Policy for the following company:

COMPANY DETAILS:
- Legal name: {company}
- Country: {country}
- Sector: {client.get('sector', 'Not specified')}
- Website: {intake.get('website_url') or client.get('website_url', 'Not specified')}
- DPO: {intake.get('dpo_name', 'None appointed')} — {intake.get('dpo_email', '')}
- Contact for data requests: {intake.get('contact_email', '')}

PROCESSING ACTIVITIES:
{intake.get('processing_activities', 'Not specified')}

THIRD-PARTY PROCESSORS:
{intake.get('third_party_processors', 'None specified')}

INTERNATIONAL TRANSFERS: {'Yes' if intake.get('international_transfers') else 'No'}

RETENTION PERIODS:
{intake.get('retention_periods', 'Not specified')}

The document MUST explicitly cover ALL of the following sections:

1. Identity and contact details of the data controller
2. DPO contact details (if applicable) or statement that no DPO is required
3. What personal data we collect, from whom, and why
4. Legal basis for EACH processing activity (Article 6 GDPR) — state the specific basis
5. Special category data: if any special category data (health, biometric, racial, religious, etc.)
   is processed, explicitly state the Article 9(2) GDPR legal ground and additional safeguards
6. Data minimisation: for each processing activity, explain why each data category is necessary
   and limited to what is strictly required for the stated purpose (Art. 5(1)(c))
7. Retention periods for each data category — specific durations, not vague statements
8. Recipients and third-party processors with their role and country
9. International transfers: if applicable, state the transfer mechanism (adequacy decision, SCCs, etc.)
10. Data subject rights (Articles 15-22 GDPR) — list ALL rights with concrete procedures:
    - Right of access (Art. 15): how to submit a request, response timeframe (1 month, extendable to 3)
    - Right to rectification (Art. 16): process for correcting inaccurate data
    - Right to erasure (Art. 17): conditions and process for deletion requests
    - Right to restriction (Art. 18): when and how processing can be restricted
    - Right to data portability (Art. 20): format and delivery method
    - Right to object (Art. 21): how to object to processing
    - Rights re automated decision-making (Art. 22): if applicable
    Include: exact contact email/address for requests, 1-month response timeframe, right to appeal
11. How to exercise rights — step-by-step: "Submit your request to [contact], we will respond within
    30 days, you may escalate to {dpa} if unsatisfied"
12. Right to lodge a complaint with {dpa} — include the authority name and website
13. Technical and organisational security measures (Art. 32) — explicitly describe:
    - Encryption (data in transit via TLS, data at rest)
    - Access controls (role-based access, authentication)
    - Pseudonymisation where applied
    - Staff training on data protection
    - Regular security assessments
    - Data breach detection and response procedures
14. Automated decision-making and profiling (if applicable)
15. Changes to this policy — how users will be notified
16. Effective date: {today}"""


def _cookie_policy_prompt(intake: dict, client: dict, today: str) -> str:
    company = f"{intake.get('legal_name') or client.get('company_name', 'The Company')} {intake.get('legal_form', '')}".strip()
    return f"""Draft a complete ePrivacy-compliant Cookie Policy for:

COMPANY: {company}
WEBSITE: {intake.get('website_url') or client.get('website_url', 'Not specified')}
COOKIES USED: {intake.get('third_party_processors', 'Not specified')}

Cover: what cookies are, categories (strictly necessary / analytics / marketing),
specific cookies used with purpose and duration, how to manage/refuse consent,
contact details, effective date: {today}"""


def _dpa_prompt(intake: dict, client: dict, today: str) -> str:
    company = f"{intake.get('legal_name') or client.get('company_name', 'The Company')} {intake.get('legal_form', '')}".strip()
    return f"""Draft a GDPR Article 28 compliant Data Processing Agreement between:

CONTROLLER: {company}
PROCESSOR: {intake.get('processor_name', 'The Processor')} ({intake.get('processor_country', '')})
PURPOSE OF PROCESSING: {intake.get('processing_purpose', 'Not specified')}
PERSONAL DATA INVOLVED: {intake.get('processing_activities', 'Not specified')}

Cover all mandatory Article 28(3) clauses: processing only on instructions,
confidentiality, security measures, sub-processors, data subject rights assistance,
deletion/return of data, audit rights. Effective date: {today}"""


def _ropa_prompt(intake: dict, client: dict, today: str) -> str:
    company = f"{intake.get('legal_name') or client.get('company_name', 'The Company')} {intake.get('legal_form', '')}".strip()
    return f"""Draft a GDPR Article 30 Record of Processing Activities (RoPA) for:

COMPANY: {company}
SECTOR: {client.get('sector', 'Not specified')}
PROCESSING ACTIVITIES: {intake.get('processing_activities', 'Not specified')}
THIRD PARTIES: {intake.get('third_party_processors', 'None')}
RETENTION: {intake.get('retention_periods', 'Not specified')}
DPO: {intake.get('dpo_name', 'None')} — {intake.get('dpo_email', '')}

Format as a structured table for each processing activity covering:
name of activity, purpose, legal basis, categories of data subjects,
categories of data, recipients, transfers, retention period, security measures.
Date: {today}"""


def _incident_response_prompt(intake: dict, client: dict, today: str) -> str:
    company = f"{intake.get('legal_name') or client.get('company_name', 'The Company')} {intake.get('legal_form', '')}".strip()
    return f"""Draft a NIS2-compliant Incident Response Plan for:

COMPANY: {company}
SECTOR: {client.get('sector', 'Not specified')}
COUNTRY: {client.get('country', 'BE')}
INCIDENT CONTACT: {intake.get('incident_response_contact', 'Not specified')}
ESCALATION PROCEDURE: {intake.get('escalation_procedure', 'Not specified')}
SIZE: {client.get('company_size', 'Not specified')} employees

Cover: scope and objectives, incident classification (low/medium/high/critical),
detection and reporting procedures, NIS2 72-hour notification requirement to national
authority (CCB for Belgium / ANSSI for France), internal escalation chain,
containment and recovery procedures, post-incident review, training requirements.
Date: {today}"""


def _ai_transparency_prompt(intake: dict, client: dict, today: str) -> str:
    company = f"{intake.get('legal_name') or client.get('company_name', 'The Company')} {intake.get('legal_form', '')}".strip()
    return f"""Draft an EU AI Act Article 50 compliant AI System Transparency Notice for:

COMPANY: {company}
AI SYSTEM DESCRIPTION: {intake.get('processing_activities', 'AI-powered system interacting with users')}
CONTACT: {intake.get('contact_email', '')}

Cover: disclosure that users are interacting with an AI system, purpose of the AI system,
limitations and when human oversight applies, how to request human review,
data processed by the AI system, contact for questions. Date: {today}"""


# ── DOCX builder ──────────────────────────────────────────────

def build_docx(document_text: str, document_type: str,
               company_name: str, language: str) -> bytes:
    """Build a professional DOCX using python-docx with full markdown parsing."""
    import re

    def sanitize(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'[--]', '', text)
        text = text.replace(' ', ' ').replace('’', "'").replace('‘', "'")
        text = text.replace('“', '"').replace('”', '"')
        text = text.replace('–', '-').replace('—', '--')
        text = text.replace('…', '...')
        return text.encode('utf-8', errors='ignore').decode('utf-8')

    document_text = sanitize(document_text)
    company_name = sanitize(company_name)

    # Sanitize text — remove control characters and invalid XML chars
    # that lxml cannot handle
    def sanitize(text: str) -> str:
        if not text:
            return ""
        # Remove XML-illegal control characters (except tab, newline, carriage return)
        text = re.sub(r'[--]', '', text)
        # Replace non-breaking spaces and other problematic unicode
        text = text.replace(' ', ' ').replace('’', "'").replace('‘', "'")
        text = text.replace('“', '"').replace('”', '"')
        text = text.replace('–', '-').replace('—', '--')
        text = text.replace('…', '...')
        # Ensure valid UTF-8 by encoding and decoding
        return text.encode('utf-8', errors='ignore').decode('utf-8')

    document_text = sanitize(document_text)
    company_name = sanitize(company_name)
    from docx import Document as DocxDocument
    from docx.shared import Pt, RGBColor, Inches, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc_title = DOCUMENT_TYPES.get(document_type, "Compliance Document")
    today = date.today().strftime("%d %B %Y")

    doc = DocxDocument()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3)
        section.right_margin = Cm(2.5)

    # Define styles
    styles = doc.styles

    def set_run_font(run, size=10, bold=False, italic=False,
                     color=(0x33,0x33,0x33)):
        run.font.name = "Arial"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = RGBColor(*color)

    def add_para_spacing(p, before=0, after=6):
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.space_after = Pt(after)

    def add_border_bottom(p, color="D3D1C7"):
        """Add bottom border to paragraph."""
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), color)
        pBdr.append(bottom)
        pPr.append(pBdr)

    def parse_inline(p, text):
        """Parse inline markdown: **bold**, *italic*, strip [text](url) to text."""
        if not text:
            return
        # Sanitize
        text = re.sub(r'[--]', '', text)
        # Strip markdown links: [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'', text)
        # Parse bold+italic ***text***
        parts = re.split(r'(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)', text)
        for part in parts:
            if part.startswith('***') and part.endswith('***'):
                run = p.add_run(part[3:-3])
                set_run_font(run, bold=True, italic=True)
            elif part.startswith('**') and part.endswith('**'):
                run = p.add_run(part[2:-2])
                set_run_font(run, bold=True)
            elif part.startswith('*') and part.endswith('*'):
                run = p.add_run(part[1:-1])
                set_run_font(run, italic=True)
            elif part.startswith('`') and part.endswith('`'):
                run = p.add_run(part[1:-1])
                set_run_font(run, color=(0x44,0x44,0x44))
            else:
                if part:
                    run = p.add_run(part)
                    set_run_font(run)

    # ── Document header ───────────────────────────────────────
    # Title block
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_para_spacing(p, before=0, after=4)
    run = p.add_run(doc_title)
    run.font.name = "Arial"
    run.font.size = Pt(22)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1B, 0x2A, 0x4A)
    add_border_bottom(p, "1B2A4A")

    p2 = doc.add_paragraph()
    add_para_spacing(p2, before=6, after=2)
    run2 = p2.add_run(company_name)
    run2.font.name = "Arial"
    run2.font.size = Pt(13)
    run2.font.color.rgb = RGBColor(0x4A, 0x3B, 0x8C)

    p3 = doc.add_paragraph()
    add_para_spacing(p3, before=0, after=16)
    run3 = p3.add_run(today)
    run3.font.name = "Arial"
    run3.font.size = Pt(10)
    run3.font.italic = True
    run3.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    # ── Parse document text ───────────────────────────────────
    lines = document_text.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Skip duplicate title lines that Mistral often adds
        if line.strip('# ').strip() == doc_title or line.strip('# ').strip() == company_name:
            i += 1
            continue

        # Blank line
        if not line.strip():
            p = doc.add_paragraph()
            add_para_spacing(p, before=0, after=2)
            i += 1
            continue

        # H1: # Title or 1. Title
        if re.match(r'^#{1,2}\s+', line) or re.match(r'^\d+\.\s+[A-Z]', line):
            clean = re.sub(r'^#{1,2}\s+', '', line).strip()
            clean = re.sub(r'^\d+\.\s+', '', clean)
            # Restore number prefix for numbered headings
            m = re.match(r'^(\d+\.\s+)(.*)', line)
            if m:
                clean = m.group(1) + re.sub(r'^#{1,2}\s+', '', m.group(2))
            else:
                clean = re.sub(r'^#{1,2}\s+', '', line)
            p = doc.add_paragraph()
            add_para_spacing(p, before=14, after=4)
            add_border_bottom(p, "D3D1C7")
            run = p.add_run(clean)
            run.font.name = "Arial"
            run.font.size = Pt(13)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x1B, 0x2A, 0x4A)
            i += 1
            continue

        # H2: ## Title or 1.1 Title
        if re.match(r'^###\s+', line) or re.match(r'^\d+\.\d+\s+[A-Z]', line):
            clean = re.sub(r'^#{2,3}\s+', '', line).strip()
            p = doc.add_paragraph()
            add_para_spacing(p, before=10, after=3)
            run = p.add_run(clean)
            run.font.name = "Arial"
            run.font.size = Pt(11)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x4A, 0x3B, 0x8C)
            i += 1
            continue

        # Bullet: - or * or •
        if re.match(r'^[-*•]\s+', line):
            clean = re.sub(r'^[-*•]\s+', '', line)
            p = doc.add_paragraph(style='List Bullet')
            add_para_spacing(p, before=1, after=1)
            p.paragraph_format.left_indent = Cm(1)
            parse_inline(p, clean)
            i += 1
            continue

        # Numbered list: 1. item (but NOT section headings)
        m_num = re.match(r'^(\d+)\.\s+(.+)', line)
        if m_num and not re.match(r'^\d+\.\s+[A-Z][A-Z]', line):
            p = doc.add_paragraph(style='List Number')
            add_para_spacing(p, before=1, after=1)
            parse_inline(p, m_num.group(2))
            i += 1
            continue

        # Horizontal rule ---
        if re.match(r'^-{3,}$', line.strip()):
            p = doc.add_paragraph()
            add_border_bottom(p, "D3D1C7")
            add_para_spacing(p, before=4, after=4)
            i += 1
            continue

        # Body text
        p = doc.add_paragraph()
        add_para_spacing(p, before=0, after=5)
        p.paragraph_format.line_spacing = Pt(14)
        parse_inline(p, line)
        i += 1

    # Footer
    doc.add_paragraph()
    p = doc.add_paragraph()
    add_border_bottom(p, "D3D1C7")
    add_para_spacing(p, before=0, after=4)
    p = doc.add_paragraph()
    add_para_spacing(p, before=4, after=0)
    run = p.add_run(
        f"Generated by COMPLAI · complai.be · {today} · "
        "This document is a starting point and should be reviewed by a qualified legal professional."
    )
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Convert DOCX bytes to PDF using LibreOffice."""
    import shutil

    # Find soffice.py — try multiple locations
    soffice_candidates = [
        '/mnt/skills/public/docx/scripts/office/soffice.py',
        '/mnt/skills/public/pptx/scripts/office/soffice.py',
    ]
    soffice_script = next((p for p in soffice_candidates if os.path.exists(p)), None)

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, 'document.docx')
        pdf_path = os.path.join(tmpdir, 'document.pdf')

        with open(docx_path, 'wb') as f:
            f.write(docx_bytes)

        if soffice_script:
            result = subprocess.run(
                ['python3', soffice_script,
                 '--headless', '--convert-to', 'pdf', docx_path, '--outdir', tmpdir],
                capture_output=True, text=True, timeout=60
            )
        else:
            # Fallback: call soffice directly
            result = subprocess.run(
                ['soffice', '--headless', '--convert-to', 'pdf',
                 '--outdir', tmpdir, docx_path],
                capture_output=True, text=True, timeout=60
            )

        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                return f.read()
        raise RuntimeError(f"PDF conversion failed: {result.stderr or result.stdout}")


def convert_docx_to_odt(docx_bytes: bytes) -> bytes:
    """Convert DOCX bytes to ODT using LibreOffice."""
    soffice_candidates = [
        '/mnt/skills/public/docx/scripts/office/soffice.py',
        '/mnt/skills/public/pptx/scripts/office/soffice.py',
    ]
    soffice_script = next((p for p in soffice_candidates if os.path.exists(p)), None)

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, 'document.docx')
        odt_path = os.path.join(tmpdir, 'document.odt')

        with open(docx_path, 'wb') as f:
            f.write(docx_bytes)

        if soffice_script:
            result = subprocess.run(
                ['python3', soffice_script,
                 '--headless', '--convert-to', 'odt', docx_path, '--outdir', tmpdir],
                capture_output=True, text=True, timeout=60
            )
        else:
            result = subprocess.run(
                ['soffice', '--headless', '--convert-to', 'odt',
                 '--outdir', tmpdir, docx_path],
                capture_output=True, text=True, timeout=60
            )

        if os.path.exists(odt_path):
            with open(odt_path, 'rb') as f:
                return f.read()
        raise RuntimeError(f"ODT conversion failed: {result.stderr or result.stdout}")
