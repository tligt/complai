"""
dedup.py — is this monitoring item one we already have? (BO review, 9 Nov)

The EDPB feed lists one news item twice with the words reordered: "fined
Securitas Direct EUR 100 000" and "fined Securitas Direct 100 000 EUR". The
monitor only skipped an identical title from the same source, so both
reached the review queue. Two titles are the same item when they have the
same words in any order, or nearly so (Jaccard similarity of their word
sets at least SAME_THRESHOLD, for a changed article or a typo).

No Streamlit, no database: used by monitor.py at intake and by the back
office's Monitoring page to mark the duplicates already in the queue.
"""

from __future__ import annotations

import re
import unicodedata

SAME_THRESHOLD = 0.85
_MIN_WORDS = 4          # shorter titles ("Vulnerability Services") must match exactly


def words(title: str | None) -> list[str]:
    """Lower-case words without accents or punctuation; numbers kept."""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    return re.findall(r"[a-z0-9]+", t)


def title_key(title: str | None) -> str:
    """The same for two titles with the same words in any order."""
    return " ".join(sorted(words(title)))


def same_item(a: str | None, b: str | None) -> bool:
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    if sorted(wa) == sorted(wb):
        return True
    sa, sb = set(wa), set(wb)
    if min(len(sa), len(sb)) < _MIN_WORDS:
        return False
    return len(sa & sb) / len(sa | sb) >= SAME_THRESHOLD


def mark_duplicates(rows: list[dict], *, title: str = "title", source: str = "source",
                    order: str = "detected_at") -> dict[str, str]:
    """{id of a duplicate: id of the item it repeats}, the oldest of a group
    kept as the original. Only within one source: across sources a shared
    story is not a repeat (monitor.find_covering_update handles that, for
    the sources that ask for it)."""
    out: dict[str, str] = {}
    by_source: dict[str, list[dict]] = {}
    for r in rows:
        by_source.setdefault(r.get(source) or "", []).append(r)
    for group in by_source.values():
        group = sorted(group, key=lambda r: r.get(order) or "")
        originals: list[dict] = []
        for r in group:
            hit = next((o for o in originals if same_item(o.get(title), r.get(title))), None)
            if hit:
                out[r["id"]] = hit["id"]
            else:
                originals.append(r)
    return out
