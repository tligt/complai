"""
mistral_text.py — D-174. One place to read the reply text out of a Mistral
chat-completions response.

Found 13 Nov: `monitor.py` on production was silently dropping every CCB
Advisories item (10 of 10, every run) with "'list' object has no attribute
'strip'" — caught by the per-item try/except, so it never showed as an
error, just as "0 relevant items after analysis". `response["choices"][0]
["message"]["content"]` is usually a plain string, but mistral-large-latest
sometimes returns a list of content blocks instead
([{"type": "text", "text": "..."}], or plain strings in a list) — which kind
depends on the input, not the caller, so every one of the ten call sites
that assumed a string ((`app_pages/chat.py`, `database.py`,
`document_generator.py`, `draft_inserts.py`, `gap_assessment.py`,
`monitor.py`, `monitor_marketing.py`, `pages_admin/monitoring.py`, `rag.py`,
`translate.py`) was exposed to the same crash, not just this one.
"""

from __future__ import annotations

from typing import Any


def message_text(data: dict[str, Any]) -> str:
    """The assistant's reply, stripped, whatever shape `content` came back
    in. Raises the same way the old `data["choices"][0]["message"]["content"]`
    did if the response doesn't have a message at all — only the content's
    own shape is made robust here."""
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
        return "".join(parts).strip()
    return str(content or "").strip()
