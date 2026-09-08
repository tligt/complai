import os
import re
import io
import uuid
import time
import requests
import numpy as np
from pypdf import PdfReader
from dataclasses import dataclass
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue, PointStruct,
    Distance, VectorParams, PayloadSchemaType
)

load_dotenv()

COLLECTION_NAME = "regulations"
VECTOR_SIZE = 1024

# All regulations now ingested via Colab rebuild script
# This list is kept for reference only — not used for ingestion
KNOWN_REGULATIONS = ["GDPR", "NIS2", "EU_AI_ACT", "EPRIVACY", "CONSUMER_RIGHTS", "EAA"]


@dataclass
class Chunk:
    text: str
    source: str


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Fixed-size chunking for admin-uploaded documents."""
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
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not found in environment")
    for attempt in range(3):
        try:
            response = requests.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": "mistral-embed", "input": texts},
            )
            response.raise_for_status()
            return [item["embedding"] for item in response.json()["data"]]
        except Exception as e:
            if attempt < 2:
                time.sleep(10)
            else:
                raise


def fetch_html_text(url: str) -> str:
    """Fetch a web page and extract plain text from HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("beautifulsoup4 not installed")

    response = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    return text


def build_index(chunks: list[Chunk]) -> np.ndarray:
    """Build in-memory index for company documents (session only)."""
    texts = [c.text for c in chunks]
    all_embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        all_embeddings.extend(get_embeddings(batch))
    return np.array(all_embeddings)


def ingest_to_qdrant(
    text: str,
    source: str,
    language: str,
    country: str = "EU",
    doc_type: str = "supplementary",
    parent_regulation: str = "general",
    enforcement_date: str = "",
    status: str = "in_force",
) -> int:
    """Ingest a document via admin interface into Qdrant. Returns number of chunks ingested."""
    client = get_qdrant_client()
    chunks = chunk_text(text)
    points = []

    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        embeddings = get_embeddings(batch)
        for chunk_text_val, embedding in zip(batch, embeddings):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "text":             chunk_text_val,
                    "source":           source,
                    "language":         language,
                    "country":          country,
                    "doc_type":         doc_type,
                    "parent_regulation":parent_regulation,
                    "article":          "n/a",
                    "article_part":     1,
                    "enforcement_date": enforcement_date,
                    "status":           status,
                    "provision_scope":  "all",
                    "chunk_method":     "fixed",
                }
            ))

    for i in range(0, len(points), 100):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i:i + 100])

    return len(points)


def update_source_metadata(
    old_source: str,
    new_source: str | None = None,
    new_country: str | None = None,
    new_language: str | None = None,
    new_doc_type: str | None = None,
    new_parent_regulation: str | None = None,
) -> int:
    """Update metadata for all chunks matching a source name."""
    client = get_qdrant_client()

    payload = {}
    if new_source:
        payload["source"] = new_source
    if new_country:
        payload["country"] = new_country
    if new_language:
        payload["language"] = new_language
    if new_doc_type:
        payload["doc_type"] = new_doc_type
    if new_parent_regulation:
        payload["parent_regulation"] = new_parent_regulation

    if not payload:
        return 0

    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="source", match=MatchValue(value=old_source))]),
        limit=10000,
        with_vectors=False,
    )
    count = len(results)

    if count > 0:
        client.set_payload(
            collection_name=COLLECTION_NAME,
            payload=payload,
            points=Filter(must=[FieldCondition(key="source", match=MatchValue(value=old_source))]),
        )

    return count


def delete_source(source: str) -> int:
    """Delete all chunks for a given source."""
    client = get_qdrant_client()

    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="source", match=MatchValue(value=source))]),
        limit=10000,
        with_vectors=False,
    )
    count = len(results)

    if count > 0:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(must=[FieldCondition(key="source", match=MatchValue(value=source))]),
        )

    return count


def get_knowledge_base_summary() -> list[dict]:
    """Query Qdrant for distinct sources and their metadata."""
    client = get_qdrant_client()
    sources = {}
    offset = None

    while True:
        results, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            p = point.payload
            key = f"{p.get('source')}_{p.get('language')}_{p.get('country')}"
            if key not in sources:
                sources[key] = {
                    "source":           p.get("source", "Unknown"),
                    "language":         p.get("language", "?"),
                    "country":          p.get("country", "EU"),
                    "doc_type":         p.get("doc_type", "core"),
                    "parent_regulation":p.get("parent_regulation", ""),
                    "detected_at":      p.get("detected_at", ""),
                    "chunks":           0,
                }
            sources[key]["chunks"] += 1

        if offset is None:
            break

    return sorted(sources.values(), key=lambda x: (x["doc_type"], x["country"], x["source"]))


def ensure_payload_indexes() -> dict[str, str]:
    """Create the payload indexes retrieval filters on. Idempotent.

    Qdrant will filter on an unindexed payload field, but by scanning rather
    than by index — fine on a few thousand chunks and not fine later. The
    collection was built by the Colab rebuild script, which may or may not have
    created these.

    Run once from a shell or an admin page. Safe to re-run: an existing index
    raises, and that is reported rather than treated as a failure.
    """
    client = get_qdrant_client()
    fields = {
        "parent_regulation": PayloadSchemaType.KEYWORD,
        "doc_type":          PayloadSchemaType.KEYWORD,
        "language":          PayloadSchemaType.KEYWORD,
        "country":           PayloadSchemaType.KEYWORD,
        "status":            PayloadSchemaType.KEYWORD,
    }
    out = {}
    for field, schema in fields.items():
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )
            out[field] = "created"
        except Exception as e:
            out[field] = f"already present or failed: {type(e).__name__}"
    return out


def retrieve_from_qdrant(
    query: str,
    top_k: int = 3,
    language: str = "en",
    country: str = "EU",
    doc_type: str | None = None,
    regulations: list[str] | None = None,
) -> list[Chunk]:
    """Retrieve chunks, optionally restricted to named regulations.

    `regulations` is a list of `parent_regulation` values — "NIS2", "GDPR",
    "EU_AI_ACT", "EPRIVACY", "CONSUMER_RIGHTS", "EAA". None means every
    regulation competes on semantic similarity, which is the right behaviour
    for chat and the wrong one for document generation.

    WHY THIS EXISTS (measured 8 Sept 2026)
    --------------------------------------
    Nine diagnostic queries, seven clean. Both failures were NIS2 questions
    phrased the way a client would ask them:

      "What are the incident reporting deadlines?"  -> 3/3 EU AI Act chunks
      "Do I have to tell anyone if we get hacked?"  -> 3/3 GDPR chunks

    Neither is a ranking bug. The AI Act has serious-incident reporting under
    Art. 73 and holds 38.9% of the collection; Art. 33 GDPR breach notification
    is a defensible answer to the second question as asked. The third NIS2
    query, using NIS2's own vocabulary ("essential entities"), returned 3/3.
    NIS2 wins when the language is distinctive and loses when the concept is
    shared across three regulations.

    In CHAT that ambiguity is real and should be preserved — a client asking
    about being hacked may well need the GDPR answer.

    In DOCUMENT GENERATION there is no ambiguity to resolve. When S29 generates
    a NIS2 breach procedure, the regulation is known before the query is sent.
    Retrieval was never told, so it guessed, and on the shared concepts it
    guessed wrong. That is what this parameter fixes.
    """
    client = get_qdrant_client()
    query_embedding = get_embeddings([query])[0]

    country_values = ["EU"]
    if country != "EU":
        country_values.append(country)

    must_conditions = [
        FieldCondition(key="language", match=MatchValue(value=language)),
        FieldCondition(key="country", match={"any": country_values}),
    ]
    if doc_type:
        must_conditions.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))
    if regulations:
        # Filtered, not re-ranked. A document generated for NIS2 must not be
        # able to cite the AI Act at all, however well the chunk scores.
        must_conditions.append(
            FieldCondition(key="parent_regulation", match={"any": list(regulations)})
        )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k,
        query_filter=Filter(must=must_conditions),
    ).points

    return [Chunk(text=r.payload["text"], source=r.payload["source"]) for r in results]


def retrieve_from_memory(
    query: str,
    chunks: list[Chunk],
    embeddings: np.ndarray,
    top_k: int = 4,
) -> list[Chunk]:
    query_embedding = np.array(get_embeddings([query])[0])
    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
    scores = np.dot(embeddings, query_embedding) / (norms + 1e-10)
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [chunks[i] for i in top_indices]


def retrieve(
    query: str,
    chunks: list[Chunk],
    embeddings: np.ndarray | None,
    top_k: int = 6,
    language: str = "en",
    country: str = "EU",
    regulations: list[str] | None = None,
) -> list[Chunk]:
    """
    Retrieve relevant chunks from Qdrant + in-memory company documents.
    Splits top_k evenly between core regulations and supplementary guidance.

    `regulations` restricts both halves to the named `parent_regulation`
    values. Default None keeps the existing behaviour — all six compete on
    semantic relevance — which is correct for chat and wrong for document
    generation. See retrieve_from_qdrant for the measurement behind this.

    Supplementary guidance is filtered too. EDPB and ENISA material is tagged
    with the regulation it interprets, so a NIS2 document pulling EDPB guidance
    on GDPR is the same error one layer down.
    """
    half = max(top_k // 2, 3)
    core_chunks = retrieve_from_qdrant(
        query, top_k=half, language=language, country=country, doc_type="core",
        regulations=regulations,
    )
    supplementary_chunks = retrieve_from_qdrant(
        query, top_k=half, language=language, country=country,
        doc_type="supplementary", regulations=regulations,
    )

    company_chunks = []
    if embeddings is not None and len(chunks) > 0:
        company_chunks = retrieve_from_memory(query, chunks, embeddings, top_k=4)

    return core_chunks + supplementary_chunks + company_chunks
