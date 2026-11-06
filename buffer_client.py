"""
buffer_client.py — S57 (D-147): Buffer's GraphQL API, the little of it the
back office needs: list the channels, add a post to a channel's queue or
schedule it for a time, or save it as a draft on the channel (saveToDraft:
finished and published in Buffer itself).

Docs read 6 Nov 2026: developers.buffer.com (your-first-post, authentication,
posts-and-scheduling, error-handling, api-limits, ideas). Endpoint
https://api.buffer.com, `Authorization: Bearer <key>`, POST {"query": ...}.
GraphQL answers HTTP 200 even for errors: a mutation's own failure comes back
as a MutationError union member (`message`), a system failure in the
top-level `errors` (code UNAUTHORIZED, RATE_LIMIT_EXCEEDED, …).

The key is a personal API key (Buffer → Settings → API) and acts for the
whole Buffer account; it lives in the back office's secrets as
BUFFER_API_KEY, never in code. No client data goes to Buffer: only the
marketing text of a post (D-05 is about compliance content).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

ENDPOINT = "https://api.buffer.com"


class BufferError(RuntimeError):
    pass


def _key() -> str:
    """The key as pasted, without the spaces, line breaks or quotes a
    secrets box picks up (a 401 on the first live try, 6 Nov)."""
    return (os.environ.get("BUFFER_API_KEY") or "").strip().strip('"').strip("'").strip()


def configured() -> bool:
    return bool(_key())


def _s(value: str) -> str:
    """A GraphQL string literal. JSON's string syntax is GraphQL's."""
    return json.dumps(value, ensure_ascii=False)


def _gql(query: str) -> dict:
    key = _key()
    if not key:
        raise BufferError("BUFFER_API_KEY is not set.")
    try:
        r = requests.post(ENDPOINT, json={"query": query}, timeout=20,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"})
    except requests.RequestException as e:
        raise BufferError(f"Buffer could not be reached: {e}") from e
    if r.status_code == 401:
        raise BufferError("Buffer refused the API key (401). Check BUFFER_API_KEY.")
    if r.status_code == 429:
        raise BufferError("Buffer's rate limit is reached. Try again in a few minutes "
                          f"(Retry-After: {r.headers.get('Retry-After', '?')} s).")
    try:
        body = r.json()
    except ValueError:
        raise BufferError(f"Unexpected answer from Buffer (HTTP {r.status_code}).")
    if body.get("errors"):
        e = body["errors"][0]
        code = (e.get("extensions") or {}).get("code") or ""
        raise BufferError(f"Buffer: {e.get('message') or 'error'}" + (f" ({code})" if code else ""))
    return body.get("data") or {}


def organizations() -> list[dict]:
    data = _gql("query { account { organizations { id name } } }")
    return ((data.get("account") or {}).get("organizations")) or []


def channels() -> list[dict]:
    """Every channel of every organisation: [{id, name, service, org_id,
    org_name}], LinkedIn first."""
    out = []
    for org in organizations():
        data = _gql(f"query {{ channels(input: {{ organizationId: {_s(org['id'])} }}) "
                    "{ id name service } }")
        for c in data.get("channels") or []:
            out.append({**c, "org_id": org["id"], "org_name": org.get("name")})
    return sorted(out, key=lambda c: (c.get("service") != "linkedin", c.get("name") or ""))


def _lit(value) -> str:
    """A Python value as a GraphQL input literal (objects unquoted keys)."""
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k}: {_lit(v)}" for k, v in value.items() if v is not None) + " }"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_lit(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _s(str(value))


def create_post(channel_id: str, text: str, due_at: datetime | None = None,
                draft: bool = False, *, first_comment: str | None = None,
                annotations: list[dict] | None = None,
                image_url: str | None = None) -> dict:
    """Queue the post (next free slot), with due_at schedule it, or with
    draft=True save it as a draft on the channel (status 'draft': nothing is
    published until it is scheduled in Buffer). Returns {id, dueAt}.

    LinkedIn extras (D-149): first_comment (up to 1,250 characters),
    annotations (mentions: id, entity, link, localizedName, vanityName,
    start, length — the format a test draft confirmed on 6 Nov), image_url
    (a public, stable image URL; Buffer fetches it, there is no upload)."""
    if due_at:
        when = due_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        mode = f"mode: customScheduled, dueAt: {_s(when)}"
    else:
        mode = "mode: addToQueue"
    if draft:
        mode += ", saveToDraft: true"
    li = {}
    if first_comment:
        li["firstComment"] = first_comment[:1250]
    if annotations:
        li["annotations"] = annotations
    if li:
        mode += f", metadata: {_lit({'linkedin': li})}"
    if image_url:
        mode += f", assets: {_lit([{'image': {'url': image_url}}])}"
    data = _gql(f"""mutation {{
      createPost(input: {{ text: {_s(text)}, channelId: {_s(channel_id)},
                           schedulingType: automatic, {mode} }}) {{
        ... on PostActionSuccess {{ post {{ id dueAt }} }}
        ... on MutationError {{ message }}
      }}
    }}""")
    res = data.get("createPost") or {}
    if res.get("post"):
        return res["post"]
    raise BufferError(res.get("message") or "Buffer did not create the post.")


def create_idea(org_id: str, title: str, text: str) -> dict:
    """Save an Idea in the organisation, to finish and publish in Buffer."""
    data = _gql(f"""mutation {{
      createIdea(input: {{ organizationId: {_s(org_id)},
                           content: {{ title: {_s(title[:120])}, text: {_s(text)} }} }}) {{
        ... on Idea {{ id }}
        ... on MutationError {{ message }}
      }}
    }}""")
    res = data.get("createIdea") or {}
    if res.get("id"):
        return res
    raise BufferError(res.get("message") or "Buffer did not save the Idea.")
