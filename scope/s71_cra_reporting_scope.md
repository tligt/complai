# S71 — CRA reporting on the incident clock — scope

**Draft, 10 Nov 2026 (D-158). Not locked:** the open questions at the end
need an answer first.

The full CRA (product inventory, Annex I requirements, conformity, SBOM)
applies from 11 Dec 2027 and stays a later sprint. **One part is already in
force:** since 11 Sept 2026 a manufacturer must report actively exploited
vulnerabilities and severe incidents through ENISA's Single Reporting
Platform (SRP). The S53 incident clock already does this for GDPR and NIS2.
CRA Art. 14 is one more track with the same shape.

---

## The obligation

Sources read 10 Nov 2026: ENISA's launch notice (11 Sept), the SRP FAQ
(updated 15 Oct) and the Commission's CRA reporting page. **The EUR-Lex text
did not load.** The Art. 14 details below come from the Regulation as known;
check them against the OJ text (Reg. (EU) 2024/2847) before the build.

| | Actively exploited vulnerability (Art. 14(1)–(2)) | Severe incident (Art. 14(3)–(5)) |
|---|---|---|
| trigger | reliable evidence that someone exploited it without the owner's permission | affects (or can affect) the product's ability to protect data or functions, or let malicious code into the product or a user's systems |
| early warning | 24 h after becoming aware; Member States where the product is available | 24 h; plus whether it looks unlawful or malicious |
| notification | 72 h: the product, the general nature of the exploit and the vulnerability, measures taken, measures users can take, how sensitive the information is | 72 h: nature of the incident, initial assessment, measures taken, measures users can take, sensitivity |
| intermediate | when the CSIRT asks | when the CSIRT asks |
| final report | **14 days after a fix or mitigation is available**: severity and impact, the malicious actor where known, the security update | **1 month after the 72 h notification**: severity and impact, type of threat or root cause, mitigation applied and ongoing |
| users | Art. 14(8): inform the users affected (all users where appropriate) of the issue and of what they can do, in a structured, machine-readable form where that fits | same |

**Recipient.** The CSIRT designated as coordinator in the Member State of the
**main establishment**: where decisions on the products' cybersecurity are
mostly taken. ENISA receives the report at the same time. A report sent to
the wrong CSIRT may be invalidated (FAQ 8).

**Channel.** The SRP only: https://portal.cra-srp.enisa.europa.eu.
- Submitted by an "Assigned Representative" with their own EU Login account
  and MFA. One primary and up to 20 secondary per manufacturer; the CSIRT
  verifies the primary in parallel.
- **No API** in this release (FAQ 15).
- **English only** (FAQ 24).
- The portal's 72 h counter is set 48 h after the early warning, so it can
  read overdue early. The legal deadline is still 72 h from awareness (FAQ 26).

**Who.** Manufacturers of products with digital elements, including products
placed on the market before Dec 2027 (FAQ 12). Nothing to report
retrospectively for anything known before 11 Sept 2026 (FAQ 13).
Open-source stewards from 11 Dec 2027.

## Not the same as NIS2

NIS2 Art. 23 is about the **entity's service**. CRA Art. 14 is about the
**product it sells**.
- A ransomware attack on a SaaS company's own systems is NIS2.
- An exploited flaw in the router firmware it ships is CRA.
- An attack through the vendor's update server can be both.

Both can run on one incident, each with its own 24 h clock, recipient and
portal. **Neither replaces the other** unless a Member State's NIS2 transposition
says so (open question 3).

---

## What gets built

### 1. The client: is it a manufacturer?

- Add `clients.cra_manufacturer boolean` (NULL = not answered, as with
  `nis2_in_scope`).
- Add `cra_scope_note text`.
- Ask it on the Obligations page next to the NIS2 scope, with the same
  warning when "no" has no reason.
- Add `cra_applies(client)` in `incident_rules.py`, the same as
  `nis2_applies`. Unset falls back to `"CRA" in regulations`.

### 2. The incident: the CRA assessment

New columns on `incidents`:

| column | meaning |
|---|---|
| `cra_type` | `vulnerability` / `severe_incident` / `none`; NULL = not assessed |
| `cra_product` | the product(s) concerned, free text (no product inventory yet) |
| `cra_member_states` | where the product is made available (early warning) |
| `cra_fix_available_at` | when a fix or mitigation became available; dates the vulnerability's final report |
| `cra_intermediate_due` | set when the CSIRT asks, as `intermediate_due` is for NIS2 |

The incident form wording changes from "incident" to "incident or exploited
vulnerability". A CVE someone is exploiting in the client's product is
logged here too.

### 3. The clock: new kinds in `incident_rules.py`

| kind | required when | due |
|---|---|---|
| `cra_early_warning` | cra_type set (not `none`) | discovered + 24 h |
| `cra_notification` | same | discovered + 72 h |
| `cra_intermediate` | `cra_intermediate_due` set | that date |
| `cra_final` | same | vulnerability: fix + 14 days, undated ("14 days after a fix is available") until the fix is recorded. Severe incident: `_add_month(notification sent)` |
| `cra_users` | same | without undue delay |

- When the client is not a manufacturer: NOT_REQUIRED.
- When `cra_type` is NULL and the client is or may be a manufacturer:
  TO_DECIDE. The clock still runs from discovery, as for NIS2.
- `describe_left` gets the two undated final-report texts.
- Reminders, the action plan (`findings`), Home and the incident file all
  follow without changes.
- `AUTHORITY_OF` maps the four reporting kinds to `"cra"`.

### 4. Where to send: `authorities()["cra"]`

- **Name:** the coordinator CSIRT for the client's jurisdiction. New
  `cra_csirt_*` fields on the jurisdiction, because it is not always the
  NIS2 CSIRT (open question 2).
- **Submit:** the SRP URL.
- **Note:** one line on EU Login with MFA and the Assigned Representative
  role, plus the 48 h counter caveat.
- **`verified`:** false until each country's coordinator is checked.

### 5. Drafts: always in English

- Templates for early warning, notification and final report, one for each
  of the two types, with the Art. 14 items above.
- Unknown items stay visible as `[to complete]`. No LLM, as D-117.
- **In English whatever the interface language**, because the SRP takes
  English only. The French interface explains that in one line.
- The users notice (Art. 14(8)) has its own draft, in the interface language.

### 6. The team

`alert_on = "significant"` also covers a CRA type, so the incident team is
alerted for "significant (NIS2) or reportable (CRA)" incidents. The label
changes to say so.

## Out of scope

- Product inventory, Annex I, conformity, SBOM, the vulnerability-handling
  process: all for the CRA sprint (Dec 2027 obligations).
- Voluntary reporting (Art. 15): not in the SRP yet (FAQ 6, 27).
- An SRP integration: there is no API.
- Open-source stewards: from Dec 2027; the same track with a different
  `cra_applies` answer.
- A CRA obligation in `obligations.py`: adding a regulation changes scoring
  and the register. That belongs with the CRA sprint unless open question 4
  says otherwise.

## Size

- One migration (2 client columns, 5 incident columns, jurisdiction
  columns).
- About 250 lines in `incident_rules.py` (drafts are most of it).
- The assessment block on the incidents page and the scope question on the
  Obligations page.
- Tests for each `deadlines()` branch.

**One working day.**

## Open questions

1. **Does any current client make products with digital elements?** If none
   does, this can wait for the first one. If one does, it is overdue: the
   duty has applied since 11 Sept.
2. **The coordinator CSIRT per country:** BE (CCB?), FR (CERT-FR?), NL, LU.
   Check each on the SRP's own list before marking it verified.
3. **NIS2 overlap:** does BE or FR let one report cover both? Read the
   Commission guidance §9.1 and its FAQ §5.
4. **Register:** add one operational obligation `cra_01` (Art. 14 reporting)
   now, or keep the CRA out of the catalogue until the full sprint?
5. **Priority:** before S60, given the duty is already in force?
