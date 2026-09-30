# S45 — draft profile questions, for review

**Status: APPROVED and shipped 30 Sept 2026 (D-111).** Approved as drafted,
with two additions from the review: help notes under questions that need
clarifying (notably the country-specific age of a "child"), and questions
grouped by regulation with only the client's selected regulations asked.
`obligations.py` is now the source of truth; this file is the review record.

Written 30 Sept 2026 as S45's remaining build item: `PROFILE_QUESTIONS` grows
from 9 toward the ~32-question calibration (D-107). Per D-108, question wording
and scoring are compliance content — **reviewed before shipping, not after.**

## What changes when these go live

22 operational obligations have no profile question today. `run_gap_assessment`
currently judges each of them by having Mistral read the first 4,000
characters of *all* the client's documents combined, looking for evidence of
things like "MFA is used" or "backups are restore-tested" — which policy
documents rarely state, so these mostly come back `missing` on weak grounds.

With a question linked, the obligation is scored **from the client's answer
only**: no document reading, no Mistral call. More honest and cheaper, but it
takes the client's word for it. That is already how the existing 9 questions
work.

## How to review

For each question, check: the wording (clear to an SME owner, not a lawyer?),
the options, and which answers count as **compliant**, **partial**, or
**not applicable** (N/A: the obligation doesn't apply, so it is excluded from
the score). Any answer not listed as one of those three scores `missing`.

Points I am least sure of are marked **⚠ Check**.

Totals: 9 existing + 22 new = **31**.

---

## GDPR (11)

### `processors_dpa` → gdpr_05, Art. 28
**Do you have a data processing agreement with every service provider that handles personal data on your behalf (e.g. hosting, payroll, CRM, email marketing)?**
- Yes — with all of them → **compliant**
- With some of them → **partial**
- No → missing
- We use no such service providers → **compliant, N/A**

⚠ Check: almost every business uses at least one processor (email, cloud
storage). The N/A option may be chosen wrongly; consider dropping it.

### `dsr_procedure` → gdpr_07, Art. 15–22
**If someone asks to see, correct or delete their personal data, is there a written procedure for handling the request within the one-month legal deadline?**
- Yes — a written procedure → **compliant**
- We handle requests case by case, without a written procedure → **partial**
- No → missing

### `intl_transfers` → gdpr_11, Art. 44–49
**Is any personal data you hold transferred outside the EEA, or accessible from outside it (e.g. through US-based cloud or software providers)?**
- No — all data stays in the EEA → **compliant, N/A**
- Yes — with safeguards in place (adequacy decision, standard contractual clauses or similar) → **compliant**
- Yes — safeguards not checked → missing
- Not sure → **partial**

⚠ Check: "Not sure" scored partial follows the existing `ai_annexiii`
precedent. Many SMEs will pick "No" while using US SaaS tools; the example
in the question is there to prevent that.

### `privacy_by_design` → gdpr_12, Art. 25
**Before a new tool, system or process that uses personal data goes live, do you consider data protection as a set step?**
- Yes — a documented step (e.g. a checklist or review) → **compliant**
- Sometimes, informally → **partial**
- No → missing

### `data_minimisation` → gdpr_14, Art. 5(1)(c)
**Do you limit the personal data you collect to what you actually need, and delete it once you no longer need it?**
- Yes — with defined retention periods that are applied → **compliant**
- Partly → **partial**
- No → missing

⚠ Check: Art. 5(1)(c) is minimisation; deletion is storage limitation,
5(1)(e). Bundled because an SME answers them together; split if you'd
rather keep the article mapping exact.

### `notice_at_collection` → gdpr_15, Art. 13
**Where you collect personal data (web forms, sign-ups, contracts, job applications), are people told at that moment how it will be used, with a link to your privacy notice?**
- Yes — at every collection point → **compliant**
- At some collection points → **partial**
- No → missing

### `special_category` → gdpr_16, Art. 9
**Do you process sensitive data: health (including staff sick-leave or medical information), biometrics, religion, political opinions, trade-union membership, sexual orientation, or ethnic origin?**
- No → **compliant, N/A**
- Yes — with a documented legal basis and extra safeguards → **compliant**
- Yes — not specifically assessed → missing

⚠ Check: sick-leave data is named because nearly every employer holds it and
few think of it as health data.

### `joint_controllers` → gdpr_17, Art. 26
**Do you decide together with another organisation why and how some personal data is used (e.g. a joint marketing campaign, a shared customer platform)?**
- No → **compliant, N/A**
- Yes — with a written joint-controller arrangement → **compliant**
- Yes — no written arrangement → missing
- Not sure → **partial**

### `legitimate_interest` → gdpr_18, Art. 6(1)(f)
**Do you rely on "legitimate interest" as the legal basis for any processing (e.g. marketing to existing customers, CCTV, fraud prevention)?**
- No → **compliant, N/A**
- Yes — with a documented legitimate interest assessment → **compliant**
- Yes — not documented → missing
- Not sure → **partial**

### `children_data` → gdpr_19, Art. 8
**Do you offer online services directly to children, or knowingly collect personal data from children?**
- No → **compliant, N/A**
- Yes — with age checks and parental consent where required → **compliant**
- Yes — without specific safeguards → missing

⚠ Check: the Art. 8 age threshold is national (13 in Belgium, 15 in
France). The question avoids naming an age for that reason.

### `security_measures` → gdpr_20, Art. 32
**Are the security measures protecting personal data (access rights, encryption, backups and so on) documented?**
- Yes — documented → **compliant**
- In place, but not documented → **partial**
- No → missing

---

## NIS2 (8)

Mapped to the Art. 21(2) measure each obligation covers. The public quiz
(`quiz/quiz_app.py`) asks about the same categories in marketing language;
these are the in-product versions.

### `supplier_security` → nis2_05, Art. 21(2)(d)
**Do you assess the security of the suppliers and service providers your business depends on, and set security requirements in their contracts?**
- Yes — assessed and in contracts → **compliant**
- Informally, or for some suppliers only → **partial**
- No → missing

### `access_mfa` → nis2_06, Art. 21(2)(i) and (j)
**Is access to your systems limited to what each person needs, with multi-factor authentication for remote and administrator access?**
- Yes — role-based access and MFA → **compliant**
- Partly (e.g. MFA on some systems only) → **partial**
- No → missing

### `encryption` → nis2_07, Art. 21(2)(h)
**Is sensitive data encrypted both when stored and when sent over networks?**
- Yes → **compliant**
- Partly → **partial**
- No → missing
- Not sure → missing

⚠ Check: "Not sure" scores missing here, unlike the GDPR questions. For a
technical control, not knowing usually means it isn't managed. Harmonise
either way if you prefer.

### `patching` → nis2_08, Art. 21(2)(e)
**Do you have a process for tracking security updates and applying patches within a set timeframe?**
- Yes — a documented process with timeframes → **compliant**
- Updates are applied, but informally → **partial**
- No → missing

### `backups_tested` → nis2_10, Art. 21(2)(c)
**Are backups made regularly, stored separately from your main systems, and tested by actually restoring from them?**
- Yes — including regular restore tests → **compliant**
- Backups are made, but restores are not tested → **partial**
- No regular backups → missing

### `management_approval` → nis2_12, Art. 20
**Has your management body (directors) formally approved your cybersecurity measures, and do its members follow cybersecurity training?**
- Yes — approved, and management trained → **compliant**
- Approved, but no management training → **partial**
- No → missing

⚠ Check: Art. 20 requires approval, oversight *and* training of management
members. Partial for approval-only is a judgement call.

### `security_monitoring` → nis2_13, Art. 21(2)(b)
**Do you monitor your network and systems for suspicious activity (e.g. firewall or antivirus alerts, or a managed security provider), with someone reviewing the alerts?**
- Yes — alerts are reviewed → **compliant**
- Tools are in place, but alerts are not routinely reviewed → **partial**
- No → missing

⚠ Check: mapped to (b) incident handling (detection), since Art. 21(2) has no
standalone "monitoring" measure. Confirm that is the mapping `nis2_13` intends.

### `audit_logs` → nis2_15, Art. 21(2)(b) and (f)
**Do your key systems keep logs of who accessed or changed what, kept long enough to investigate an incident?**
- Yes → **compliant**
- Partly → **partial**
- No → missing

---

## EU AI Act (3)

### `ai_prohibited` → ai_02, Art. 5
**Do you use AI for any of the following: manipulative or deceptive techniques, exploiting people's vulnerabilities, social scoring, emotion recognition at work or in education, untargeted scraping of facial images, or categorising people by sensitive traits from biometric data?**
- No → **compliant**
- Not sure → **partial**
- Yes → missing

⚠ Check: a "Yes" here is a prohibited practice, not a gap to close. It may
deserve its own urgent message rather than the standard "Implement: …"
recommendation. The list paraphrases Art. 5(1). Verify against the text
before shipping.

### `ai_roles` → ai_03, Art. 3(3), 3(4), 25
**For each AI system you use or offer, have you determined whether you are its provider or its deployer under the AI Act?**
- We do not use AI systems → **compliant, N/A**
- Yes — documented for each system → **compliant**
- Partly → **partial**
- No → missing

⚠ Check: overlaps `ai_usage`'s "We do not use AI systems". A client could
contradict themselves across the two. Acceptable for now, or derive N/A from
`ai_usage` instead.

### `ai_intimate_imagery` → ai_10, Art. 5 (as amended)
**Can any AI system you provide or deploy generate sexual imagery of real people without their consent, or child sexual abuse material?**
- We do not provide or deploy image- or video-generating AI → **compliant, N/A**
- No — safeguards prevent it → **compliant**
- Not sure → missing
- Yes → missing

⚠ Check: `ai_10` applies from 2 December 2026 (not yet in force), so until
then it scores `not_assessed` regardless of the answer. The open question in
section 7 about verifying this date against the OJ still stands.

---

## Open for the reviewer

1. **"Not sure" handling is inconsistent on purpose**: partial for legal
   judgements (GDPR, AI Act), missing for technical controls and ai_10.
   Keep, or pick one rule.
2. **Question order in the product**: currently dictionary order. Suggest
   grouping by regulation, as here.
3. **The 32 target**: this reaches 31. No obligation is left without a
   question, so a 32nd would be padding.
