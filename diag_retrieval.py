"""
pages/diag_retrieval.py — TEMPORARY. Delete after answering the question.

Does retrieve() return chunks from the regulation the question is about?

`retrieve()` filters on language, country and doc_type — but NOT on
parent_regulation, so all six regulations compete on semantic similarity alone
and GDPR has by far the most material in the collection.

This answers the S31-before-S28 question in section 7 of the sprint log. If a
NIS2 question comes back mostly GDPR, S31 moves ahead of S28: S28, S29 and S30
all produce documents with LLM inserts, and templates authored against a
retrieval layer that answers from the wrong regulation get reviewed twice.

A page, rather than a script, only because the Qdrant and Mistral credentials
live in this environment.

DELETE THIS FILE, its nav entry in app.py, and its PAGE_CONTEXT entry once the
answer is recorded. A diagnostic left in the navigation becomes a permanent one
nobody removes — `pages_admin/` is already carrying three modules that arrived
that way.
"""

from collections import Counter

import streamlit as st
from qdrant_client.models import Filter, FieldCondition, MatchValue

from rag import COLLECTION_NAME, get_qdrant_client, get_embeddings, get_knowledge_base_summary

st.title("🔬 Retrieval diagnostic")
st.caption(
    "Temporary. Measures whether retrieval answers from the right regulation. "
    "Delete once the S31 sequencing question is settled."
)

# Two phrasings per regulation: one using the regulation's own vocabulary, one
# the way a client would actually type it. The second is the harder case and
# the realistic one — nobody types "Article 23 NIS2".
QUERIES = [
    ("NIS2",      "What are the incident reporting deadlines?"),
    ("NIS2",      "Do I have to tell anyone if we get hacked?"),
    ("NIS2",      "supply chain security measures for essential entities"),
    ("EU_AI_ACT", "What are my obligations as a deployer of an AI system?"),
    ("EU_AI_ACT", "We use a chatbot on our website. Do we have to say so?"),
    ("EU_AI_ACT", "high-risk classification Annex III"),
    ("GDPR",      "What must a record of processing activities contain?"),
    ("GDPR",      "How long can we keep employee data?"),
    ("EPRIVACY",  "Do we need consent for analytics cookies?"),
]


def probe(query: str, doc_type: str, top_k: int = 3):
    """The same filters retrieve() applies, keeping the payload it discards."""
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


if not st.button("Run diagnostic", type="primary"):
    st.info(
        "Runs 18 Qdrant queries and 9 embedding calls. A few seconds and a "
        "small amount of Mistral quota."
    )
    st.stop()

# What is actually in the collection. A regulation with ten times the chunks of
# another wins on volume before relevance is considered.
st.subheader("Collection mix")
with st.spinner("Reading the knowledge base…"):
    totals = Counter()
    for row in get_knowledge_base_summary():
        totals[row.get("parent_regulation") or "(none)"] += row["chunks"]

total = sum(totals.values()) or 1
st.dataframe(
    [
        {"Regulation": reg, "Chunks": n, "Share": f"{100 * n / total:.1f}%"}
        for reg, n in totals.most_common()
    ],
    hide_index=True,
    width="stretch",
)

st.subheader("Retrieval — expected regulation vs what came back")
st.caption(
    "Only the **core** half is scored. Supplementary guidance legitimately "
    "crosses regulations."
)

hits = misses = 0
rows = []

progress = st.progress(0.0)
for i, (expected, query) in enumerate(QUERIES):
    core = probe(query, "core")
    supp = probe(query, "supplementary")
    got = [r for r, _, _ in core]
    on_target = sum(1 for r in got if r == expected)
    verdict = "✅ OK" if on_target >= 2 else ("🟡 WEAK" if on_target == 1 else "🔴 MISS")
    if on_target >= 2:
        hits += 1
    elif on_target == 0:
        misses += 1

    rows.append({
        "": verdict,
        "Expected": expected,
        "Query": query,
        "Core returned": ", ".join(got) or "—",
        "On target": f"{on_target}/{len(core)}",
    })
    progress.progress((i + 1) / len(QUERIES))

    with st.expander(f"{verdict} · {expected} · {query}", expanded=False):
        for reg, src, score in core:
            mark = "→ " if reg != expected else ""
            st.markdown(f"- {mark}**core** `{reg}` · {score} · {src}")
        for reg, src, score in supp:
            st.markdown(f"- supp `{reg}` · {score} · {src}")

progress.empty()
st.dataframe(rows, hide_index=True, width="stretch")

st.subheader(f"{hits} clean · {misses} missed · out of {len(QUERIES)}")

# Three readings, and the third is the one worth catching: it looks like a
# retrieval failure and is a query-construction failure, which is a much
# cheaper fix and would not justify moving a sprint.
plain = [r for r in rows if r["Query"].endswith("?") and r[""] != "✅ OK"]
if misses == 0 and hits >= 7:
    st.success(
        "**S31 stays at 31.** Retrieval answers from the right regulation. "
        "Start S28."
    )
elif len(plain) >= 3 and misses <= 2:
    st.warning(
        "**Look at the query construction before moving the sprint.** The "
        "vocabulary phrasings work and the plain-language ones do not, which "
        "means retrieval is fine and what the app sends it is not. A cheaper "
        "fix than regulation-aware allocation, and it would not justify "
        "reordering."
    )
else:
    st.error(
        "**S31 moves ahead of S28.** Retrieval is answering from the wrong "
        "regulation. S28, S29 and S30 all produce documents with LLM inserts — "
        "templates authored against this get reviewed twice."
    )

st.divider()
st.caption(
    "Record the result in the sprint log, then delete this page, its entry in "
    "`app.py`'s navigation, and its `PAGE_CONTEXT` key."
)
