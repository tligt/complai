# S28 — Privacy Policy — scope lock

**Tier 1, not Tier 2.** The roadmap said "first LLM inserts". It does not need
them.

Art. 13 and 14 prescribe the content: identity and contact details, DPO,
purposes, legal bases, legitimate interests where relied on, recipients,
third-country transfers and safeguards, retention, data subject rights,
withdrawal, complaint route, whether provision is statutory or contractual, and
automated decision-making.

**Every one of those is already structured data** after S26 and S26C. A privacy
policy is the controller register rendered for a public audience — same source,
different reader.

This is also what the evidence says. The privacy policy went from 30–40% to 80%
review scores *by constraining toward fixed structure*. The obvious reading is
that constraint produced the gain, and the remaining 20% is more constraint
rather than better prose.

**Consequence:** the first genuine LLM inserts move to S29 (InfoSec, BCP),
where content actually varies by organisation rather than by data.

---

## Part 1 — `data_source` (blocking)

**Nothing in the inventory records where personal data came from.** Fifteen
vocabularies, none of them this.

Without it every generated policy silently discharges Art. 13 only. That is
wrong for most SMEs: an employee's emergency contact, a supplier's accounts
contact, a referred prospect and a bought prospect list are all Art. 14, and
almost every client has at least one.

Art. 14 differs in two ways the template must handle. It requires **the
categories of data** — Art. 13 does not, because the person already knows what
they handed over — and **the source**, including whether it was publicly
accessible.

**Vocabulary** (`reference_values`, `value_type = 'data_source'`), append-only:

| code | meaning |
|---|---|
| `data_subject` | Given to us by the person. Art. 13 path. |
| `client_controller` | Supplied by a controller we process for |
| `employer_or_colleague` | Emergency contacts, referees, staff of a customer |
| `public_register` | Company register, professional roll |
| `publicly_available` | Website, public social profile — Art. 14(2)(f) asks this specifically |
| `third_party_referral` | Passed on by an existing contact |
| `data_broker` | Purchased or licensed list |
| `credit_reference` | Credit or background checking agency |
| `another_group_entity` | Another company in the same group |
| `other` | Describe |

**Schema:** `data_source_codes TEXT[]` on `processing_activities`. An array,
not a scalar — an HR record holds data from the employee *and* from their
referees, and both have to be disclosable.

**Form:** one multiselect, same pattern as `data_categories`.

Roughly a third of S26C's size.

---

## Part 2 — the document

**Controller activities only.** A privacy policy is a controller's disclosure.
Processor-role activities belong to the customer's own policy, and listing them
here would tell a data subject that RECOSA's client decides purposes they do
not decide. Filter `controller_role = 'controller'` and joint controller.

**Sections**, all rendered from structured data:

1. Who we are — reuses the S26 identity block
2. What we do with your data — block renderer, one row per purpose group:
   purpose, legal basis, data categories, retention
3. Where your data came from — **conditional**. Renders only when any activity
   carries a `data_source` other than `data_subject`. Art. 14 content.
4. Who we share it with — recipients from `activity_counterparties`, by
   category, with the joint-controller wording from the Cookie Policy
5. Transfers outside the EEA — from `processing_country` and
   `transfer_mechanism`; the whole section suppressed when there are none
6. How long we keep it — S26C structured retention, both phases
7. Your rights — **see the rule below**
8. Complaints — supervisory authority per establishment, the S25 rule
9. Changes to this policy — version and effective date from the S27 register

## The rights section is conditional, and most policies get this wrong

Data subject rights are **not universal**. They depend on the legal basis:

| Right | Applies when |
|---|---|
| Withdraw consent (Art. 7(3)) | consent is a basis for at least one activity |
| Object (Art. 21) | legitimate interests or public task |
| Portability (Art. 20) | consent or contract **and** processing is automated |
| Erasure (Art. 17) | qualified — not available against a legal obligation |
| Restriction, access, rectification | always |

A template listing every right unconditionally tells a data subject they can
demand portability of records held under a statutory retention duty. That is a
promise the client cannot keep, in a published document.

**Encoded as executable rules over the activity set**, per the constraint that
rules are checks and not prose — the same pattern that caught three Microsoft
365 activities in S24.

---

## Out of scope

- **AI Transparency Notice.** Art. 50 duties attach to specific AI systems and
  interactions, not to the organisation. Without S51's inventory there is
  nothing structured to describe, and generating it from guesses is the failure
  this sprint is avoiding elsewhere. **Moves to S28A**, which already carries
  the AI deployer pack and can wait for S51.
- **Automated decision-making detail** (Art. 13(2)(f), Art. 22). No field
  records it. A client flag with a free-text explanation would be a placeholder
  by another name. Deferred with S51.
- Per-purpose cookie detail — the Cookie Policy has it; cross-reference.
- Children's data (Art. 8) — no field, and it changes the tone of the whole
  document. Own decision when a client needs it.

---

## Open — needs a decision before building

**1. Purpose grouping.** A client with fifteen activities produces fifteen
rows, which is a register rather than a policy. Group by legal basis? By data
subject category? Or list all and accept the length? *Leaning: group by data
subject category — "if you are a customer / an employee / a supplier contact",
which is how a reader arrives at the document.*

**2. Does section 3 name sources per activity or as a flat list?** Per activity
is precise and verbose; a flat list is readable and slightly less informative.
Art. 14(2)(f) says "from which source the personal data originate", which
suggests per activity. *Leaning: per activity, inside the section 2 block.*

**3. Publication.** The Cookie Policy has the same question and S27 records
`published_at`. Does this sprint do anything with it, or is publication still
the client's job elsewhere?
