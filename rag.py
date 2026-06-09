import os
import re
import uuid
import requests
import numpy as np
from dataclasses import dataclass
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointStruct

load_dotenv()

COLLECTION_NAME = "regulations"


@dataclass
class Chunk:
    text: str
    source: str


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )


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
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not found in environment")
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


def build_index(chunks: list[Chunk]) -> np.ndarray:
    """Build in-memory index for company documents (session only)."""
    texts = [c.text for c in chunks]
    all_embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        all_embeddings.extend(get_embeddings(batch))
    return np.array(all_embeddings)


def ingest_to_qdrant(text: str, source: str, language: str, doc_type: str = "supplementary") -> int:
    """Ingest a document permanently into Qdrant. Returns number of chunks ingested."""
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
                    "text": chunk_text_val,
                    "source": source,
                    "language": language,
                    "doc_type": doc_type,
                }
            ))

    batch_size_upload = 100
    for i in range(0, len(points), batch_size_upload):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points[i:i + batch_size_upload],
        )

    return len(points)


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
            payload = point.payload
            source = payload.get("source", "Unknown")
            language = payload.get("language", "?")
            doc_type = payload.get("doc_type", "core")
            key = f"{source}_{language}"
            
            if key not in sources:
                sources[key] = {
                    "source": source,
                    "language": language,
                    "doc_type": doc_type,
                    "chunks": 0,
                }
            sources[key]["chunks"] += 1
        
        if offset is None:
            break
    
    return sorted(sources.values(), key=lambda x: (x["doc_type"], x["source"]))


def retrieve_from_qdrant(
    query: str,
    top_k: int = 6,
    language: str = "en",
    doc_type: str | None = None,
) -> list[Chunk]:
    """Retrieve from persistent regulatory knowledge base."""
    client = get_qdrant_client()
    query_embedding = get_embeddings([query])[0]

    must_conditions = [FieldCondition(key="language", match=MatchValue(value=language))]
    if doc_type:
        must_conditions.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k,
        query_filter=Filter(must=must_conditions),
    ).points

    return [
        Chunk(text=r.payload["text"], source=r.payload["source"])
        for r in results
    ]


def retrieve_from_memory(
    query: str,
    chunks: list[Chunk],
    embeddings: np.ndarray,
    top_k: int = 4,
) -> list[Chunk]:
    """Retrieve from in-memory company document index."""
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
) -> list[Chunk]:
    """
    Combined retrieval:
    - Retrieves from core regulations (always)
    - Retrieves from supplementary documents (always)
    - Retrieves from in-memory company documents if loaded
    """
    core_chunks = retrieve_from_qdrant(query, top_k=top_k // 2 or 3, language=language, doc_type="core")
    supplementary_chunks = retrieve_from_qdrant(query, top_k=top_k // 2 or 3, language=language, doc_type="supplementary")

    company_chunks = []
    if embeddings is not None and len(chunks) > 0:
        company_chunks = retrieve_from_memory(query, chunks, embeddings, top_k=4)

    return core_chunks + supplementary_chunks + company_chunks
