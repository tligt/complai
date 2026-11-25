"""
backfill_title_en.py — D-208. English titles for regulatory updates already
stored whose source is not in English (title_en is NULL). New items get one
from the monitor; this is the one-off for the rows before it.

    python backfill_title_en.py            # show what would be written
    python backfill_title_en.py --write    # write it

Uses the environment's SUPABASE_* and MISTRAL_API_KEY (.env locally, the
container's environment on production). Rejected items are skipped.
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import get_supabase_admin
from mistral_text import message_text

BATCH = 20


def translate_titles(titles: list[str]) -> list[str]:
    prompt = ("Translate each of these regulatory news titles into English. Keep names, "
              "acronyms and figures as they are. Return ONLY a JSON array of strings, "
              "same order, same length.\n\n" + json.dumps(titles, ensure_ascii=False))
    r = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['MISTRAL_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": "mistral-medium-latest", "temperature": 0.1, "max_tokens": 4000,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    try:
        from database import log_mistral_usage
        log_mistral_usage(data, "title_en_backfill")
    except Exception:
        pass
    raw = re.sub(r"```json|```", "", message_text(data)).strip()
    out = json.loads(re.search(r"\[[\s\S]*\]", raw).group(0))
    if len(out) != len(titles):
        raise ValueError(f"{len(out)} translations for {len(titles)} titles")
    return [str(t).strip() for t in out]


def main(write: bool) -> None:
    sb = get_supabase_admin()
    rows = (sb.table("regulatory_updates").select("id, title, language, status")
            .neq("language", "en").is_("title_en", "null").neq("status", "rejected")
            .execute().data or [])
    print(f"{len(rows)} item(s) without an English title")
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        for row, en in zip(chunk, translate_titles([r["title"] for r in chunk])):
            print(f"- [{row['language']}] {row['title']}\n  → {en}")
            if write and en:
                sb.table("regulatory_updates").update({"title_en": en}).eq("id", row["id"]).execute()
    print("Written." if write else "Nothing written (add --write).")


if __name__ == "__main__":
    main("--write" in sys.argv)
