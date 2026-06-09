# ============================================================
# COMPLAI — Knowledge Base Rebuild Script
# Run this in Google Colab to rebuild the full regulatory KB
# ============================================================
# Step 1: Run this cell to install dependencies
# !pip install qdrant-client pypdf requests

# Step 2: Set your API keys (replace values)
import os
os.environ["MISTRAL_API_KEY"] = "MYDyzfOV42m77wESlznavmH90aFbrJKq"
os.environ["QDRANT_URL"]      = "https://8e1a861e-e4f6-4b7b-802d-1b691ab4a9dc.eu-central-1-0.aws.cloud.qdrant.io"
os.environ["QDRANT_API_KEY"]  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6NWU5N2ZkZjAtYWEzMi00YTZmLWFmYWItODljMmViYjVjYjIxIn0.WSUvimgjed5vMOHJ3ueE6fg_Qu1ZJYar05YG8Jp8YB0"

# ============================================================
# Step 3: Run the full rebuild
# ============================================================
import io
import re
import uuid
import time
import requests
import numpy as np
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, PayloadSchemaType
)

COLLECTION_NAME = "regulations"
VECTOR_SIZE     = 1024
HEADERS         = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CORE_DOCUMENTS = [
    # NIS2
    {"url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022L2555", "source": "NIS2 Directive",      "parent_regulation": "NIS2",       "language": "en", "country": "EU", "doc_type": "core"},
    {"url": "https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:32022L2555", "source": "Directive NIS2",      "parent_regulation": "NIS2",       "language": "fr", "country": "EU", "doc_type": "core"},
    {"url": "https://eur-lex.europa.eu/legal-content/NL/TXT/PDF/?uri=CELEX:32022L2555", "source": "NIS2 Richtlijn",      "parent_regulation": "NIS2",       "language": "nl", "country": "EU", "doc_type": "core"},
    # GDPR
    {"url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32016R0679", "source": "GDPR",                "parent_regulation": "GDPR",       "language": "en", "country": "EU", "doc_type": "core"},
    {"url": "https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:32016R0679", "source": "RGPD",                "parent_regulation": "GDPR",       "language": "fr", "country": "EU", "doc_type": "core"},
    {"url": "https://eur-lex.europa.eu/legal-content/NL/TXT/PDF/?uri=CELEX:32016R0679", "source": "AVG",                 "parent_regulation": "GDPR",       "language": "nl", "country": "EU", "doc_type": "core"},
    # EU AI Act
    {"url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689", "source": "EU AI Act",           "parent_regulation": "EU_AI_ACT",  "language": "en", "country": "EU", "doc_type": "core"},
    {"url": "https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:32024R1689", "source": "Acte IA européen",    "parent_regulation": "EU_AI_ACT",  "language": "fr", "country": "EU", "doc_type": "core"},
    {"url": "https://eur-lex.europa.eu/legal-content/NL/TXT/PDF/?uri=CELEX:32024R1689", "source": "EU AI Verordening",   "parent_regulation": "EU_AI_ACT",  "language": "nl", "country": "EU", "doc_type": "core"},
]


def chunk_text(text, chunk_size=500, overlap=50):
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


def get_embeddings(texts):
    for attempt in range(3):
        try:
            r = requests.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={"Authorization": f"Bearer {os.environ['MISTRAL_API_KEY']}", "Content-Type": "application/json"},
                json={"model": "mistral-embed", "input": texts},
            )
            r.raise_for_status()
            return [item["embedding"] for item in r.json()["data"]]
        except Exception as e:
            if attempt < 2:
                print(f"  Rate limit, retrying in 10s...")
                time.sleep(10)
            else:
                raise


# ── Setup Qdrant ──────────────────────────────────────────────
client = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ["QDRANT_API_KEY"])

existing = [c.name for c in client.get_collections().collections]
if COLLECTION_NAME in existing:
    print(f"Deleting existing collection '{COLLECTION_NAME}'...")
    client.delete_collection(COLLECTION_NAME)

print(f"Creating collection '{COLLECTION_NAME}'...")
client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
)

for field in ["language", "country", "doc_type", "parent_regulation"]:
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name=field,
        field_schema=PayloadSchemaType.KEYWORD,
    )
print("Payload indexes created.\n")

# ── Ingest documents ──────────────────────────────────────────
all_points = []

for doc in CORE_DOCUMENTS:
    print(f"Processing {doc['source']} ({doc['language'].upper()})...")
    try:
        r = requests.get(doc["url"], timeout=60, headers=HEADERS)
        r.raise_for_status()
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n\n".join([p.extract_text() or "" for p in reader.pages])
        chunks = chunk_text(text)
        print(f"  {len(chunks)} chunks")

        for i in range(0, len(chunks), 50):
            batch = chunks[i:i+50]
            time.sleep(2)
            embeddings = get_embeddings(batch)
            for chunk_val, emb in zip(batch, embeddings):
                all_points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "text": chunk_val,
                        "source": doc["source"],
                        "language": doc["language"],
                        "country": doc["country"],
                        "doc_type": doc["doc_type"],
                        "parent_regulation": doc["parent_regulation"],
                    }
                ))
            print(f"  Batch {i//50+1}/{(len(chunks)-1)//50+1} done")

    except Exception as e:
        print(f"  ERROR: {e}")
        continue

# ── Upload to Qdrant ──────────────────────────────────────────
print(f"\nUploading {len(all_points)} points to Qdrant...")
for i in range(0, len(all_points), 100):
    client.upsert(collection_name=COLLECTION_NAME, points=all_points[i:i+100])
    print(f"  Uploaded {min(i+100, len(all_points))}/{len(all_points)}")

print("\n✅ Rebuild complete.")
