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
- Use clear section headings (numbered: 1., 2., 3. etc.)
- Write in flowing legal prose — no bullet points inside sections
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
            "max_tokens": 4096,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _privacy_policy_prompt(intake: dict, client: dict, today: str, dpa: str) -> str:
    company = f"{intake.get('legal_name') or client.get('company_name', 'The Company')} {intake.get('legal_form', '')}".strip()
    return f"""Draft a complete GDPR-compliant Privacy Policy for the following company:

COMPANY DETAILS:
- Legal name: {company}
- Country: {intake.get('country') or client.get('country', 'BE')}
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

The document must cover:
1. Identity and contact details of the data controller
2. DPO contact (if applicable)
3. What personal data we collect and why
4. Legal basis for each processing activity (Article 6 GDPR)
5. Retention periods
6. Recipients and third-party processors
7. International transfers (if applicable)
8. Data subject rights (Articles 15-22 GDPR)
9. How to exercise rights
10. Right to lodge a complaint with {dpa}
11. Automated decision-making (if applicable)
12. Changes to this policy
13. Effective date: {today}"""


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
    """Build a professional DOCX from generated text using docx-js via Node."""

    doc_title = DOCUMENT_TYPES.get(document_type, "Compliance Document")
    today = date.today().strftime("%d %B %Y")

    # Parse sections from generated text
    # Split on numbered headings like "1.", "2.", "1.1" etc.
    import re
    lines = document_text.strip().split('\n')

    js_paragraphs = []

    # Title
    js_paragraphs.append(f"""
new Paragraph({{
  heading: HeadingLevel.TITLE,
  children: [new TextRun({{ text: {json.dumps(doc_title)}, font: "Arial", size: 40, bold: true, color: "1B2A4A" }})]
}})""")

    # Company + date subtitle
    js_paragraphs.append(f"""
new Paragraph({{
  children: [new TextRun({{ text: {json.dumps(company_name)}, font: "Arial", size: 24, color: "4A3B8C" }})]
}})""")

    js_paragraphs.append(f"""
new Paragraph({{
  children: [new TextRun({{ text: {json.dumps(today)}, font: "Arial", size: 20, color: "888888", italics: true }})]
}})""")

    js_paragraphs.append("""
new Paragraph({ children: [new TextRun({ text: "" })] })""")

    # Process each line
    heading1_re = re.compile(r'^(\d+)\.\s+(.+)')
    heading2_re = re.compile(r'^(\d+\.\d+)\s+(.+)')

    for line in lines:
        line = line.strip()
        if not line:
            js_paragraphs.append("""
new Paragraph({ children: [new TextRun({ text: "" })] })""")
            continue

        m2 = heading2_re.match(line)
        m1 = heading1_re.match(line)

        if m2:
            text = m2.group(0)
            js_paragraphs.append(f"""
new Paragraph({{
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun({{ text: {json.dumps(text)}, font: "Arial", size: 24, bold: true, color: "4A3B8C" }})]
}})""")
        elif m1:
            text = m1.group(0)
            js_paragraphs.append(f"""
new Paragraph({{
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({{ text: {json.dumps(text)}, font: "Arial", size: 28, bold: true, color: "1B2A4A" }})]
}})""")
        else:
            # Body text — handle bold **text**
            safe = json.dumps(line)
            js_paragraphs.append(f"""
new Paragraph({{
  children: [new TextRun({{ text: {safe}, font: "Arial", size: 22 }})],
  spacing: {{ after: 120 }}
}})""")

    children_str = ",\n".join(js_paragraphs)

    js_code = f"""
const {{ Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
         Header, Footer, PageNumber, BorderStyle, LevelFormat }} = require('docx');
const fs = require('fs');

const doc = new Document({{
  styles: {{
    default: {{ document: {{ run: {{ font: "Arial", size: 22 }} }} }},
    paragraphStyles: [
      {{ id: "Title", name: "Title", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: {{ size: 40, bold: true, font: "Arial", color: "1B2A4A" }},
        paragraph: {{ spacing: {{ before: 0, after: 240 }} }} }},
      {{ id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: {{ size: 28, bold: true, font: "Arial", color: "1B2A4A" }},
        paragraph: {{ spacing: {{ before: 360, after: 120 }}, outlineLevel: 0,
          border: {{ bottom: {{ style: BorderStyle.SINGLE, size: 4, color: "D3D1C7", space: 1 }} }} }} }},
      {{ id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: {{ size: 24, bold: true, font: "Arial", color: "4A3B8C" }},
        paragraph: {{ spacing: {{ before: 240, after: 80 }}, outlineLevel: 1 }} }},
    ]
  }},
  sections: [{{
    properties: {{
      page: {{
        size: {{ width: 11906, height: 16838 }},
        margin: {{ top: 1440, right: 1440, bottom: 1440, left: 1440 }}
      }}
    }},
    headers: {{
      default: new Header({{
        children: [new Paragraph({{
          children: [
            new TextRun({{ text: {json.dumps(doc_title)}, font: "Arial", size: 18, color: "888888" }}),
            new TextRun({{ text: "   |   " + {json.dumps(company_name)}, font: "Arial", size: 18, color: "888888" }}),
          ],
          border: {{ bottom: {{ style: BorderStyle.SINGLE, size: 4, color: "D3D1C7", space: 1 }} }}
        }})]
      }})
    }},
    footers: {{
      default: new Footer({{
        children: [new Paragraph({{
          children: [
            new TextRun({{ text: "Generated by COMPLAI · complai.be   |   Page ", font: "Arial", size: 16, color: "888888" }}),
            new PageNumber({{ font: "Arial", size: 16, color: "888888" }}),
          ],
          alignment: AlignmentType.RIGHT,
          border: {{ top: {{ style: BorderStyle.SINGLE, size: 4, color: "D3D1C7", space: 1 }} }}
        }})]
      }})
    }},
    children: [
      {children_str}
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync(process.argv[2], buf);
  console.log('ok');
}});
"""

    # Write JS to temp file and run
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
        f.write(js_code)
        js_path = f.name

    out_path = js_path.replace('.js', '.docx')

    try:
        result = subprocess.run(
            ['node', js_path, out_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"Node error: {result.stderr}")

        with open(out_path, 'rb') as f:
            return f.read()
    finally:
        for p in [js_path, out_path]:
            try:
                os.unlink(p)
            except Exception:
                pass


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Convert DOCX bytes to PDF using LibreOffice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, 'document.docx')
        pdf_path = os.path.join(tmpdir, 'document.pdf')

        with open(docx_path, 'wb') as f:
            f.write(docx_bytes)

        result = subprocess.run(
            ['python3', '/mnt/skills/public/docx/scripts/office/soffice.py',
             '--headless', '--convert-to', 'pdf', docx_path, '--outdir', tmpdir],
            capture_output=True, text=True, timeout=60
        )

        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                return f.read()
        raise RuntimeError(f"PDF conversion failed: {result.stderr}")


def convert_docx_to_odt(docx_bytes: bytes) -> bytes:
    """Convert DOCX bytes to ODT using LibreOffice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, 'document.docx')
        odt_path = os.path.join(tmpdir, 'document.odt')

        with open(docx_path, 'wb') as f:
            f.write(docx_bytes)

        result = subprocess.run(
            ['python3', '/mnt/skills/public/docx/scripts/office/soffice.py',
             '--headless', '--convert-to', 'odt', docx_path, '--outdir', tmpdir],
            capture_output=True, text=True, timeout=60
        )

        if os.path.exists(odt_path):
            with open(odt_path, 'rb') as f:
                return f.read()
        raise RuntimeError(f"ODT conversion failed: {result.stderr}")
