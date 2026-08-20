"""
template_seed_lib.py — S26

Shared machinery for the per-document authoring scripts.

Extracted from template_seed.py, which was written for one document type:
DOC_TYPE, SOURCE_REVISION and VERSION_NO were module-level constants and
emit_sql() inserted a single document_templates row. S26 adds two more types
and S26A adds the DPA.

WHY A LIBRARY AND NOT ONE BIG SEED FILE
---------------------------------------
The authoring surface stays one file per legal document, because a lawyer
reviews one document and not the others, and because a Cookie Policy and an
Art. 30 register change on entirely different schedules. Bundling them would
mean regenerating and re-reviewing text nobody touched.

The machinery lives here so the self-check cannot drift between documents —
copying check_bodies() three times is how one of the copies quietly loses rule
5 and a French body starts missing a paragraph the English one has.

NEVER IMPORTED AT RUNTIME. Same contract as inventory_seed.py.

AUTHORING CONTRACT
------------------
An authoring script defines a TemplateDoc and calls run(). Nothing else:

    from template_seed_lib import TemplateDoc, run

    DOC = TemplateDoc(
        doc_type="ropa_controller",
        title="Record of Processing Activities — Controller",
        tier=1,
        sort_order=20,
        sprint="S26",
        bodies={"en": BODY_EN, "fr": BODY_FR},
        blocks={"ropa_controller_table"},
    )

    if __name__ == "__main__":
        run(DOC, "seed_s26_ropa_controller.sql")
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Mapping

from template_store import FIELD_SPECS


# The template syntax, mirrored from template_renderer. Deliberately a second
# copy: this file must be able to reject a body WITHOUT importing the renderer,
# so a broken renderer cannot make the self-check pass by agreeing with it.
_FIELD_RE = re.compile(r"\{\{([a-z0-9_]+)\}\}")
_IF_RE = re.compile(r"\{\{#(if|ifnot):([a-z0-9_]+)\}\}")
_CLOSE_RE = re.compile(r"\{\{/(if|ifnot):([a-z0-9_]+)\}\}")
_BLOCK_RE = re.compile(r"\{\{#block:([a-z0-9_]+)\}\}")

BASELINE_LANG = "en"


@dataclass
class TemplateDoc:
    doc_type: str
    title: str
    bodies: Mapping[str, str]
    blocks: set[str] = field(default_factory=set)
    tier: int = 1
    sort_order: int = 0
    version_no: int = 1
    source_revision: int = 1
    materiality: str = "required"
    sprint: str = "S26"
    effective_from: str = field(default_factory=lambda: date.today().isoformat())
    change_note: str | None = None

    @property
    def note(self) -> str:
        return self.change_note or f"Initial version ({self.sprint})."


# ===========================================================================
# SELF-CHECK
# ===========================================================================
# Runs before anything is emitted. A typo'd merge field does not fail loudly
# at render time — it renders "[[ TO COMPLETE: unknown field 'legal_nmae' ]]"
# into a legal document.

def check_bodies(doc: TemplateDoc) -> list[str]:
    errors: list[str] = []

    if doc.doc_type not in FIELD_SPECS:
        return [f"no FIELD_SPECS entry for doc_type '{doc.doc_type}'"]
    specs = {s.name: s for s in FIELD_SPECS[doc.doc_type]}

    if BASELINE_LANG not in doc.bodies:
        errors.append(f"no '{BASELINE_LANG}' body — it is the translation baseline")

    for lang, body in doc.bodies.items():
        # 1. Every substituted field is declared.
        for name in sorted(set(_FIELD_RE.findall(body))):
            if name not in specs:
                errors.append(f"[{lang}] undeclared field: {name}")
            elif specs[name].flag:
                errors.append(
                    f"[{lang}] {name} is a flag and must be used in a "
                    f"conditional, not substituted as text"
                )

        # 2. Every conditional tests a declared flag.
        for kind, name in _IF_RE.findall(body):
            if name not in specs:
                errors.append(f"[{lang}] #{kind} on undeclared field: {name}")
            elif not specs[name].flag:
                errors.append(
                    f"[{lang}] #{kind}:{name} tests a value field. Conditionals "
                    f"take flags — otherwise the branch silently depends on "
                    f"whether the client filled a text box."
                )

        # 3. Conditionals balance. An unclosed one strips silently at render.
        opens = sorted(_IF_RE.findall(body))
        closes = sorted(_CLOSE_RE.findall(body))
        if opens != closes:
            errors.append(f"[{lang}] unbalanced conditionals: {opens} vs {closes}")

        # 4. Blocks exist.
        for name in _BLOCK_RE.findall(body):
            if name not in doc.blocks:
                errors.append(f"[{lang}] unknown block: {name}")

        # 4b. A block tag must sit alone on its line. _BLOCK_RE in the renderer
        #     is anchored with [ \t]*$; a tag with text beside it silently
        #     never matches and the table simply does not appear.
        for line in body.splitlines():
            if "{{#block:" in line and line.strip() != line.strip():
                pass
            if "{{#block:" in line:
                stripped = line.strip()
                if not (stripped.startswith("{{#block:") and stripped.endswith("}}")):
                    errors.append(
                        f"[{lang}] block tag shares a line with other text: "
                        f"{line.strip()[:60]!r} — the renderer's anchored regex "
                        f"will not match it and the table will vanish silently"
                    )

        # 4c. Declared blocks are actually used. A block the store builds and
        #     no body references is dead work at generation time.
        used_blocks = set(_BLOCK_RE.findall(body))
        for name in sorted(doc.blocks - used_blocks):
            errors.append(f"[{lang}] declared block never used: {name}")

    # 5. Languages agree on which fields they use. A field present in one body
    #    and absent from another means the translation drifted from the source
    #    — a French reader silently loses a paragraph the English reader gets.
    used = {
        lang: set(_FIELD_RE.findall(b)) | {n for _, n in _IF_RE.findall(b)}
        for lang, b in doc.bodies.items()
    }
    if BASELINE_LANG in used:
        for lang, names in used.items():
            if lang == BASELINE_LANG:
                continue
            missing = used[BASELINE_LANG] - names
            extra = names - used[BASELINE_LANG]
            if missing:
                errors.append(f"[{lang}] fields present in en but missing: {sorted(missing)}")
            if extra:
                errors.append(f"[{lang}] fields not present in en: {sorted(extra)}")

    # 6. Every required field is actually referenced. A required field no body
    #    uses blocks generation for nothing.
    referenced: set[str] = set().union(*used.values()) if used else set()
    for name, spec in specs.items():
        if spec.required and name not in referenced:
            errors.append(
                f"required field '{name}' is declared but referenced by no "
                f"body — it would block generation and change nothing"
            )

    # 7. CRLF. Body text reaches Postgres through this file, and a template
    #    saved on Windows lost every block once already — _BLOCK_RE cannot
    #    match a \r before the newline. The renderer normalises defensively;
    #    catching it here means it never gets stored wrong in the first place.
    for lang, body in doc.bodies.items():
        if "\r" in body:
            errors.append(f"[{lang}] body contains CR characters — save as LF")

    return errors


# ===========================================================================
# SQL EMISSION
# ===========================================================================

def _dollar_quote(text: str, tag: str) -> str:
    """Dollar-quote rather than escape.

    These bodies contain apostrophes throughout ("l'autorité", "d'entreprise").
    Doubling them is a correctness hazard for exactly the language most likely
    to need it, so the quoting mechanism sidesteps escaping entirely.
    """
    marker = f"${tag}$"
    if marker in text:
        raise ValueError(f"body contains the dollar-quote tag {marker}")
    return f"{marker}{text}{marker}"


def emit_sql(doc: TemplateDoc, filename: str) -> str:
    parts: list[str] = []
    parts.append(f"""\
-- ============================================================================
-- {filename}
-- GENERATED — DO NOT EDIT THIS FILE.
--
-- Edit the authoring script and regenerate. Editing here means the next
-- regeneration silently discards the change.
--
-- Idempotent. Re-running updates the bodies in place.
--
-- DRAFT FOR LEGAL REVIEW — not yet reviewed by counsel.
-- ============================================================================

INSERT INTO document_templates (doc_type, title, tier, active, sort_order)
VALUES ('{doc.doc_type}', '{doc.title.replace("'", "''")}', {doc.tier}, TRUE, {doc.sort_order})
ON CONFLICT (doc_type) DO UPDATE
SET title = EXCLUDED.title,
    tier = EXCLUDED.tier,
    active = EXCLUDED.active,
    sort_order = EXCLUDED.sort_order;
""")

    # Supersede any earlier in-force version FIRST.
    #
    # dtv_one_in_force_per_language allows exactly one in_force row per
    # (template, language). Emitting a version 2 as in_force while version 1
    # still is violates it, and the seed fails on a unique constraint rather
    # than doing anything useful. A revision is a supersession, not an
    # addition — the previous body stays in the table as evidence of what a
    # document generated last month was rendered from.
    if doc.version_no > 1:
        parts.append(f"""
UPDATE document_template_versions v
SET status = 'superseded'
FROM document_templates t
WHERE t.id = v.template_id
  AND t.doc_type = '{doc.doc_type}'
  AND v.status = 'in_force'
  AND v.version_no < {doc.version_no};
""")

    for lang, body in doc.bodies.items():
        quoted = _dollar_quote(body, f"body_{lang}")
        parts.append(f"""
INSERT INTO document_template_versions
    (template_id, language, version_no, source_revision, body_md,
     materiality, status, change_note, effective_from)
SELECT id, '{lang}', {doc.version_no}, {doc.source_revision},
       {quoted},
       '{doc.materiality}', 'in_force', '{doc.note.replace("'", "''")}',
       DATE '{doc.effective_from}'
FROM document_templates WHERE doc_type = '{doc.doc_type}'
ON CONFLICT (template_id, language, version_no) DO UPDATE
SET source_revision = EXCLUDED.source_revision,
    body_md         = EXCLUDED.body_md,
    materiality     = EXCLUDED.materiality,
    status          = EXCLUDED.status,
    change_note     = EXCLUDED.change_note,
    effective_from  = EXCLUDED.effective_from;
""")

    langs = ", ".join(f"'{l}'" for l in doc.bodies)
    parts.append(f"""
-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
-- SELECT t.doc_type, v.language, v.version_no, v.source_revision, v.status,
--        v.effective_from, length(v.body_md) AS body_chars
-- FROM document_template_versions v
-- JOIN document_templates t ON t.id = v.template_id
-- WHERE t.doc_type = '{doc.doc_type}'
-- ORDER BY v.language;
--
-- Expect {len(doc.bodies)} in_force rows ({langs}) at version {doc.version_no},
-- source_revision {doc.source_revision}. Earlier versions remain, superseded —
-- they are what previously generated documents were rendered from and must
-- not be deleted.
--
-- SELECT t.doc_type, v.language, v.version_no, v.status
-- FROM document_template_versions v
-- JOIN document_templates t ON t.id = v.template_id
-- WHERE t.doc_type = '{doc.doc_type}' ORDER BY v.language, v.version_no;
--
-- NOTE ON RE-RUNNING: the ON CONFLICT arbiter is the real UNIQUE constraint
-- (template_id, language, version_no). It is NOT the partial index
-- dtv_one_in_force_per_language, which cannot arbitrate — a partial index
-- raises 42P10 if named as a conflict target.
""")
    return "".join(parts)


def run(doc: TemplateDoc, filename: str) -> None:
    """Self-check, then emit to stdout. Exits non-zero and emits nothing on
    failure — a half-valid seed applied to Postgres is worse than no seed."""
    problems = check_bodies(doc)
    if problems:
        print(f"SELF-CHECK FAILED ({doc.doc_type}) — nothing emitted:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)
    print(emit_sql(doc, filename))
