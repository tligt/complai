"""
diag_retrieval.py — one-off. Does retrieve() return chunks from the regulation
the question is about?

Run from the repo root:  python diag_retrieval.py

Answers the S31-before-S28 question in section 7 of the sprint log. retrieve()
filters on language, country and doc_type — but NOT on parent_regulation, so
all six regulations compete on semantic similarity alone and GDPR has the most
material in the collection.

If a NIS2 question comes back mostly GDPR, S31 moves ahead of S28: S28, S29 and
S30 all produce documents with LLM inserts, and templates authored against a
retrieval layer that answers from the wrong regulation get reviewed twice.

Delete this file afterwards. It is a measurement, not a feature.
"""

import os
from collections import Counter

from qdrant_client.models import Filter, FieldCondition, MatchValue

from rag import COLLECTION_NAME, get_qdrant_client, get_embeddings


# Two per regulation: one using the regulation's own vocabulary, one phrased
# the way a client would. The second is the harder case and the realistic one —
# nobody types "Article 23 NIS2".
QUERIES = [
    ("NIS2",       "What are the incident reporting deadlines?"),
    ("NIS2",       "Do I have to tell anyone if we get hacked?"),
    ("NIS2",       "supply chain security measures for essential entities"),
    ("EU_AI_ACT",  "What are my obligations as a deployer of an AI system?"),
    ("EU_AI_ACT",  "We use a chatbot on our website. Do we have to say so?"),
    ("EU_AI_ACT",  "high-risk classification Annex III"),
    ("GDPR",       "What must a record of processing activities contain?"),
    ("GDPR",       "How long can we keep employee data?"),
    ("EPRIVACY",   "Do we need consent for analytics cookies?"),
]


def probe(query: str, doc_type: str, top_k: int = 3):
    """Same filters retrieve() uses, but keeping the payload it discards."""
    client = get_qdrant_client()
    vec = get_embeddings([query])[0]
    res = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vec,
        limit=top_k,
        query_filter=Filter(must=[
            FieldCondition(key="language", match=MatchValue(value="en")),
            FieldCondition(key="country", match={"any": ["EU"]}),
            FieldCondition(key="doc_type", match=MatchValue(value=doc_type)),
        ]),
    ).points
    return [
        (p.payload.get("parent_regulation", "?"),
         p.payload.get("source", "?"),
         round(p.score, 3))
        for p in res
    ]


def main():
    if not os.environ.get("QDRANT_URL"):
        raise SystemExit("QDRANT_URL not set — run where the app's env is loaded.")

    # What is actually in the collection. A regulation with ten times the
    # chunks of another wins on volume before relevance is considered.
    print("=" * 72)
    print("COLLECTION MIX")
    print("=" * 72)
    from rag import get_knowledge_base_summary
    totals = Counter()
    for row in get_knowledge_base_summary():
        totals[row.get("parent_regulation") or "(none)"] += row["chunks"]
    total = sum(totals.values()) or 1
    for reg, n in totals.most_common():
        print(f"  {reg:18} {n:6}  {100 * n / total:5.1f}%")

    print()
    print("=" * 72)
    print("RETRIEVAL — expected regulation vs what came back")
    print("=" * 72)

    hits = misses = 0
    for expected, query in QUERIES:
        core = probe(query, "core")
        supp = probe(query, "supplementary")
        got = [r for r, _, _ in core]
        on_target = sum(1 for r in got if r == expected)
        # The core half is what matters: supplementary guidance legitimately
        # crosses regulations.
        verdict = "OK " if on_target >= 2 else ("WEAK" if on_target == 1 else "MISS")
        if verdict == "OK ":
            hits += 1
        elif verdict == "MISS":
            misses += 1

        print(f"\n[{verdict}] {expected:10} {query}")
        for reg, src, score in core:
            mark = "  " if reg == expected else "->"
            print(f"   {mark} core  {reg:12} {score}  {src[:44]}")
        for reg, src, score in supp:
            print(f"      supp  {reg:12} {score}  {src[:44]}")

    print()
    print("=" * 72)
    print(f"{hits} clean, {misses} missed, out of {len(QUERIES)}")
    print()
    print("READ IT LIKE THIS:")
    print("  Mostly OK          -> S31 stays at 31. Start S28.")
    print("  Several WEAK/MISS  -> S31 moves ahead of S28. Templates authored")
    print("                        against this get reviewed twice.")
    print("  MISS on the plain-language phrasings only -> the retrieval works")
    print("                        and the queries the app sends do not; that")
    print("                        is a different fix and a cheaper one.")


if __name__ == "__main__":
    main()
