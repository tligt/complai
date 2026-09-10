# S30 — DPIA and risk assessment — scope lock

**Tier 3.** The first document RECOSA cannot produce from what it already
knows, because a DPIA is not a description of processing — it is a judgement
about it.

---

## 1. One engine, two catalogues, two acceptance rules

`nis2_01` became operational in S29A because a risk assessment is an
assessment, not a template. A DPIA is the same shape. Building both separately
would be the divergence pattern.

**What generalises — the register and the workflow.** Identify a risk, state
likelihood and severity, record existing controls, decide whether the residual
risk is acceptable, record who decided and when. Identical for both.

**What does not — what a risk IS, and what makes it acceptable.**

| | DPIA (Art. 35) | NIS2 risk assessment (Art. 21(2)(a)) |
|---|---|---|
| risk to | **rights and freedoms of natural persons** | **network and information systems** |
| typical | intrusive profiling, unlawful disclosure, discrimination | outage, ransomware, supply-chain compromise |
| if unacceptable | **Art. 36 prior consultation with the supervisory authority** | a management decision, and nothing else |

Those are different axes. A cloud outage is a serious NIS2 risk and barely a
DPIA risk; a lawful but intrusive profiling operation is a serious DPIA risk
with no NIS2 dimension.

**The failure to guard against** is a generic "risk" object that serves both by
being vague about which harm it measures. That is how a DPIA ends up reading
like an IT risk register — the most common way DPIAs are done badly, and the
thing an authority spots immediately.

So: shared engine, separate catalogues, separate acceptance rules, and the
document says which harm it is about in its first line.

---

## 2. Trigger detection is IN SCOPE, and is the more valuable half

Art. 35(1) requires a DPIA where processing is likely to result in a high risk.
Art. 35(3) lists three cases; the supervisory authorities publish their own
lists under Art. 35(4).

**RECOSA already holds most of what decides this.** Special categories,
criminal data, data subject categories, automated decision-making (once S51
lands), systematic monitoring, and scale.

Telling a client **which activities need a DPIA** is worth more than producing
one, because it is the part they get wrong — usually by not realising the
question applies to them at all.

Same pattern as `rights_in_play()` in S28: an executable rule over the
inventory, not prose in a template. And the same conservatism — where RECOSA
cannot tell, it says so rather than concluding "not required".

*Rejected:* a questionnaire. Every answer it would ask for is already in the
inventory, and asking again invites two answers to one question.

---

## 3. What is reusable from `gap_assessment.py`: less than expected

It answers "does this document satisfy this obligation". A DPIA answers "what
could go wrong for people, how likely, how bad, what are we doing". Different
objects, and the machinery does not transfer.

It also imports Streamlit throughout — `st.progress`, `st.warning` — so it is
not a pure module. **The DPIA engine is a pure module (D-61)**: the logic
deciding whether a client needs a DPIA and whether a residual risk is
acceptable is a compliance verdict, which is exactly the class that belongs
where it can be tested.

Genuinely reusable: `extract_text_from_storage`, and the PDF machinery.

---

## 4. Schema

`risk_assessments` — one per (client, subject, regulation). A DPIA is *about*
something: an activity, a set of activities, a system. Not one per client.

`risk_items` — the register itself:
- `regulation` — GDPR or NIS2, because it decides which catalogue and which
  acceptance rule applies
- `catalogue_code` — from the risk vocabulary, or `other` with a description
- `likelihood`, `severity` — a fixed scale, coded not free text, because a
  register that cannot be sorted by seriousness is a list
- `existing_controls`, `additional_measures` — client prose
- `residual_likelihood`, `residual_severity`
- `accepted_by`, `accepted_at` — **a name and a date**, same rule as S29's
  acknowledgements: an unattributed risk acceptance is not a decision
- `consultation_required` — derived, not entered

Two risk vocabularies in `reference_values`, seeded from Python like every
other: `dpia_risk` and `nis2_risk`.

---

## 5. Art. 36 is the point of the DPIA

Where residual risk remains high after mitigation, Art. 36(1) requires prior
consultation with the supervisory authority **before** processing begins.

This is a legal consequence with a procedure attached, and it is the reason a
DPIA is not paperwork. The engine derives it — never the client — and the
document states it plainly:

> Processing must not begin until the supervisory authority has been
> consulted.

Most DPIA templates bury this. A client who mitigates to "medium" and files the
document has done the work; one who leaves a high residual risk and starts
processing has broken Art. 36 and does not know it.

---

## 6. The document

**Target the EDPB model template** section for section, per the S30 note
already in the log. An auditor recognising the shape of the document is worth
more than a better-organised original.

Art. 35(7) content: a systematic description of the processing and its
purposes; an assessment of necessity and proportionality; an assessment of the
risks; and the measures envisaged to address them.

The first two come from the inventory — this is the RoPA content again, in a
different arrangement. The second two come from the register above.

**The DPO's advice must be recorded** (Art. 35(2)) where one is appointed, and
the document says whether it was sought.

---

## Out of scope

- Automated decision-making detail. No field; deferred with S51, and the
  trigger rule reports "cannot tell" rather than "not required".
- Consulting data subjects (Art. 35(9)) — "where appropriate", and a judgement
  RECOSA should not make.
- A risk *scoring* model. Likelihood times severity produces a number that
  looks objective and is not. The register records both dimensions and lets a
  person decide.

---

## Open — needs a decision

1. **Does S30 cover the NIS2 risk assessment too, or only the DPIA?** The
   engine serves both, but two catalogues and two documents in one sprint is
   large. Doing the DPIA alone leaves `nis2_01` unaddressed for longer, but
   the engine is built either way.
2. **Who authors the risk catalogues?** Roughly 15–25 entries each, and they
   are the substance of the sprint. RECOSA-authored and reviewed, or drawn
   from a published source such as the CNIL PIA knowledge base?
3. **Does an unmitigated high residual risk BLOCK the document?** A DPIA
   recording an unacceptable risk is a valid and important DPIA — it is what
   triggers Art. 36. But generating it silently, with no prompt, would let a
   client file it and start processing.
