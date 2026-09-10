"""
draft_inserts.py — S29A. First drafts for the prose RECOSA cannot derive.

AUTHORING TIME, NOT RENDER TIME
-------------------------------
This runs when a client opens the insert for editing, never while a document is
being produced. The output is stored on `clients`, edited by the client, and
then merged like any other field.

That keeps template-first intact (D-01). A lawyer reviewing a template reviews
a document with known text in it, not a shape that will be filled by a model
later. And a regenerated document is identical to the last one unless someone
changed something, which is the property S27's versioning depends on.

Same category as translate.py: LLM under human review, output stored and
inspectable before it reaches anything.

WHY IT RETRIEVES
----------------
A model asked to describe incident detection with no context writes plausible
security-consultancy prose. Given the actual Art. 21 and Art. 23 text it writes
something closer to what the obligation says.

`regulations=["NIS2"]` — the first real use of the D-70 filter, and the reason
it exists. The 8 September diagnostic showed that a NIS2 question phrased in
plain language returns EU AI Act or GDPR chunks, because the AI Act holds 39%
of the collection. Without the filter, a prompt about incident detection would
be grounded in the wrong regulation and read perfectly well.

FAILURE IS NOT AN ERROR
-----------------------
Returns "" on any failure — no key, no network, a model that answers in prose
when asked for prose but at the wrong length. The client then writes their own,
which they were always free to do. Blocking on a draft would make the feature a
dependency rather than a help.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

import requests

API_URL = "https://api.mistral.ai/v1/chat/completions"
MODEL = "mistral-large-latest"

# Longer than translate.py's 12s: this is a paragraph grounded in retrieved
# text, not a phrase, and the client is waiting on a button they pressed
# deliberately rather than on a form save.
TIMEOUT_SECONDS = 45


def _api_key() -> str | None:
    return os.environ.get("MISTRAL_API_KEY") or None


def _context(query: str, language: str) -> str:
    """Regulation text for the prompt. Empty string when retrieval fails.

    A draft written without grounding is worse but still useful; no draft at
    all is neither. So a retrieval failure degrades rather than aborts.
    """
    try:
        from rag import retrieve  # noqa: PLC0415
        chunks = retrieve(
            query, chunks=[], embeddings=None, top_k=6,
            language="en", country="EU",
            regulations=["NIS2"],
        )
        return "\n\n".join(c.text for c in chunks[:6])
    except Exception as e:
        print(f"Insert drafting: retrieval failed, continuing without: {e}")
        return ""


def draft(
    insert_key: str,
    client: Mapping[str, Any],
    language: str = "en",
    user_id: str | None = None,
    client_id: str | None = None,
) -> str:
    """A first draft for one insert. Empty string on any failure."""
    from template_nis2 import INSERTS  # noqa: PLC0415

    spec = INSERTS.get(insert_key)
    if not spec:
        return ""
    key = _api_key()
    if not key:
        return ""

    # What the model is told about the client. Deliberately thin: sector, size
    # signal, and the systems they actually use. Feeding it the whole inventory
    # produces a draft that recites the inventory back, which the client can
    # already see and did not ask for.
    facts = [f"Organisation: {client.get('company_name') or 'the organisation'}"]
    if client.get("nis2_sector"):
        facts.append(f"Sector: {client['nis2_sector']}")
    if client.get("nis2_entity_class"):
        facts.append(f"NIS2 classification: {client['nis2_entity_class']}")

    context = _context(spec["query"], language)

    _LANG = {"en": "English", "fr": "French", "nl": "Dutch", "de": "German"}
    target = _LANG.get(language, "English")

    system = (
        f"You draft short, factual paragraphs in {target} for a small "
        "company's internal security documentation. Write in the first person "
        "plural — 'we do X' — because the client will publish this as their "
        "own statement.\n\n"
        f"Write in {target} only. The retrieved regulation text below may be "
        "in another language; use it for accuracy, not for wording.\n\n"
        "Rules:\n"
        "- Say what the organisation DOES. Never give advice, never write "
        "'should' or 'must', never explain the regulation.\n"
        "- Plain language. No security-consultancy register, no 'robust', no "
        "'leverage', no 'best-in-class'.\n"
        "- Claim nothing specific you were not told. A draft that invents a "
        "24/7 security operations centre for a five-person company is worse "
        "than a blank field, because the client may not notice and it becomes "
        "a false statement in their own document.\n"
        "- Where something is likely not in place, say so plainly. 'We do not "
        "currently test this' is a usable starting point; an invented test "
        "programme is not.\n"
        "- Return the paragraph only. No preamble, no heading, no quotes."
    )

    user = (
        f"{spec['prompt']}\n\n"
        f"About the organisation:\n" + "\n".join(facts)
        + (f"\n\nRelevant NIS2 text, for accuracy — do not quote or cite it:\n"
           f"{context[:4000]}" if context else "")
    )

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={
                "model": MODEL,
                # Low but not zero. These are drafts a human edits, and a
                # little variation is preferable to the same four sentences
                # appearing in every client's documentation.
                "temperature": 0.3,
                "max_tokens": 400,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return ""
        payload = resp.json()
        text = (payload.get("choices", [{}])[0]
                .get("message", {}).get("content", "") or "").strip()

        try:
            from database import log_token_usage  # noqa: PLC0415
            usage = payload.get("usage", {})
            log_token_usage(
                user_id=user_id, feature="draft_insert", client_id=client_id,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
        except Exception:
            pass

        # A model that returns a wall of text has misunderstood the brief, and
        # a wall of text in a template field is worse than nothing: it looks
        # authoritative and nobody reads it before adopting the document.
        if len(text) > 1500:
            return ""
        return text
    except Exception as e:
        print(f"Insert drafting failed: {e}")
        return ""
