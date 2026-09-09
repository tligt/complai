# S29 — NIS2 pack — scope lock

**Tier 2. This one genuinely needs LLM inserts**, unlike S28.

S28 turned out to be Tier 1 because Art. 13/14 prescribe the content and every
prescribed item was already structured data. NIS2 Art. 21(2) does the opposite:
it names ten *areas* an entity must have measures for and says nothing about
what the measures are. The answer is specific to the organisation, and the
inventory does not hold it.

---

## Finding 1 — `incident_response` carries five obligations

| id | regulation | article | what it actually requires |
|---|---|---|---|
| `gdpr_06` | GDPR | 33/34 | personal data breach notification procedure |
| `nis2_01` | NIS2 | 21 | cybersecurity risk assessment |
| `nis2_02` | NIS2 | 21 | incident response plan |
| `nis2_03` | NIS2 | 23 | significant incident reporting, 24h/72h/1 month |
| `nis2_04` | NIS2 | 21 | business continuity plan |

**One doc_type, five obligations, two regulations.** A risk assessment is not
an incident response plan; a BCP is not either.

The immediate consequence is a live scoring defect of a shape already in this
log: a client who uploads an incident response plan scores as having a business
continuity plan, because both resolve to `incident_response`. It is the
`"rop"`/`"ropa"` shape, and S26 resolved the identical case by retiring the
ambiguous code for specific ones.

**Nothing has ever been generated as `incident_response`**, so the split is
free today and stops being free the first time it is.

## Finding 2 — the roadmap and the catalogue disagree

The roadmap says "InfoSec + BCP + Data Breach Procedure".

There is **no InfoSec document obligation in the catalogue.** `nis2_12`
("management body approved cybersecurity policy") is `kind: operational` with
`doc_type: None`. Meanwhile the catalogue has three document obligations the
roadmap does not name: risk assessment, incident response plan, and the Art. 23
reporting procedure.

`obligations.py` is the single source of truth (D-02). **The catalogue wins.**
The roadmap line was written before the catalogue was, and is not evidence of
anything.

---

## Proposed doc types

Append-only. `incident_response` is retired, not reused.

| doc_type | obligations | tier |
|---|---|---|
| `infosec_policy` | nis2_12 (see below) | 2 |
| `incident_response_plan` | nis2_02 | 2 |
| `breach_notification_procedure` | gdpr_06, nis2_03 | 2 |
| `business_continuity_plan` | nis2_04 | 2 |
| — | nis2_01 stays operational, see below | — |

### `nis2_12` becomes a document obligation

Art. 21(1) requires the measures to be taken; Art. 20(1) makes the management
body approve them and supervises implementation. **The approval is an act; the
policy is a document, and you cannot approve one that does not exist.**

Marking it operational was reasonable when there was no template to point at.
There is now.

*Change of `kind`, not of code* — the id and its article stay, so no client
data is orphaned.

### `nis2_01` stays operational

A risk assessment is an assessment, not a template. Threats, vulnerabilities,
likelihood, impact, treatment decisions — none of it is in the data model, and
none of it is prose RECOSA can supply.

**It is closer to S30's DPIA than to anything in this sprint**, and the honest
options are its own sprint alongside S30, or an upload slot in the register
where the client puts theirs. Generating one from nothing would be the
placeholder failure S28 was careful to avoid.

---

## The breach procedure is two regimes, one document

The scoping decision that matters most.

| | GDPR Art. 33 | NIS2 Art. 23 |
|---|---|---|
| trigger | personal data breach | significant incident |
| to | supervisory authority (GBA/APD, CNIL) | CSIRT or competent authority |
| clock | 72 hours | **24 hours** early warning, 72h notification, 1 month final report |
| subjects | Art. 34 where high risk | recipients where appropriate |

Most incidents are one or the other. **Some are both** — ransomware on a system
holding personal data starts both clocks, and the 24-hour one binds.

**One document, two decision paths, and an explicit both-apply case.** Two
separate documents would mean a client under time pressure choosing between
them at the worst possible moment, and the choice is exactly what they are
least able to make in the first hour.

*Rejected:* one merged procedure with a single timeline. It would have to state
either 24 or 72 hours, and whichever it chose would be wrong half the time.

*Rejected:* two documents. The overlap case is real and neither document would
own it.

---

## Where the LLM inserts go

Tier 2 means template with bounded inserts, not generated prose. Candidate
inserts, all narrow:

- **InfoSec policy** — how each Art. 21(2) area is addressed. Ten areas; the
  inventory has `security_measures` codes per activity, which is a list of
  controls, not a policy about applying them. The gap between them is the
  insert.
- **BCP** — recovery objectives, roles, escalation, testing cadence. None of it
  is in the data model.
- **Incident response plan** — detection, containment, recovery, review steps.

Every insert passes `regulations=["NIS2"]` to `retrieve()` (D-70). This is the
first real use of that filter, and the reason it was built: the diagnostic
showed that a NIS2 question phrased in plain language returns EU AI Act or GDPR
chunks, because the AI Act holds 39% of the collection.

---

## What the inventory is missing

S24 models processing activities and the vendors touching them. NIS2 is about
**the entity and its network and information systems**, which overlaps but is
not the same object.

Not in the data model today:
- entity classification: essential vs important (Annex I/II, size thresholds)
- whether the client is in scope at all, and on what basis
- national registration status (`nis2_11` asks; nothing records it)
- recovery objectives per system (RTO/RPO) — a BCP without them is prose
- criticality is on `systems` (S24) but is not a continuity judgement
- incident history — nothing records that an incident happened

**Open: how much of this does S29 add, and how much does it ask for at
generation time?** The S28 answer was to add the field (`data_source`) rather
than accept a placeholder. The same logic points at adding entity
classification and RTO/RPO. That is a part-1 the way `data_source` was.

---

## Out of scope

- `nis2_01` risk assessment. See above.
- Incident *recording* — a register of incidents that occurred. That is S44
  (breach notification workflow), and this sprint writes the procedure that
  workflow follows.
- Supply chain security (`nis2_05`) — operational, and the vendor risk register
  in the backlog is where it lands.
- Determining whether the client is in NIS2 scope. Applicability is the
  existing engine's job; if it cannot answer, that is a finding, not this
  sprint.

---

## Open — needs a decision

1. **Does `nis2_12` become a document obligation?** It makes `infosec_policy`
   real rather than a document nothing requires.
2. **How much entity data does part 1 add?** Classification and RTO/RPO at
   minimum, or accept generation-time questions.
3. **Four documents or three?** The catalogue supports four. Four Tier 2
   documents in one sprint is large, and `incident_response_plan` could fold
   into the breach procedure — though they are different documents for
   different moments, and merging them repeats the mistake this sprint exists
   to fix.
