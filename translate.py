"""
translate.py — S26C. Second-language drafts for client-authored inventory text.

WHAT THIS IS AND IS NOT
-----------------------
This is AUTHORING-TIME translation under human review, not runtime generation.
The client writes an activity purpose in one language; this proposes the other
languages their documents are produced in; the client confirms or edits them;
only then is the text marked reviewed. Template-first holds — nothing here runs
while a document is being rendered, and every string it produces is stored,
inspectable and editable before it reaches a register or a contract.

The output is marked `machine_unreviewed` in translation_status until a human
saves it. D-53: a translation nobody looked at, sitting in a signed contract,
is exactly what template-first exists to prevent.

FAILURE IS NOT AN ERROR
-----------------------
Every entry point returns rather than raises, and returns {} when anything at
all goes wrong — no key, no network, a timeout, a malformed reply, a model that
answers in prose instead of JSON.

That is deliberate. The client's own text is the thing that matters; a missing
translation is a gap, and gaps belong in the register of outstanding work, not
in an exception that loses the client's typing. Blocking a save on an LLM call
would mean the inventory form stops working whenever Mistral is slow.

The cost of that choice: saves can quietly produce rows with untranslated
fields. Whatever calls this is responsible for making that visible.

WHY NOT A BATCH JOB
-------------------
Because the review has to happen, and a client is far more likely to check a
translation of the sentence they just wrote than one surfaced days later
without context.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

import requests


API_URL = "https://api.mistral.ai/v1/chat/completions"

# Deliberately smaller than chat.py's mistral-large-latest. This runs inside a
# form submit with the client watching a spinner, and short-form translation
# between two European languages is not where a larger model earns its latency.
MODEL = "mistral-small-latest"

# Short on purpose. This runs inside a form submit, with the client watching a
# spinner, and a slow save is worse than a missing translation they can add
# later. Two fields of a sentence or two each is a small request.
TIMEOUT_SECONDS = 12

# Fields are named so the model has some idea what register to write in. A
# retention basis and an activity name want different registers, and unlabelled
# strings get translated as though they were prose.
_FIELD_HINTS = {
    "name": "a short label naming a business activity, as a heading",
    "purpose": "why an organisation processes personal data, one or two sentences",
}

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "nl": "Dutch",
    "de": "German",
}


def _api_key() -> str | None:
    # os.environ, matching chat.py. st.secrets would work on Streamlit Cloud
    # and quietly not elsewhere, and two ways of reading the same credential is
    # the kind of divergence that only shows up in the environment nobody
    # tested.
    return os.environ.get("MISTRAL_API_KEY") or None


def _extract_json(text: str) -> dict[str, Any] | None:
    """Parse the model's reply, tolerating fences and a sentence either side.

    A model told to return only JSON usually does. Usually is not always, and
    the difference between a fenced block and a bare one must not decide
    whether the client's translation appears.
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        brace = re.search(r"\{.*\}", candidate, re.S)
        if not brace:
            return None
        try:
            parsed = json.loads(brace.group(0))
        except (json.JSONDecodeError, TypeError):
            return None
    return parsed if isinstance(parsed, dict) else None


def translate_fields(
    texts: Mapping[str, str],
    source_lang: str,
    target_langs: list[str],
    user_id: str | None = None,
    client_id: str | None = None,
) -> dict[str, dict[str, str]]:
    """Draft `texts` into each of `target_langs`.

    Returns {target_lang: {field: text}}, containing only what actually came
    back. Absent means untranslated, which the caller surfaces as outstanding
    work — it never means "leave the field blank in the document", because
    _i18n() falls back to another language rather than rendering nothing.

    Never raises.
    """
    texts = {k: v.strip() for k, v in (texts or {}).items() if v and v.strip()}
    targets = [
        l for l in (target_langs or [])
        if l != source_lang and l in LANGUAGE_NAMES
    ]
    if not texts or not targets:
        return {}

    key = _api_key()
    if not key:
        return {}

    src = LANGUAGE_NAMES.get(source_lang, source_lang)
    described = "\n".join(
        f"- {field}: {_FIELD_HINTS.get(field, 'a short piece of business text')}\n"
        f"  {src} text: {value}"
        for field, value in texts.items()
    )
    wanted = ", ".join(f"{LANGUAGE_NAMES[l]} ({l})" for l in targets)

    system = (
        "You translate short business text for a GDPR compliance record. "
        "Use the standard data protection vocabulary of the target language — "
        "the wording a data protection officer in that country would use, not "
        "a literal rendering of the English. Keep the register plain and the "
        "length close to the original. Do not explain, expand, soften or add "
        "anything the source does not say: this text is filed with a "
        "supervisory authority, and an embellished translation is a different "
        "statement from the one the client made.\n\n"
        "Return ONLY a JSON object, no prose and no code fence, shaped:\n"
        '{"<language code>": {"<field name>": "<translation>"}}'
    )
    user = f"Translate into {wanted}.\n\nFields:\n{described}"

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                # Deterministic. Two clients writing the same purpose should
                # get the same French, and a translation that varies between
                # saves is one nobody can review with confidence.
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return {}
        payload = resp.json()
        content = (
            payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        # Billable, so it is counted — the credits work in S41 has to see every
        # call, not only the ones a client made on purpose. Failures are not
        # logged because nothing was consumed.
        try:
            from database import log_token_usage  # noqa: PLC0415
            usage = payload.get("usage", {})
            log_token_usage(
                user_id=user_id,
                feature="translate",
                client_id=client_id,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
        except Exception:
            # Same rule as chat.py: a logging failure must not cost the client
            # the translation that was already paid for.
            pass
    except Exception:
        # Network, timeout, malformed envelope. All the same outcome: the
        # client keeps their text and the translation stays outstanding.
        return {}

    parsed = _extract_json(content)
    if not parsed:
        return {}

    # Keep only what was asked for. A model that invents a language, renames a
    # field or returns a nested object has produced something this cannot store
    # safely, and a wrong key would write a translation into the wrong column.
    out: dict[str, dict[str, str]] = {}
    for target in targets:
        block = parsed.get(target)
        if not isinstance(block, Mapping):
            continue
        cleaned = {
            field: str(block[field]).strip()
            for field in texts
            if isinstance(block.get(field), str) and str(block[field]).strip()
        }
        if cleaned:
            out[target] = cleaned
    return out


def apply_translations(
    i18n: Mapping[str, Mapping[str, str]],
    status: Mapping[str, Mapping[str, str]],
    drafts: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Merge drafts into the stored blobs WITHOUT overwriting reviewed text.

    `i18n` is keyed field -> language, which is how the columns are shaped;
    `drafts` arrives keyed language -> field, which is how the model answers.
    The transpose happens here so neither the caller nor the prompt has to
    care about the other's shape.

    A language already marked human is never touched. Regenerating over text a
    client has confirmed would silently replace their wording with the model's,
    and they would have no way of knowing.
    """
    merged = {f: dict(v) for f, v in (i18n or {}).items()}
    merged_status = {f: dict(v) for f, v in (status or {}).items()}

    for target, fields in (drafts or {}).items():
        for field, text in fields.items():
            if merged_status.get(field, {}).get(target) == "human":
                continue
            if (merged.get(field, {}).get(target) or "").strip() and \
                    field in merged_status and target in merged_status[field]:
                # Present and not machine-flagged: a human wrote it before
                # translation_status existed. Same rule applies.
                continue
            merged.setdefault(field, {})[target] = text
            merged_status.setdefault(field, {})[target] = "machine_unreviewed"

    return merged, merged_status


def outstanding(
    i18n: Mapping[str, Mapping[str, str]],
    status: Mapping[str, Mapping[str, str]],
    fields: list[str],
    languages: list[str],
) -> list[str]:
    """Human-readable list of what still needs a person: missing or unreviewed.

    Used to surface the gap on the activity list the way readiness() gaps
    already are. This is the interim home for it — the task register that
    should hold it does not exist yet, and until it does the only alternative
    is the gap being invisible.
    """
    out = []
    for field in fields:
        for language in languages:
            text = (i18n.get(field, {}) or {}).get(language)
            if not (text or "").strip():
                out.append(f"{field} ({language}): not translated")
            elif (status.get(field, {}) or {}).get(language) == "machine_unreviewed":
                out.append(f"{field} ({language}): awaiting review")
    return out
