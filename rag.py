import os
import re
import requests
import numpy as np
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Chunk:
    text: str
    source: str


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
        json={
            "model": "mistral-embed",
            "input": texts,
        }
    )
    response.raise_for_status()
    data = response.json()
    return [item["embedding"] for item in data["data"]]


def build_index(chunks: list[Chunk]) -> np.ndarray:
    texts = [c.text for c in chunks]
    all_embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = get_embeddings(batch)
        all_embeddings.extend(batch_embeddings)
    return np.array(all_embeddings)


def retrieve(
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
