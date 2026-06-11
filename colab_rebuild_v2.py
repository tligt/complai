# ============================================================
# COMPLAI — Sprint 7: Knowledge Base Re-ingestion
# Article-level chunking + enriched metadata
#
# HOW TO USE:
# 1. Open Google Colab
# 2. Upload all PDF files when prompted
# 3. Fill in your API keys in the CONFIGURATION section
# 4. Run all cells in order
# ============================================================

# ── Cell 1: Install dependencies ─────────────────────────────
# !pip install pypdf qdrant-client requests beautifulsoup4

# ── Cell 2: Imports and configuration ────────────────────────
import re
import os
import uuid
import time
import requests
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    PayloadSchemaType
)

# ── CONFIGURATION — fill these in ────────────────────────────
QDRANT_URL      = "your-qdrant-url"
QDRANT_API_KEY  = "your-qdrant-api-key"
MISTRAL_API_KEY = "your-mistral-api-key"

COLLECTION_NAME      = "regulations"
VECTOR_SIZE          = 1024
MAX_TOKENS_PER_CHUNK = 400
OVERLAP_TOKENS       = 50

# ── Enforcement dates per regulation ─────────────────────────
# Enforcement dates per regulation.
# Per-article overrides removed — phased timelines (e.g. EU AI Act)
# are handled via the system prompt instead.
ENFORCEMENT_CONFIG = {
    "GDPR":           {"default_date": "2018-05-25", "default_status": "in_force",  "provisions": {}},
    "NIS2":           {"default_date": "2024-10-18", "default_status": "in_force",  "provisions": {}},
    "EU_AI_ACT":      {"default_date": "2024-08-01", "default_status": "in_force",  "provisions": {}},
    "EPRIVACY":       {"default_date": "2003-07-31", "default_status": "in_force",  "provisions": {}},
    "CONSUMER_RIGHTS":{"default_date": "2011-10-25", "default_status": "in_force",  "provisions": {}},
    "EAA":            {"default_date": "2025-06-28", "default_status": "in_force",  "provisions": {}},
}

# ── PDF documents ─────────────────────────────────────────────
PDF_DOCUMENTS = [
    # ── GDPR ──────────────────────────────────────────────────
    {"filename": "gdpr_en.pdf",           "source": "GDPR",                                      "parent_regulation": "GDPR",           "language": "en", "country": "EU", "doc_type": "core"},
    {"filename": "gdpr_fr.pdf",           "source": "RGPD",                                      "parent_regulation": "GDPR",           "language": "fr", "country": "EU", "doc_type": "core"},
    {"filename": "gdpr_nl.pdf",           "source": "AVG",                                       "parent_regulation": "GDPR",           "language": "nl", "country": "EU", "doc_type": "core"},
    # ── NIS2 ──────────────────────────────────────────────────
    {"filename": "nis2_en.pdf",           "source": "NIS2 Directive",                            "parent_regulation": "NIS2",           "language": "en", "country": "EU", "doc_type": "core"},
    {"filename": "nis2_fr.pdf",           "source": "Directive NIS2",                            "parent_regulation": "NIS2",           "language": "fr", "country": "EU", "doc_type": "core"},
    {"filename": "nis2_nl.pdf",           "source": "NIS2 Richtlijn",                            "parent_regulation": "NIS2",           "language": "nl", "country": "EU", "doc_type": "core"},
    # ── EU AI Act ──────────────────────────────────────────────
    {"filename": "aiact_en.pdf",      "source": "EU AI Act",                                 "parent_regulation": "EU_AI_ACT",      "language": "en", "country": "EU", "doc_type": "core"},
    {"filename": "aiact_fr.pdf",      "source": "Acte IA européen",                          "parent_regulation": "EU_AI_ACT",      "language": "fr", "country": "EU", "doc_type": "core"},
    {"filename": "aiact_nl.pdf",      "source": "EU AI Verordening",                         "parent_regulation": "EU_AI_ACT",      "language": "nl", "country": "EU", "doc_type": "core"},
    # ── ePrivacy ──────────────────────────────────────────────
    {"filename": "CELEX_32002L0058_EN_TXT.pdf", "source": "ePrivacy Directive",                  "parent_regulation": "EPRIVACY",       "language": "en", "country": "EU", "doc_type": "core"},
    {"filename": "CELEX_32002L0058_FR_TXT.pdf", "source": "Directive ePrivacy",                  "parent_regulation": "EPRIVACY",       "language": "fr", "country": "EU", "doc_type": "core"},
    {"filename": "CELEX_32002L0058_NL_TXT.pdf", "source": "ePrivacy Richtlijn",                  "parent_regulation": "EPRIVACY",       "language": "nl", "country": "EU", "doc_type": "core"},
    # ── Consumer Rights ───────────────────────────────────────
    {"filename": "CELEX_32011L0083_EN_TXT.pdf", "source": "Consumer Rights Directive",           "parent_regulation": "CONSUMER_RIGHTS","language": "en", "country": "EU", "doc_type": "core"},
    {"filename": "CELEX_32011L0083_FR_TXT.pdf", "source": "Directive Droits des Consommateurs",  "parent_regulation": "CONSUMER_RIGHTS","language": "fr", "country": "EU", "doc_type": "core"},
    {"filename": "CELEX_32011L0083_NL_TXT.pdf", "source": "Richtlijn Consumentenrechten",        "parent_regulation": "CONSUMER_RIGHTS","language": "nl", "country": "EU", "doc_type": "core"},
    # ── EAA ───────────────────────────────────────────────────
    {"filename": "CELEX_32019L0882_EN_TXT.pdf", "source": "European Accessibility Act",          "parent_regulation": "EAA",            "language": "en", "country": "EU", "doc_type": "core"},
    {"filename": "CELEX_32019L0882_FR_TXT.pdf", "source": "Acte européen accessibilité",         "parent_regulation": "EAA",            "language": "fr", "country": "EU", "doc_type": "core"},
    {"filename": "CELEX_32019L0882_NL_TXT.pdf", "source": "Europese Toegankelijkheidswet",       "parent_regulation": "EAA",            "language": "nl", "country": "EU", "doc_type": "core"},
    # ── EDPB Guidelines ───────────────────────────────────────
    {"filename": "edpb_guidelines_202402_article48_v2_en.pdf", "source": "EDPB Guidelines 2024/02 Art.48", "parent_regulation": "GDPR", "language": "en", "country": "EU", "doc_type": "supplementary"},
    {"filename": "edpb_guidelines_202402_article48_v2_fr.pdf", "source": "Lignes directrices EDPB 2024/02 Art.48", "parent_regulation": "GDPR", "language": "fr", "country": "EU", "doc_type": "supplementary"},
    {"filename": "edpb_guidelines_202402_article48_v2_nl_0.pdf", "source": "EDPB Richtsnoeren 2024/02 Art.48", "parent_regulation": "GDPR", "language": "nl", "country": "EU", "doc_type": "supplementary"},
]

# ── URL documents (HTML pages) ────────────────────────────────
URL_DOCUMENTS = [
    {
        "url": "https://www.ejustice.just.fgov.be/cgi/article.pl?language=fr&sum_date=2024-05-17&lg_txt=f&pd_search=2024-05-17&s_editie=1&numac_search=2024202344&caller=sum&2024202344=4&view_numac=2024202344nx2024202344f",
        "source": "Loi belge cybersécurité NIS2",
        "parent_regulation": "NIS2",
        "language": "fr",
        "country": "be",
        "doc_type": "supplementary",
    },
]


# ── Cell 3: Text extraction ───────────────────────────────────

def extract_text_from_pdf(filename: str) -> str:
    reader = PdfReader(filename)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    full_text = "\n\n".join(pages)
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    full_text = re.sub(r' {2,}', ' ', full_text)
    return full_text.strip()


def extract_text_from_url(url: str) -> str:
    from bs4 import BeautifulSoup
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    return text


# ── Cell 4: Article-level chunking ───────────────────────────

ARTICLE_PATTERN = re.compile(
    r'\n\s*(Article\s+\d+\w*|Artikel\s+\d+\w*|Article\s+\d+er)',
    re.IGNORECASE
)
ARTICLE_NUMBER_PATTERN = re.compile(r'(\d+\w*)', re.IGNORECASE)
HEADING_PATTERN = re.compile(r'\n\s*(\d+\.\s+[A-Z]|[IVX]+\.\s+[A-Z])')


def count_tokens(text: str) -> int:
    return len(text) // 4


def split_by_paragraphs(text: str, article_num: str, max_tokens: int) -> list:
    paragraphs = re.split(r'\n\n+', text.strip())
    chunks = []
    current = []
    current_tokens = 0
    part = 1

    for para in paragraphs:
        para_tokens = count_tokens(para)
        if current_tokens + para_tokens > max_tokens and current:
            chunks.append({
                "text": "\n\n".join(current).strip(),
                "article": article_num,
                "article_part": part,
            })
            current = current[-1:] if current else []
            current_tokens = count_tokens(current[0]) if current else 0
            part += 1
        current.append(para)
        current_tokens += para_tokens

    if current:
        chunks.append({
            "text": "\n\n".join(current).strip(),
            "article": article_num,
            "article_part": part,
        })
    return chunks


def chunk_by_articles(text: str) -> list:
    matches = list(ARTICLE_PATTERN.finditer(text))
    if len(matches) < 3:
        return None

    chunks = []

    # Preamble
    preamble = text[:matches[0].start()].strip()
    if preamble and len(preamble) > 100:
        if count_tokens(preamble) > MAX_TOKENS_PER_CHUNK:
            chunks.extend(split_by_paragraphs(preamble, "preamble", MAX_TOKENS_PER_CHUNK))
        else:
            chunks.append({"text": preamble, "article": "preamble", "article_part": 1})

    # Articles
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        num_match = ARTICLE_NUMBER_PATTERN.search(heading)
        article_num = num_match.group(1) if num_match else str(i + 1)

        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        article_text = text[start:end].strip()

        if not article_text or len(article_text) < 50:
            continue

        if count_tokens(article_text) > MAX_TOKENS_PER_CHUNK:
            chunks.extend(split_by_paragraphs(article_text, article_num, MAX_TOKENS_PER_CHUNK))
        else:
            chunks.append({"text": article_text, "article": article_num, "article_part": 1})

    return chunks if chunks else None


def chunk_by_headings(text: str) -> list:
    matches = list(HEADING_PATTERN.finditer(text))
    if len(matches) < 3:
        return None

    chunks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()

        if not section_text or len(section_text) < 50:
            continue

        if count_tokens(section_text) > MAX_TOKENS_PER_CHUNK:
            chunks.extend(split_by_paragraphs(section_text, f"section_{i+1}", MAX_TOKENS_PER_CHUNK))
        else:
            chunks.append({"text": section_text, "article": f"section_{i+1}", "article_part": 1})

    return chunks if chunks else None


def chunk_fixed_size(text: str, size: int = 400, overlap: int = 50) -> list:
    words = text.split()
    chunks = []
    start = 0
    part = 1

    while start < len(words):
        end = min(start + size, len(words))
        chunks.append({"text": " ".join(words[start:end]), "article": "n/a", "article_part": part})
        if end == len(words):
            break
        start += size - overlap
        part += 1

    return chunks


def smart_chunk(text: str, doc_meta: dict) -> list:
    chunks = chunk_by_articles(text)
    method = "article"

    if chunks is None:
        chunks = chunk_by_headings(text)
        method = "heading"

    if chunks is None:
        chunks = chunk_fixed_size(text)
        method = "fixed"

    print(f"  Chunking method: {method} → {len(chunks)} chunks")

    reg = doc_meta.get("parent_regulation", "")
    enf_config = ENFORCEMENT_CONFIG.get(reg, {})
    default_date   = enf_config.get("default_date", "")
    default_status = enf_config.get("default_status", "in_force")
    provisions     = enf_config.get("provisions", {})

    enriched = []
    for chunk in chunks:
        article_num = chunk.get("article", "n/a")
        if article_num in provisions:
            enf_date, enf_status, scope = provisions[article_num]
        else:
            enf_date   = default_date
            enf_status = default_status
            scope      = "all"

        enriched.append({
            "text":             chunk["text"],
            "source":           doc_meta["source"],
            "parent_regulation":doc_meta["parent_regulation"],
            "language":         doc_meta["language"],
            "country":          doc_meta["country"],
            "doc_type":         doc_meta["doc_type"],
            "article":          article_num,
            "article_part":     chunk.get("article_part", 1),
            "enforcement_date": enf_date,
            "status":           enf_status,
            "provision_scope":  scope,
            "chunk_method":     method,
        })

    return enriched


# ── Cell 5: Embeddings ────────────────────────────────────────

MAX_CHARS_PER_CHUNK = 4000  # Mistral embed limit ~8192 tokens ≈ 4000 chars safe

def truncate_texts(texts: list) -> list:
    """Truncate any chunk exceeding the safe character limit."""
    truncated = []
    for t in texts:
        if len(t) > MAX_CHARS_PER_CHUNK:
            print(f"  ⚠️  Truncating chunk from {len(t)} to {MAX_CHARS_PER_CHUNK} chars")
            truncated.append(t[:MAX_CHARS_PER_CHUNK])
        else:
            truncated.append(t)
    return truncated

def get_embeddings(texts: list) -> list:
    texts = truncate_texts(texts)
    all_embeddings = []
    batch_size = 50

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        for attempt in range(3):
            try:
                response = requests.post(
                    "https://api.mistral.ai/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {MISTRAL_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"model": "mistral-embed", "input": batch},
                    timeout=60,
                )
                response.raise_for_status()
                all_embeddings.extend([item["embedding"] for item in response.json()["data"]])
                print(f"  Embedded batch {i//batch_size + 1} ({len(batch)} chunks)")
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  Retry {attempt + 1}: {e}")
                    time.sleep(10)
                else:
                    raise

    return all_embeddings


# ── Cell 6: Qdrant setup ──────────────────────────────────────

def setup_qdrant() -> QdrantClient:
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"✅ Dropped existing collection '{COLLECTION_NAME}'")
    except Exception:
        print(f"ℹ️  No existing collection to drop")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    print(f"✅ Created new collection '{COLLECTION_NAME}'")

    indexes = [
        ("language",           PayloadSchemaType.KEYWORD),
        ("country",            PayloadSchemaType.KEYWORD),
        ("doc_type",           PayloadSchemaType.KEYWORD),
        ("parent_regulation",  PayloadSchemaType.KEYWORD),
        ("article",            PayloadSchemaType.KEYWORD),
        ("status",             PayloadSchemaType.KEYWORD),
        ("provision_scope",    PayloadSchemaType.KEYWORD),
        ("chunk_method",       PayloadSchemaType.KEYWORD),
    ]
    for field_name, schema_type in indexes:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field_name,
            field_schema=schema_type,
        )
        print(f"  Index: {field_name}")

    return client


# ── Cell 7: Ingestion helpers ─────────────────────────────────

def upload_to_qdrant(client: QdrantClient, chunks: list):
    texts = [c["text"] for c in chunks]
    embeddings = get_embeddings(texts)

    points = [
        PointStruct(id=str(uuid.uuid4()), vector=emb, payload=chunk)
        for chunk, emb in zip(chunks, embeddings)
    ]

    batch_size = 100
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i:i + batch_size])

    return len(points)


def ingest_pdf(client: QdrantClient, doc: dict) -> dict:
    filename = doc["filename"]
    print(f"\n{'='*60}")
    print(f"PDF: {filename}")

    if not os.path.exists(filename):
        print(f"  ⚠️  File not found — SKIPPED")
        return {"file": filename, "status": "skipped", "chunks": 0}

    try:
        text = extract_text_from_pdf(filename)
        print(f"  Extracted {len(text):,} characters")
        chunks = smart_chunk(text, doc)
        count = upload_to_qdrant(client, chunks)
        print(f"  ✅ {count} chunks ingested")
        return {"file": filename, "status": "ok", "chunks": count}
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return {"file": filename, "status": "error", "chunks": 0}


def ingest_url(client: QdrantClient, doc: dict) -> dict:
    url = doc["url"]
    print(f"\n{'='*60}")
    print(f"URL: {doc['source']}")
    print(f"  {url[:80]}...")

    try:
        text = extract_text_from_url(url)
        print(f"  Extracted {len(text):,} characters")
        chunks = smart_chunk(text, doc)
        count = upload_to_qdrant(client, chunks)
        print(f"  ✅ {count} chunks ingested")
        return {"file": doc["source"], "status": "ok", "chunks": count}
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return {"file": doc["source"], "status": "error", "chunks": 0}


# ── Cell 8: Main ingestion ────────────────────────────────────

def run_full_ingestion():
    print("COMPLAI Sprint 7 — Full Knowledge Base Re-ingestion")
    print("=" * 60)
    print(f"PDF documents:  {len(PDF_DOCUMENTS)}")
    print(f"URL documents:  {len(URL_DOCUMENTS)}")
    print(f"Total:          {len(PDF_DOCUMENTS) + len(URL_DOCUMENTS)}")

    client = setup_qdrant()

    results = []

    # Ingest PDFs
    print(f"\n{'='*60}")
    print("INGESTING PDF DOCUMENTS")
    for doc in PDF_DOCUMENTS:
        result = ingest_pdf(client, doc)
        results.append(result)

    # Ingest URLs
    print(f"\n{'='*60}")
    print("INGESTING URL DOCUMENTS")
    for doc in URL_DOCUMENTS:
        result = ingest_url(client, doc)
        results.append(result)

    # Summary
    total_chunks = sum(r["chunks"] for r in results)
    ok      = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors  = [r for r in results if r["status"] == "error"]

    print(f"\n{'='*60}")
    print(f"INGESTION COMPLETE")
    print(f"{'='*60}")
    print(f"✅ Success:  {len(ok)} documents")
    print(f"⚠️  Skipped:  {len(skipped)} documents")
    print(f"❌ Errors:   {len(errors)} documents")
    print(f"\nTotal chunks: {total_chunks}")

    if skipped:
        print(f"\nSkipped files (upload to Colab and re-run):")
        for r in skipped:
            print(f"  - {r['file']}")

    if errors:
        print(f"\nFailed:")
        for r in errors:
            print(f"  - {r['file']}")

    info = client.get_collection(COLLECTION_NAME)
    print(f"\nQdrant collection: {info.points_count} points")


run_full_ingestion()

# ── Optional: re-run only specific files after fixing issues ─
# Uncomment and edit the list below to re-ingest specific documents
# without dropping the whole collection.
#
# def rerun_specific(filenames: list):
#     client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
#     docs = [d for d in PDF_DOCUMENTS if d["filename"] in filenames]
#     for doc in docs:
#         ingest_pdf(client, doc)
#
# rerun_specific([
#     "aiact_en.pdf",
#     "aiact_fr.pdf",
#     "aiact_nl.pdf",
#     "CELEX_32019L0882_FR_TXT.pdf",
#     "CELEX_32019L0882_NL_TXT.pdf",
# ])


# ── Cell 9: Verification ──────────────────────────────────────

def verify_ingestion():
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    print("VERIFICATION")
    print("=" * 60)

    info = client.get_collection(COLLECTION_NAME)
    print(f"Total points: {info.points_count}")

    # Count by regulation
    print(f"\nChunks by regulation:")
    for reg in ["GDPR", "NIS2", "EU_AI_ACT", "EPRIVACY", "CONSUMER_RIGHTS", "EAA"]:
        count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=Filter(must=[
                FieldCondition(key="parent_regulation", match=MatchValue(value=reg))
            ])
        ).count
        print(f"  {reg}: {count}")

    # Count by doc_type
    print(f"\nChunks by type:")
    for dt in ["core", "supplementary"]:
        count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=Filter(must=[
                FieldCondition(key="doc_type", match=MatchValue(value=dt))
            ])
        ).count
        print(f"  {dt}: {count}")

    # Count by enforcement status
    print(f"\nChunks by enforcement status:")
    for status in ["in_force", "upcoming"]:
        count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=Filter(must=[
                FieldCondition(key="status", match=MatchValue(value=status))
            ])
        ).count
        print(f"  {status}: {count}")

    # Count by chunking method
    print(f"\nChunks by method:")
    for method in ["article", "heading", "fixed"]:
        count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=Filter(must=[
                FieldCondition(key="chunk_method", match=MatchValue(value=method))
            ])
        ).count
        print(f"  {method}: {count}")

    # Sample 3 chunks
    print(f"\nSample chunks:")
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=3,
        with_payload=True,
        with_vectors=False,
    )
    for r in results:
        p = r.payload
        print(f"\n  [{p.get('source')}] Article {p.get('article')} part {p.get('article_part')}")
        print(f"  Status: {p.get('status')} | Date: {p.get('enforcement_date')} | Method: {p.get('chunk_method')}")
        print(f"  Preview: {p.get('text','')[:120]}...")


verify_ingestion()
