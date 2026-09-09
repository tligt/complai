# S26A — build status and decisions, 21 Aug 2026

Supersedes the "Build status at handover" and "Note on the source" sections of
`s26a_scope_lock_corrections.md`. Issued after building against the real
`template_seed_lib.py` and `template_store.py` rather than against the file
layout described in the handover.

---

## Correction 4 — `body_from_file()` was not written

The handover marks it ✅ *written, parses*. It is not in `template_seed_lib.py`,
and that file does not import `Path`. Now written.

Worth noting for its own sake: two of the four ✅ items in that handover were
carried forward from intent rather than from the file. The other was the
Section I transcription, which turned out to contain correction 5 below. A ✅
in a handover written at the end of a session is a claim about what was
believed, not about what is on disk.

## Correction 5 — Section I as committed modified clause text

Clauses 1(b), 1(e), 1(f), 3(a), 3(b) and 3(c) carry "and/or Regulation (EU)
2018/1725" in the Official Journal with **no** `[OPTION]` markers. Only five
places in the whole instrument are marked choices: Clause 1(a), 8(c)(4),
9.1(b), 9.1(c), and the closing paragraph of 9.2.

Stripping the unmarked EUDPR references is a Clause 2(a) modification. It is
also self-defeating: the verification method is a diff against the OJ, and a
body with authorised deviations in it can never diff clean, so the reviewer
has to hold a mental list of which differences are fine.

Resolved by construction — the body is no longer transcribed. See below.

## Correction 6 — Annex IV is emitted, not omitted

Correction 2 concluded Annex IV is not used, which is right, and inferred it
should not appear, which is wrong. Clause 1(d) makes Annexes I to IV integral
to the Clauses. An annex that states why it is empty reads better than a
dangling reference to one that is missing.

## Correction 7 — the sub-processor scoping in correction 2 was wrong twice

Recorded as: S24 `systems` filtered to `role != 'internal'`.

`role` is not on `systems`. It is on `activity_systems`, because a vendor can
be processor for one activity and joint controller for another.

More seriously, filtering the whole inventory lists every vendor the client
uses, including those touching only their own controller-side data. In a
signed contract with a customer that names, as sub-processors of that
customer's data, vendors which never see it — and each name is one the
controller may object to under Clause 7.7(a). Over-naming is not the safe
direction.

Correct predicate: systems joined to activities with
`controller_role='processor'`, excluding `_NON_RECIPIENT_ROLES`.

---

## D-44 — Annex III parts 2 and 3 get RECOSA defaults, editable, not scored

Clause 8(d) requires Annex III to set out the measures by which the processor
assists the controller and the scope and extent of that assistance. The closing
paragraph of Clause 9.2 requires the further elements provided when assisting
with breach notification. Neither has an S24 source: `security_measures` are
controls, assistance is a service commitment.

Rejected: leaving them blank (emits a DPA that fails its own clauses), and
deriving them from `security_measures` (answers a different question).

**Adopted:** a RECOSA-authored default the client edits, on the D-43 reasoning
— a commercial term on the client's contract with their own customer, where
RECOSA supplies a defensible starting point and does not score the answer.
Part 3 is the more determinate of the two, since Clause 9.2(a)–(c) already
fixes the minimum content and the default adds only the routing.

Not a `readiness()` check.

---

## File layout — changed again

The clause text is no longer authored by RECOSA in any form. It is downloaded
from EUR-Lex and patched mechanically.

- `templates/raw/dpa_scc_{en,fr}.oj.md` — the Annex of CELEX:32021D0915,
  committed unedited. Never hand-edited.
- `template_seed_dpa_patch.py` — applies six documented edits and asserts each
  anchor. Contains no clause wording: every resolved option is regex-captured
  out of the raw text and re-emitted.
- `templates/dpa_scc_{en,fr}.md` — generated. Regenerating reverts any hand
  edit silently, so the header says so.
- `.gitattributes` — `templates/*.md text eol=lf` and the same for
  `templates/raw/*.md`. `body_from_file()` normalises defensively, but the
  attribute is the real fix: with `core.autocrlf=true` an LF-committed file
  arrives as CRLF on a Windows checkout through nobody's fault, and check 7
  would make the seed unrunnable there.

**Why this is better than a transcription.** D-42 requires the text be verified
rather than trusted. A hand-typed transcription needs 100% verification. A
downloaded file needs only the patch reviewed — six edits, each asserted, none
of which rewrites Commission wording. Counsel reviews a diff, not a contract.

---

## Build status

- ✅ `template_seed_lib.body_from_file()`
- ✅ `template_seed_dpa_patch.py` — self-test passes; `verify()` enforces the
  same rules `check_bodies()` does (field names, block syntax and line
  anchoring, conditional balance, flag set) so the two cannot disagree
- ✅ `template_seed_dpa.py`
- ✅ `FIELD_SPECS["dpa"]`, `DOC_BLOCKS["dpa"]`, `format_notice_period()`
- ✅ Annex II / Annex III / sub-processor loaders, D-44 default texts
- ⬜ `templates/raw/dpa_scc_{en,fr}.oj.md` — download from EUR-Lex
- ⬜ The five block renderers — needs the `Block` /
  `DEFAULT_BLOCK_RENDERERS` contract from `template_renderer.py`
- ⬜ `build_block_context()` and `build_values()` branches (wiring drafted)
- ⬜ Gate in `pages/documents.py` — hidden when no `controller_role='processor'`
  activity exists. Expose the predicate as a helper rather than duplicating
  the filter in the page.

**First real test** is `python template_seed_dpa.py`, where `check_bodies()`
sees the generated bodies against `FIELD_SPECS["dpa"]` for the first time.

**Watch on the first run:** `normalise()`'s unwrap regex has only been
exercised against synthetic input. If the EUR-Lex export wraps in a way the
negative lookahead does not anticipate, the symptom is a clause heading
swallowed into the preceding paragraph, which `verify()` catches as a clause
count under 10.

---

## Carried forward, unresolved

- `sort_order=40` for the DPA is a guess — confirm against the S25/S26 seeds.
- `activity_systems.role` vs `system_role` is still unverified (noted in
  `template_store.py`'s adapter section). The sub-processor loader depends on
  it; a 400 on that select is the cause.
- `registered_address` gets `"  \n"` hard breaks in `build_values`. In Annex I
  it sits indented under a numbered list item — eyeball the first render.
- `sub_processor_notice_days` needs a home: client profile column, or a DPA
  settings row.
