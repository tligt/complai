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
  — **JSONB from the first row, written in English only for now.** Statements
  are internal today, so translating them is hard to justify; but S52's annual
  compliance report renders them and an InfoSec insert probably would, so they
  WILL reach a document.

  The expensive part of adding languages later is not the column, it is ending
  up with text whose language nobody recorded. That is what S26C hit: the
  backfill had to *assume* English, and the form still says "recorded before
  languages were tracked, and its language is unknown". Costing nothing now
  means every statement carries its language from the start.
- `reviewed_at`, `review_due` — seeded from the obligation's existing
  `review_in`, populated for 8 of 54 today
- `not_applicable_reason` — **required when status is `not_applicable`.** An
  obligation dismissed without a reason is the single most likely thing an
  auditor asks about, and the client will not remember.

Every change writes to the S21 audit trail. The register's value to an auditor
is that it shows a gap was found on one date and closed on another.

---

## What this changes elsewhere

**The dashboard score — DEFERRED, with a condition.**

Today it counts documents. This register could reflect coverage across all
applicable obligations, which is a different and much lower number.

Deferred to a later sprint. But the risk is not that the old score stays wrong
for another sprint: it is that **the register would publish its own coverage
figure while the dashboard publishes a different one, in the same product.**
Two numbers contradicting each other is worse than one honest low number.

So the register ships with **status per obligation and counts by state, and no
headline percentage.** Both move together in one sprint, with the explanation
in the same release — a client watching their score fall deserves to be told
why at the moment it happens.

When it does move, D-59 applies unchanged: `not_applicable` and anything
blocked on RECOSA must not count against the client.

**The task register is part of this sprint.** See below.

**S29 becomes smaller.** Three Tier 2 documents against a register that
already tracks the other twelve NIS2 obligations.

---

## The task register

In scope. It has been unnumbered since S26C and three sprints depend on it;
this is the first sprint that gives it something to attach to.

### Derived state, stored history

A task register can hold rows or compute them, and neither alone is right.

**Stored rows drift.** A task whose underlying gap was fixed elsewhere — the
translation confirmed, the document adopted, the retention structured — sits
there claiming to be open until something reconciles it. Reconciliation is
where these systems rot.

**Derived rows cannot remember.** Who is working on it, that it was dismissed
and why, that it was found in March and closed in April. That last one is the
whole audit value: *a gap was found on one date and closed on another.*

So: **the open list is DERIVED from its producers, and the history is STORED as
events.** A task is open because the producer still reports it, not because a
row says so. When the producer stops reporting it, the closure is recorded
rather than inferred, and the event survives even though the task does not.

### Producers

Each is a pure function returning findings — no Streamlit, no I/O (D-61), so
the register composes them rather than knowing about each source.

| producer | finding |
|---|---|
| obligation register (this sprint) | `review_due` passed; `not_started` on an in-force obligation |
| S26C translations | `machine_unreviewed` text reaching a document |
| S27 document register | draft never adopted; superseded version approaching `retain_until` |
| `readiness()` | activity gaps blocking a register |
| template rendering | outstanding `[[ TO COMPLETE ]]` placeholders |
| S55 (later) | RoPA consistency findings |
| S57 (later) | stale legal holds, published policy drift |

**S55 and S57 are not built yet.** The register must not require them — a
producer that does not exist contributes nothing, and adding one later is
registering a function.

### Events

`task_events`: client, `producer`, `finding_key`, `event` (`opened` /
`closed` / `dismissed` / `assigned` / `noted`), actor, timestamp, note.

`finding_key` is the stable identity of a finding — producer plus subject, for
example `translation:activity:<uuid>:purpose:fr`. Without it a finding that
disappears and returns cannot be told from a new one, and the history becomes
a list of unrelated events.

**Dismissal requires a reason**, same rule as `not_applicable` above and for
the same reason: it is what an auditor asks about and what the client will not
remember.

### Explicitly not

- **A to-do list clients can add items to.** Every task traces to a producer;
  free-form items are a different product and would break the derivation.
- **Assignment beyond a name.** Multi-user is S35.
- **Notification.** S57 owns the schedule. This is the surface it writes to.

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

## Resolved

**Dashboard score:** deferred, and the register publishes no headline
percentage until both move together. See above.

**Statement language:** `statement_i18n` JSONB from the start, English only in
this sprint. Not the interface language — English, fixed, so every statement is
comparable and the language is known rather than inferred from whoever happened
to be logged in.
