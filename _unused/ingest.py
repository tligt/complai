"""
One-time ingestion script.
Run locally or in a Python shell to load regulatory documents into Qdrant.
Usage: python ingest.py
"""

import os
import re
import io
import uuid
import requests
import numpy as np
from pypdf import PdfReader
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

load_dotenv()

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]
MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
COLLECTION_NAME = "regulations"
VECTOR_SIZE = 1024  # mistral-embed output dimension

DOCUMENTS = [
    # NIS2
    {
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022L2555",
        "regulation": "NIS2",
        "language": "en",
    },
    {
        "url": "https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:32022L2555",
        "regulation": "NIS2",
        "language": "fr",
    },
    {
        "url": "https://eur-lex.europa.eu/legal-content/NL/TXT/PDF/?uri=CELEX:32022L2555",
        "regulation": "NIS2",
        "language": "nl",
    },
    # GDPR
    {
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32016R0679",
        "regulation": "GDPR",
        "language": "en",
    },
    {
        "url": "https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:32016R0679",
        "regulation": "GDPR",
        "language": "fr",
    },
    {
        "url": "https://eur-lex.europa.eu/legal-content/NL/TXT/PDF/?uri=CELEX:32016R0679",
        "regulation": "GDPR",
        "language": "nl",
    },
    # EU AI Act
    {
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689",
        "regulation": "EU_AI_ACT",
        "language": "en",
    },
    {
        "url": "https://eur-lex.europa.eu/legal-content/FR/TXT/PDF/?uri=CELEX:32024R1689",
        "regulation": "EU_AI_ACT",
        "language": "fr",
    },
    {
        "url": "https://eur-lex.europa.eu/legal-content/NL/TXT/PDF/?uri=CELEX:32024R1689",
        "regulation": "EU_AI_ACT",
        "language": "nl",
    },
]


def fetch_pdf(url: str) -> str:
    print(f"  Fetching {url}...")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    reader = PdfReader(io.BytesIO(response.content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


def get_embeddings(texts: list[str]) -> list[list[float]]:
    response = requests.post(
        "https://api.mistral.ai/v1/embeddings",
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": "mistral-embed", "input": texts},
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def main():
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Create collection if it doesn't exist
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        print(f"Creating collection '{COLLECTION_NAME}'...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    else:
        print(f"Collection '{COLLECTION_NAME}' already exists — clearing it...")
        client.delete_collection(COLLECTION_NAME)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    all_points = []

    for doc in DOCUMENTS:
        print(f"\nProcessing {doc['regulation']} ({doc['language'].upper()})...")
        try:
            text = fetch_pdf(doc["url"])
            chunks = chunk_text(text)
            print(f"  {len(chunks)} chunks created")

            batch_size = 50
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                embeddings = get_embeddings(batch)
                for chunk_text_val, embedding in zip(batch, embeddings):
                    all_points.append(
                        PointStruct(
                            id=str(uuid.uuid4()),
                            vector=embedding,
                            payload={
                                "text": chunk_text_val,
                                "regulation": doc["regulation"],
                                "language": doc["language"],
                                "source": f"{doc['regulation']} ({doc['language'].upper()})",
                            },
                        )
                    )
                print(f"  Embedded batch {i // batch_size + 1}/{(len(chunks) - 1) // batch_size + 1}")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    print(f"\nUploading {len(all_points)} points to Qdrant...")
    batch_size = 100
    for i in range(0, len(all_points), batch_size):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=all_points[i:i + batch_size],
        )
        print(f"  Uploaded {min(i + batch_size, len(all_points))}/{len(all_points)}")

    print("\nIngestion complete.")


if __name__ == "__main__":
    main()
