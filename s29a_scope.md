# S29A — Obligation register — scope lock

**Position:** before S29. The NIS2 documents satisfy three obligations; this
gives all 54 a home, and S29 then slots into a register that already exists
rather than one built around it afterwards.

---

## Why

**38 of 54 obligations have no home in the product.** Documents are 16.

| regulation | total | no doc_type |
|---|---|---|
| GDPR | 20 | 14 |
| NIS2 | 15 | 11 |
| EU AI Act | 14 | 11 |
| ePrivacy | 5 | 2 |

Seventy per cent of the compliance surface RECOSA claims to cover is invisible.
A client sees a checkbox on a dashboard and has nowhere to record what they
actually do about it — no evidence, no date, no reviewer, no history.

So they keep a spreadsheet. **That spreadsheet is the competitor**, not
Adequacy, and it is where the parts of their compliance RECOSA cannot hold end
up living.

This is the gap between "RECOSA generates compliance documents" and "RECOSA is
where your compliance lives", which is the positioning the product is sold on.

It is also the piece several registered sprints are waiting for. S50's training
register is one obligation's evidence. S55's consistency findings need
somewhere to land. The task register needs something to attach to. Each is a
fragment of this.

---

## Response types

Not every obligation is answered the same way, and forcing one shape on all 54
is what makes compliance tools feel like paperwork.

**1. `derived` — RECOSA already knows.**

The finding that makes this sprint worth doing. A meaningful share of the
"operational" obligations are answerable from S24 and S26 data:

| obligation | answered from |
|---|---|
| `gdpr_04` DPO appointed | client record |
| `gdpr_05` DPAs with all processors | `systems.dpa_status` |
| `gdpr_11` transfer safeguards | `systems.transfer_mechanism` |
| `gdpr_16` special category safeguards | `activities.art9_condition` |
| `gdpr_17` joint controller documented | `activity_systems.role` |
| `gdpr_18` legitimate interest assessment | `legitimate_interest_note` |
| `gdpr_20` security measures | `activities.security_measures` |

The client confirms or corrects; they do not retype. **This is the difference
between a register worth keeping and a checklist.**

Each derivation is a pure function over the inventory, in a module with no
Streamlit in it (D-61), so it is testable — and each is a compliance verdict,
which is exactly the class of logic that belongs there.

**2. `document` — generates or holds one.** Links to the S27 register and
inherits its status. No second source of truth for whether a document exists.

**3. `statement` — the client describes what they do.** Free text, per
language once S26C's pattern is reused. For obligations where the answer is
genuinely theirs and RECOSA has no view: `nis2_06` access control,
`nis2_07` cryptography.

**4. `evidence` — a file.** A penetration test report, a certificate, minutes
recording management approval. Opaque, like S27 uploads: held, not parsed.

**5. `acknowledgement` — who confirmed, and when.** For obligations that are an
act rather than an artefact: `nis2_11` registration with the national
authority, `nis2_12` management body approval. **A name and a date, because an
unattributed tick is not evidence of anything.**

**6. `tracked_elsewhere` — points into the product.** `gdpr_13` and `nis2_09`
training resolve to S50's training register. The register shows the status and
links; it does not hold a second copy.

---

## Schema

`obligation_responses`, one row per (client, obligation_id):

- `response_kind` — from the six above, resolved per obligation, not per row
- `status` — `not_started` / `in_progress` / `done` / `not_applicable`
- `statement_i18n` JSONB, `evidence_path`, `acknowledged_by`, `acknowledged_at`
- `reviewed_at`, `review_due` — seeded from the obligation's existing
  `review_in`, populated for 8 of 54 today
- `not_applicable_reason` — **required when status is `not_applicable`.** An
  obligation dismissed without a reason is the single most likely thing an
  auditor asks about, and the client will not remember.

Every change writes to the S21 audit trail. The register's value to an auditor
is that it shows a gap was found on one date and closed on another.

---

## What this changes elsewhere

**The dashboard score.** Today it counts documents. With this it can reflect
actual coverage across all applicable obligations, which is a different and
much lower number. Honest, and a visible drop — the same care as D-59 applies:
`not_applicable` and anything blocked on RECOSA must not count against the
client.

**The task register** finally has something to attach to. An obligation with a
`review_due` in the past is a task; so is an unreviewed translation and an
S55 finding. **Decide whether the task register is part of this sprint or
immediately after** — it is the natural home for every deferred item in this
log, and three sprints now depend on it.

**S29 becomes smaller.** Three Tier 2 documents against a register that
already tracks the other twelve NIS2 obligations.

---

## Out of scope

- Changing `kind` on any obligation. `nis2_12` stays operational — see the
  S29 scope lock; a document whose entire content is "we have measures in each
  area" is a table of contents with assertions under it.
- Scoring changes. The register is built first and the score moved
  deliberately, not as a side effect.
- Evidence parsing. Files are held, not read.
- New obligations. The catalogue is the input, not the output.

---

## Open — needs a decision

1. **Task register in this sprint, or immediately after?** Three sprints
   depend on it and it has no number.
2. **Does the dashboard score move in this sprint or a later one?** It will
   drop visibly, and it should — but a client watching it fall deserves the
   explanation shipped alongside.
3. **Per-language statements, or English only for now?** S26C's pattern exists
   and works, but statements are internal rather than published, and the case
   for translating them is weaker than for a privacy policy.
