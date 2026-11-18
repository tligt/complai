"""
load_template_nl.py — S64 (D-163). Load the nl-BE template translations.

Each templates/nl_BE/<doc_type>.md is a translation of that document's
in-force English body. Loaded as language 'nl', valid for nl-BE and nl-NL (the user's decision,
10 Nov: one Dutch text for both until a Netherlands text exists), at the
English version's version_no and source_revision (the same document, another
language — S27).

    python load_template_nl.py                 # check and load every file
    python load_template_nl.py --check         # check only
    python load_template_nl.py privacy_policy  # one document

REFUSES a file whose structure differs from the English one: the same merge
fields, the same conditionals, the same tables, each table tag on its own
line, no CR. A translation that drops a {{#if}} renders a paragraph the
English would not, and nobody reading Dutch would notice.

Every file must carry the draft banner (DRAFT_BANNER) until a Belgian lawyer
has reviewed it; the reviewer removes it and the file is loaded again.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent / "templates" / "nl_BE"
DRAFT_BANNER = "*Conceptvertaling — nog niet nagekeken door een Belgische jurist.*"
# S72 (D-190): the DPA is not a translation. Its clauses are the official
# Dutch text of Decision 2021/915, built by template_seed_dpa_patch.py into
# templates/dpa_scc_nl.md (cover and annexes are RECOSA's Dutch, hence the
# same draft banner until the lawyer's review). Loaded from there, not nl_BE/.
DPA_NL = ROOT.parent / "dpa_scc_nl.md"

_FIELD = re.compile(r"\{\{([a-z0-9_]+)\}\}")
_COND = re.compile(r"\{\{#(if|ifnot):([a-z0-9_]+)\}\}")
_CLOSE = re.compile(r"\{\{/(if|ifnot):([a-z0-9_]+)\}\}")
_BLOCK = re.compile(r"\{\{#block:([a-z0-9_]+)\}\}")


def structure(body: str) -> dict:
    return {
        "fields": sorted(set(_FIELD.findall(body))),
        "conds": sorted(_COND.findall(body)),
        "closes": sorted(_CLOSE.findall(body)),
        "blocks": sorted(_BLOCK.findall(body)),
    }


def check(doc_type: str, en: str, nl: str) -> list[str]:
    errs = []
    a, b = structure(en), structure(nl)
    for k in ("fields", "conds", "closes", "blocks"):
        if a[k] != b[k]:
            errs.append(f"{doc_type}: {k} differ — en {set(a[k]) ^ set(b[k])}")
    if b["conds"] != b["closes"]:
        errs.append(f"{doc_type}: unbalanced conditionals")
    for line in nl.splitlines():
        if "{{#block:" in line and not (line.strip().startswith("{{#block:") and line.strip().endswith("}}")):
            errs.append(f"{doc_type}: block tag shares a line: {line.strip()[:60]!r}")
    if "\r" in nl:
        errs.append(f"{doc_type}: contains CR")
    if DRAFT_BANNER not in nl:
        errs.append(f"{doc_type}: draft banner missing")
    return errs


def main(argv: list[str]) -> int:
    from database import get_supabase_admin
    only_check = "--check" in argv
    wanted = [a for a in argv if not a.startswith("--")]
    sb = get_supabase_admin()
    rows = (sb.table("document_template_versions")
            .select("template_id, language, version_no, source_revision, materiality, body_md, "
                    "document_templates!inner(doc_type)")
            .eq("status", "in_force").eq("language", "en").execute().data or [])
    en = {r["document_templates"]["doc_type"]: r for r in rows}
    files = sorted(ROOT.glob("*.md")) + ([DPA_NL] if DPA_NL.exists() else [])
    failures = 0
    for f in files:
        dt = "dpa" if f == DPA_NL else f.stem
        if wanted and dt not in wanted:
            continue
        if dt not in en:
            print(f"{dt}: skipped (no English version)")
            continue
        nl = f.read_text(encoding="utf-8").replace("\r\n", "\n")
        errs = check(dt, en[dt]["body_md"], nl)
        if errs:
            failures += 1
            print("\n".join("  REFUSED " + e for e in errs))
            continue
        if only_check:
            print(f"{dt}: ok")
            continue
        r = en[dt]
        sb.table("document_template_versions").upsert({
            "template_id": r["template_id"], "language": "nl", "version_no": r["version_no"],
            "source_revision": r["source_revision"], "body_md": nl, "materiality": r["materiality"],
            "status": "in_force", "locales": ["nl-BE", "nl-NL"],
            "effective_from": __import__("datetime").date.today().isoformat(),
            "change_note": ((f"Official Dutch text of Decision (EU) 2021/915, with RECOSA's Dutch "
                             f"cover and annexes, at the English version {r['version_no']} (S72, D-190). "
                             "Cover and annexes not yet reviewed by a Belgian lawyer.")
                            if dt == "dpa" else
                            (f"nl-BE draft translation of the English version {r['version_no']} "
                             "(S64, D-163). Not yet reviewed by a Belgian lawyer.")),
        }, on_conflict="template_id,language,version_no").execute()
        print(f"{dt}: loaded (nl-BE, version {r['version_no']})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
