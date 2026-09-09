# RECOSA — Sprint Log and Decision Register

**Maintained by:** Fabrice Fonder
**Last updated:** 4 September 2026 (S27 closed)
**Purpose:** the standing record of what was built, why, and what was decided against.

> **This file was not in version control until 4 September 2026.** It was
> maintained as a local copy, and D-12 through D-42 were lost as a result —
> written during the S25, S26 and S26A sessions and never committed. Two
> surviving working documents allowed D-42, D-43 and D-44 to be recovered; the
> rest are gone, and the gap is recorded in section 4 rather than papered over.
>
> **Commit this file.** An uncommitted decision register is the same failure it
> exists to prevent.

---

## How to use this document

This exists because reasoning agreed in conversation and written nowhere gets
reversed by accident six months later. Three rules keep it useful:

1. **Append at sprint close, not at sprint start.** Scope changes during a
   sprint; recording the plan produces a document that disagrees with the code.
2. **Record the decision and the rejected alternative.** "We use Postgres for
   reference data" is worth little. "We use Postgres rather than a Python
   constant *because* the S41 scanner needs to query it" is what stops a future
   reader undoing it.
3. **Decisions live in section 4, not in the sprint entries.** Sprints are
   chronological and get stale; decisions are current until superseded.

### Confidence in this record

| Sprints | Source | Reliability |
|---|---|---|
| S25–S27 | Written same-session | High — decisions recorded with their rejected alternatives |
| S20–S24 | Detailed working notes | High — file names, error codes, specific fixes |
| S12–S19 | Session summaries | Good — objectives and key decisions, fewer specifics |
| S1–S11 | Early session summaries | Partial — objectives reliable, implementation detail thin |

S11 in particular is uncertain: the roadmap at the time listed it as data
extraction from uploaded documents to pre-fill generation, but that feature was
explicitly deferred in the same discussion. **Worth confirming against the
repository before relying on it.**

### Before deleting old conversations

The assistant's memory of this project is *derived from* those conversations.
Deleting them eventually removes the derived entries too. So: verify this
document is complete first, delete second. Anything not written here is lost.

---

## 1. What RECOSA is

An EU-native regulatory compliance platform for SMEs in Belgium and France,
covering GDPR, NIS2, ePrivacy and the EU AI Act. It delivers AI-powered Q&A
grounded in regulatory text, document generation, gap assessment, website
auditing, and regulatory monitoring.

Solo-founded, bootstrapped, pre-beta. The beta gate is **S32** (GDPR data
deletion + session security hardening).

**Positioning:** the intersection of three regulations converging on SMEs at
once — a gap no existing tool addressed at the time of the original analysis.

**Domains:** recosa.eu (primary, marketing site), recosa.ai (registered).
Contact: hello@recosa.ai.

### Stack

| Layer | Choice | Note |
|---|---|---|
| Client app | Streamlit on Streamlit Cloud | `app.py` + `pages/` |
| Admin back-office | Streamlit, same repo | `admin_app.py` + `pages_admin/` |
| Database | Supabase (Postgres, PostgREST, Auth, Storage, Edge Functions) | |
| Vector store | Qdrant Cloud, eu-central-1 AWS | collection `regulations` |
| LLM | Mistral via **raw REST** | `mistral-embed`, `mistral-large-latest`; no SDK in repo |
| Email | Brevo | transactional, content-free only |
| Marketing site | Framer | |
| Cron | GitHub Actions | monitoring jobs |
| Analytics | Umami | Google Analytics rejected — inconsistent with EU-sovereign positioning |

**EU sovereignty is a product constraint, not a preference.** No CLOUD Act
exposure anywhere in the stack. It is the differentiator against US-hosted
competitors and it constrains vendor choice throughout.

---

## 2. Sprint log

### Phase 1 — Foundation (S1–S9)

**S1 — Semantic embeddings.** Replaced the TF-IDF prototype with
`mistral-embed`. Called over raw HTTP because the `mistralai` library failed to
import in the original environment; that workaround became permanent and there
is still no Mistral SDK in the repo.

**S2 — Persistent vector storage.** Qdrant Cloud, with payload indexes on
`language`, `country`, `doc_type` and `parent_regulation`.

**S3 — Regulatory ingestion.** GDPR, NIS2 and the EU AI Act in EN/FR/NL.
EUR-Lex blocks automated fetching (HTTP 202 with empty body) from both
Streamlit Cloud and Colab IP ranges, so **PDFs must be downloaded manually and
uploaded to Colab**. This is still true and still the ingestion path.

**S4 — Admin upload interface.** Add/edit/delete tabs, HTML ingestion via
BeautifulSoup, country and language selectors.

**S5 — Per-client data model.** Supabase auth, `clients` table, chat history.

**S6 — Website audit.** Crawler, checklist, PDF report, Brevo delivery.

**S7 — Knowledge base quality.** Article-level chunking replacing fixed-token
chunks, so "Article 32" retrieves cleanly. Added `article`, `article_title`,
`enforcement_date`, `status` and `provision_scope` to chunk metadata. Full
re-ingestion. Detection patterns: `Article N` (EN), `Article Ner` (FR),
`Artikel N` (NL). Articles over ~600 tokens split at paragraph boundaries,
never mid-sentence. Recitals chunked separately.

**S8 — Document generation.** Six types: privacy policy, cookie policy, DPA,
RoPA, incident response, AI transparency notice. DOCX/PDF/ODT output.

**S9 — File storage.** Supabase Storage, download and email from history.

### Phase 2 — Compliance engine (S10–S15)

**S10 — Gap assessment engine.** `gap_assessments` table with a `gaps` JSONB
field, per-regulation scores, PDF report.

**S11 — Uncertain.** See the confidence note above. Verify against the repo.

**S12 — Knowledge base live updates.** Approved regulatory alerts ingested into
Qdrant. Three-tier strategy: the summary is always embedded, full article text
attempted with graceful fallback.

**S13 — Client compliance dashboard.** Per-regulation status, document
checklist driven by the `gaps` JSONB, activity summary.

**S14 — Admin dashboard.** Client list, document/gap/chat counts, abuse
flagging at 20+ documents.

**S15 — Token tracking.** Middleware across every Mistral call site, logging to
`usage_logs` with cost calculation. Client vs internal usage split in the admin
BO.

### Phase 3 — Market-facing (S16–S20)

**S16 — Marketing website.** Framer, static. Wix Vibe evaluated and abandoned
(no edit control, no AI credits).

**S17 — Unified monitoring.** Regulatory monitor reading sources from a
`monitoring_sources` table; marketing monitor on Mistral's Agents API with
Premium Search (persistent agent `ag_019efe92f08e71a78d70f0f8b9230d29`);
LinkedIn draft generation; `monitor_runs` logging; admin BO page with four tabs.

*Three approaches failed first:* NewsAPI blocked server-side, Google News RSS
blocked, Mistral Conversations API parsing unreliable. The persistent Agents
API agent was the fourth attempt and is what works.

**S18 — UI and navigation redesign.** RECOSA branding, standalone login, dark
blue `#003366` sidebar with teal `#14C7D5` accents, hero-centred chat input,
account menu, KB management moved from the client app to the admin BO.

**S19 — Dynamic site + compliance.** Supabase Edge Function serving the
Compliance Pulse feed; custom cookie consent banner (Axeptio rejected on cost);
`cookie_consents` audit table; Privacy Policy, Cookie Policy and Terms pages on
recosa.eu.

**S20 — Trust messaging + Compliance Pulse wiring.** Framer connected to the
Edge Function via the FramerSync/AnySync plugin rather than a native CMS
collection. Markdown stored in Postgres, converted to HTML at the Edge Function
layer using `marked`, rendered through a Rich Text element. A second AnySync
collection filtered on `articles_only=true` exists specifically to stop Framer
generating blank UUID-slug pages for every feed item, which was polluting the
sitemap. Monitoring page gained freshness gating (auto-disabling publish and
email for items older than 21 days, with manual override), manual item entry,
and URL validation with a `KNOWN_UNRELIABLE_DOMAINS` blocklist.

### Phase 4 — Beta preparation (S21–S24)

**S21 — Audit trail, cookie reopen, source citations.**
`audit_log` table with RLS scoped so clients see their own company and admins
see all; `log_audit_event()` writing through the service-role client to bypass
RLS; hooks in document generation, gap assessment and website audit.
`session_id` and `sources` columns on `chat_history`, per-session history panel,
citations persisted and re-rendered. CNIL-mandated persistent cookie reopen
button on the Framer site.

*Three failures diagnosed during this sprint, all the same shape:* the audit
helper was never actually added to `database.py` (silent failure); the `audits`
table had RLS enabled with **no policies at all**, blocking every insert with
error 42501; and `save_audit` used a locally-defined anon client carrying no
session, so the insert-then-select-back pattern failed RLS even after policies
were added. This is the origin of decision **D-06**.

**S22 — Feedback and support ticketing.**
`answer_feedback`, `message_threads`, `messages`, `support_tickets`. A generic
`message_threads` table was chosen over purpose-built ticket threading so the
S46 document workflow comments can reuse it. Content-free Brevo reply
notification, throttled to the 0→1 unread transition. Deep-link `?ticket=`
capture at the top of `app.py`.

**S23 — Obligation catalogue unification.**
New `obligations.py` at repo root as single source of truth. The codebase had
**three competing obligation-to-document mappings that disagreed** — only
`gdpr_01` and `gdpr_07` appeared in all three, so a document scored in one view
was judged against a different obligation set in another. A live bug had the
dashboard keying RoPA as `"rop"` while everything else used `"ropa"`, meaning a
generated RoPA could never match its checklist row.

Also closed the EU AI Act gap: the registry had **zero** AI Act obligations
while recosa.eu sold AI Act coverage as one of three core regulations. Registry
went 40 → 54 (20 GDPR, 15 NIS2, 5 ePrivacy, 14 EU AI Act).

*Note:* stored `gap_assessments` rows were scored under the old logic. Re-runs
will not match historical numbers, and scores move upward.

**S24 — Vendor and system inventory.**
Seven tables. Reference: `reference_values` (92 vocabulary terms across 14
types), `vendor_catalogue` (20 vendors), `vendor_catalogue_activities` (26
suggested activities), `vendor_domain_patterns` (empty until S41),
`catalogue_principles`. Client data: `systems`, `processing_activities`,
`activity_systems`.

Pulled forward out of the onboarding redesign so the same vendor inventory is
built once rather than three times across the Tier 1 documents — Cookie Policy
needs the vendor table, DPA the sub-processor list, RoPA the processing
activities, and all three are views of one inventory.

**S25 — Template engine + Cookie Policy.**
First Tier 1 template. Markdown bodies (D-11), block renderers for tabular
content, merge fields with visible `[[ TO COMPLETE ]]` placeholders rather than
blocking generation. Proved the engine end to end.

**S26 — RoPA (controller and processor).**
Two documents, not one: the CNIL advises separate registers, and Art. 30(1) and
30(2) prescribe different content — eight items against five. Retired the
ambiguous `ropa` doc_type for `ropa_controller` and `ropa_processor`, which is
the precedent D-55 later relied on.

**S26A — DPA (Art. 28 processor clauses).**
Standard Contractual Clauses from Commission Implementing Decision (EU)
2021/915, downloaded from EUR-Lex and patched mechanically rather than
transcribed (D-42). Annex II, Annex III and Schedule 1 built from the S24
inventory, scoped to activities where `controller_role = 'processor'`.
Closed 3 Sept 2026.

**S26C — Multilingual activity text + structured retention.**
Client free text (`name`, `purpose`) became per-language JSONB; retention prose
became `retention_value` + `retention_unit` + `retention_basis_code`, with a
separate archive phase (D-49). New `translate.py` drafts second-language
versions under human review. Prompted by a French DPA carrying English text in
Annex II.

**S27 — Document register.**
`client_documents` extended, not replaced. Generation writes a draft; the
client puts it in force with an effective date they supply (D-58). Version
numbers assigned at adoption so drafts leave no gaps (D-57). Supersession
chains, retention dates, legal hold, and an auditor-facing compliance record
page. Closed 4 Sept 2026.

---

## 3. Current roadmap

Numbering has changed four times. **This is authoritative; older notes are
not.** The shift from the table previously here: D-09 inserted the document
register as S27 and moved everything below it by one, putting the beta gate at
S33.

**Delivered:** S1–S24, S25, S26, S26A, S26C, S27.

| # | Sprint | Notes |
|---|---|---|
| ~~S28~~ | ~~Privacy Policy~~ | **Delivered 8 Sept. Tier 1, no LLM (D-71). AI Transparency Notice moved to S28A.** |
| S28A | AI deployer pack: AUP + Human Oversight + **AI Transparency Notice** | Notice moved here from S28 — Art. 50 attaches to systems, and S51 has the inventory |
| ~~S29~~ | ~~Obligation register + task register~~ | **Delivered 8 Sept.** D-77 to D-79. 7 derivations, 5 response kinds, derived-state task register |
| S29A | NIS2 pack: incident response + breach procedure + BCP | Tier 2, first real LLM inserts. No InfoSec policy — see scope |
| S30 | DPIA | Tier 3. Target the EDPB model template |
| S31 | Regulation-aware chunk allocation | **See sequencing note below** |
| S32 | Admin user management | |
| **S32A** | **Migration to European infrastructure** | **D-67. Precedes the gate. Self-hosted Supabase + containerised app** |
| **S32B** | **UI/navigation rework** | **D-69. In Streamlit, not a rewrite** |
| **S33** | **GDPR deletion + session hardening** | **BETA GATE** |
| S34 | Regulatory update → impact re-scoring | Reads S27 `source_revision` |
| S35 | Multi-user for Professional | Seeds `workspace_members` |
| S36 | Audit rate-limiting | |
| S37 | Audit report email delivery | |
| S38 | Domain verification | |
| S39 | Scheduled recurring audits | Depends on S38 |
| S40 | Freemium single-page scanner | Two-stage funnel — see S40 note |
| S41 | Stripe + credits + annual billing | Meters shipped in S27 |
| S42 | Onboarding redesign | Auto-detection layer only |
| S43 | Document branding | Theme only |
| S44 | Breach notification workflow | |
| S45 | Advisory multi-client workspace | |
| S46 | Enterprise multi-seat/multi-division | |
| S47 | Enterprise routing + in-app messaging | |
| S48 | Buffer/LinkedIn integration | |
| S49 | Monitoring source management | Low priority. Merge with S54 |
| S50 | Skills matrix and training register | High value-to-cost |
| S51 | AI Act three-layer inventory | Use case / system / model |
| S52 | Annual compliance report | |
| S53 | Dutch language support | Cost grows with every template shipped |
| S54 | Competitive monitoring | Merge with S49 |
| S55 | RoPA consistency checks | Depends on S26C |
| S56 | Cookie Policy purpose granularity | |
| S57 | Compliance heartbeat — scheduled checks | Needs `hold_set_on` (shipped) |

**Sequencing note on S31.** S28, S29 and S30 all produce documents with LLM
inserts. If those inserts retrieve context, S31 gates the quality of three
sprints that ship before it — and templates authored against a retrieval layer
already suspected of being wrong get reviewed twice. Settle it before S28 by
running a NIS2, an AI Act and a GDPR query through `retrieve()` and looking at
the chunk mix. An afternoon's check turns a guess into an answer.

**Unnumbered, still to be slotted:**
- ~~**Task register**~~ — now part of **S29**. Retained here for context: Unresolved work is
  currently surfaced where it is found and nowhere else: `readiness()` gaps,
  outstanding `[[ TO COMPLETE ]]` placeholders, S55 findings, unreviewed
  translations (S26C), S57 heartbeat findings. A client cannot see everything
  outstanding in one place and an auditor cannot see that a gap was found on
  one date and closed on another. **Three sprints already depend on it.**
- ~~UI/navigation redesign~~ — now **S32B** (D-69).
- Pinning the remaining `requirements.txt` packages — before beta onboarding.

**Post-S48 backlog:** DB schema import tool; NIS2 vendor risk register (extend
to third-party AI tools); compliance calendar; public compliance badge; RECOSA
trust page; SSO/SAML; document diffing; register export as a document.

---

## 3b. Sprint scopes and research

Detail behind the roadmap table above: scope locks for sprints not yet started,
the competitor research they came from, and the open checks and deferred items
they carry.

*Written 3–8 September 2026. Folded in from working documents — the roadmap
table alone had the sprint numbers and none of the reasoning.*

### S27 — Document register — SCOPE LOCK

**Position:** after S26C, before S28. Pre-beta.
**Strategic, not cosmetic (D-09).** This is the sprint that makes regulatory
update propagation possible: without a register, RECOSA cannot answer "which
clients are running the old version of this template".

---

#### The model, and where the Git analogy breaks

Immutable versions, a chain, one current head per key, metadata about what
changed. That part transfers.

Where it breaks: **Git diffs text it can read.** Uploaded documents are
deliberately opaque — no parsing (recorded in the S27 line since it was first
registered). For an uploaded document RECOSA has bytes and a filename, so it
cannot say what changed. See "Change notes" below, which splits on exactly this.

---

#### Key and status

**Primary key is (client_id, doc_type, language).** Not (client, doc_type).

A French policy adopted while the English one is still draft is a real state
and the dashboard has to express it — "Policy X is in force in FR, outdated in
EN, not available in NL". Collapsing language into one row makes that
unsayable.

Status: `draft` / `in_force` / `superseded` / `archived`.

**One `in_force` row per key, many superseded ones.** A partial unique index on
`(client_id, doc_type, language) WHERE status = 'in_force'` expresses it, but
**partial indexes cannot serve as `ON CONFLICT` arbiters (42P10)** — a
constraint already recorded in this log. Adoption must therefore be an explicit
transition (supersede the current head, then insert), not an upsert. Design for
that from the start.

---

#### Generation is not adoption

Two distinct artifacts, and conflating them is the main design risk.

- **Generated document** — produced by the template engine. RECOSA knows its
  template version, source revision and every merge value.
- **Adopted document** — what the client actually operates under. Often the
  generated one; sometimes a revision that came back from counsel and was
  uploaded.

The register tracks the second and points at the first. A client generates a
DPA, sends it to counsel, gets it back changed, uploads the revision — *that*
is the in-force version.

**Consequence to state on the register's face:** once a reworked document is
uploaded, RECOSA can no longer score it, cannot tell whether counsel removed a
clause, and cannot propagate a regulatory update into it. The register must say
so rather than implying the uploaded document is still covered. An auditor
reading the page should be able to tell which documents RECOSA vouches for the
structure of and which it merely holds.

---

#### Stamping

Every register row carries, at **adoption** and not merely at generation:

- `template_id`, `template_version_id`, `source_revision`
- `effective_from` — the date the version began to apply, which is a client
  fact and not `created_at`
- `published_at` where the document is published (cookie policy, privacy
  policy) — evidence of when it actually appeared
- `superseded_by` / `superseded_on`
- `origin`: `generated` | `generated_then_revised` | `external`
- `language`

`source_revision` is the S34 hook: when a template's source revision bumps
because the underlying law changed, the register is what identifies every
client still on the old one.

---

#### Change notes

**Split on what RECOSA can actually know.**

**Generated → generated: computed, deterministic, free.** No LLM. RECOSA holds
the previous template version, the new one, and both sets of merge values, so
the note is exact: *"Clause 7.7(a) notice period changed from 30 to 60 days;
Annex II gained Payroll administration; template updated to source revision 2
(Commission Decision amended)."* Produced in every document language from the
same structured facts. For a document that goes to counsel, a computed note is
strictly better than a generated one — no hallucination surface, no review
burden, no cost.

**Generated → uploaded revision, or uploaded → uploaded: RECOSA knows a human
changed something and nothing more.** It says exactly that. The client can
write their own note, and should be prompted to.

**Optional analysis of an uploaded revision — on request, never automatic.**
A button ("Analyse changes"), not a background job. Reverses the no-parsing
rule for that document only, at the client's instruction.

- Never automatic, because a wrong summary of a legal change is worse than no
  summary, and because parsing a document the client uploaded is a thing they
  should ask for rather than have happen to them.
- Output is explicitly marked as a machine reading of a document RECOSA did not
  produce, and is advisory — the same posture as `machine_unreviewed`
  translations in S26C.
- **Metered from day one.** Billing is S41, but the counter is S27: an
  `analysis_runs` record per invocation with client, document version, tokens
  and outcome. Retrofitting usage tracking after a feature ships is how you end
  up guessing at historical volumes when pricing it.
- Tier-gated at the switch level in S27, with the tier itself defined in S41.

---

#### External and user-generated documents

The register holds documents RECOSA did not produce, because the objective is
to be the single source of truth for compliance across the regulations covered.
A client with a counsel-drafted DPIA has a real compliance document, and an
auditor page that cannot show it is incomplete.

Two consequences:

- **They cannot be scored.** No template, no obligations mapping. The auditor
  page must distinguish structurally vouched-for documents from held ones.
- **`doc_type` needs values for them.** Append-only convention applies: add
  codes, never allow null. At minimum an `external_other` with a client-supplied
  label; better, codes for the documents RECOSA does not yet generate but
  expects to see (DPIA before S30, training records before S50).

---

#### Retention of superseded versions

**Default: retained, not deleted.** Reversing the earlier "delete to save
space, pay to keep longer" model — see the note at the end.

There is no GDPR rule stating a retention period for superseded transparency
notices. The requirement is Art. 5(2) accountability: the client must be able to
demonstrate what information it provided at the time the processing took place.
A complaint in 2027 about processing in 2024 is answered by the 2024 policy, not
the current one.

Working rule to implement, **configurable and displayed with its reasoning
rather than asserted as law** (D-50, D-51 — RECOSA does not state legal periods
it has not verified):

> Historical versions of privacy notices, cookie policies and other
> transparency notices are retained for five years after they cease to apply,
> unless a longer period is required by a pending or reasonably anticipated
> complaint, investigation, audit or proceeding.

Requirements that follow:

- **Legal hold.** A flag that suspends deletion regardless of age, for a
  document relevant to a live matter. Without it the retention rule deletes
  evidence during the proceeding that needs it.
- **Archive as it appeared** — the rendered artifact with its own version number
  and effective date on it, not a re-render from current data. A re-render is
  not evidence of what the client published.
- **Historical versions are never presented as current.** A rendering rule, and
  a real risk once superseded versions are downloadable.
- **Cookie policies are the strict case.** The Belgian DPA is reported to
  expect retained previous versions, dated and version-numbered, together with
  evidence of how the consent mechanism evolved. That last item is not a
  document — it is configuration history, and RECOSA does not hold it today.
  **Open: does S27 store cookie-banner configuration history, or is that S56?**
- **VERIFY BEFORE SHIPPING.** The Belgian DPA guidance above and the five-year
  figure come from a working note, not from a checked primary source. Both are
  reasonable; neither should become a product default that tells a client what
  the law requires until confirmed. Same standard as D-42 and D-51.

**Deletion, when it happens, keeps the metadata.** Version number, effective
dates, change note, who adopted it, when it was superseded. But state plainly at
the point of deletion that **metadata is not evidence**: a client discarding the
artifact may be discarding the only proof of what they were operating under, and
they should be told that rather than reassured by the row that remains.

---

#### Out of scope

- A médiathèque. Adequacy has document storage connected to every module with
  permission scopes; S27 is a register with an upload slot, not a DMS. The main
  scope-creep risk in this sprint.
- Parsing uploaded documents by default. Only the on-request analysis above.
- Scoring external documents.
- The billing and tier definitions themselves (S41). S27 implements the switch
  and the counter.
- Cookie-banner configuration history, pending the open question above.

---

#### Dashboard rollup

Per-document, per-language status surfaced as a client-facing summary:
*"Privacy Policy — in force (FR), outdated (EN), not available (NL)."*

**One thing to decide before building:** the moment a client sets NL as a
document language, every document reports "not available in NL", because the
templates do not exist until S53. Honest, and the point of the feature — but
alarming on day one and not actionable by the client. Options: show gaps only
for languages RECOSA can currently produce; or show them all and say plainly
which are RECOSA's gap rather than the client's. **The second is more honest
and needs wording care.**

---

---

### S41 — Billing — SCOPE ADDITIONS (from S27)

S41 defines tiers, prices and enforcement. S27 ships the switches and the
counters, so that when S41 arrives the usage history already exists rather than
being guessed at retrospectively.

**Implement the meter with the feature, not with the billing.** A feature that
ships unmetered means pricing it later against invented volumes.

---

#### Metered in S27, priced in S41

**Uploaded-document analysis.** The "Analyse changes" button in S27 parses a
document the client uploaded and summarises what a human altered. It is an LLM
call against an arbitrary-length document — the most expensive per-invocation
feature in the product, and unlike translation it has no cheap fallback.

- `analysis_runs`: client, document version, tokens in/out, outcome, timestamp.
- Token usage logged through `database.log_token_usage` with a distinct
  feature name, alongside `chat` and `translate` (S26C).
- S27 implements the tier check as a switch; S41 decides where it sits.
- Candidate shape: unavailable on Starter, N runs per month on Professional,
  unmetered on Advisory. Not decided here.

**Document storage volume.** External and user-generated documents (S27) are
client-supplied files of arbitrary size, unlike generated documents which are
small and predictable.

- Track bytes stored per client, split by `origin`: generated, revised,
  external.
- The split matters for the pricing rule below.

**Translation.** Already logged as feature `translate` from S26C. No further
work; noted so S41 sees it.

---

#### Pricing rule: compliance is never behind a paywall

**Retained superseded versions are not a paid feature.**

An earlier model had old versions deleted by default with longer retention sold
as an option. That was reversed in S27, and the reason belongs here rather than
only there:

Historical versions of transparency notices are accountability evidence under
Art. 5(2). If they are what makes a client defensible, charging to keep them is
selling back the thing that makes them compliant, and deleting them by default
leaves a client worse off than if they had stored nothing in RECOSA at all.
A competitor would put that in a comparison table, and they would be right to.

The documents are also small. Generated compliance documents are kilobytes; the
storage cost of retaining every superseded version for five years across the
whole client base is not a line item worth defending.

**So the monetisation surface is:**

- retention **beyond** the compliance-relevant window
- **volume** of client-uploaded external documents, which is genuinely
  unbounded and genuinely costly
- the **analysis** feature, which is compute rather than compliance
- seats, clients, and the existing tier axes

**Not:** the client's ability to demonstrate what they published in 2024.

---

#### Consequence for tier design

Any feature gate proposed in S41 should be checked against one question: **does
withholding this make the client less compliant, or only less comfortable?**

Withholding convenience, automation, speed, analysis, seats and multi-client
workspaces is normal product tiering. Withholding evidence, retention of what
they have already adopted, or the ability to produce a document an obligation
requires is selling compliance back to them — and it undermines the positioning
that RECOSA produces compliance documents where competitors only manage them.

Worth recording as a decision when S41 is scoped.

---

### New sprints and scope notes

Registered after reviewing two competitors: `data-privacy-office.eu`
(DPO Europe GmbH — consultancy, fixed-price AI Act packages) and
`adequacy.app` (French SaaS, GDPR + AI Act + NIS2, enterprise and public
sector). Reference data at the end.

#### Scope notes on existing sprints

**S30 — DPIA — target the EDPB template.** Adequacy's 6.3.1 release (5 Aug
2026) added DPIA output conforming to the EDPB model. Match the published
template rather than inventing a structure: an auditor recognising the shape of
the document is worth more than a better-organised original.

**S40 — freemium scanner — two-stage funnel.** Adequacy runs a public
10-question NIS2 self-assessment (ungated, no email wall) feeding a 32-question
in-product maturity questionnaire that scores and populates the action plan.
DPO Europe gates a 4-step AI Act checklist behind a form and emails a PDF.
Public stage short and ungated with the answer inline; in-product stage full
and scored. **Calibration: 32 questions is what a credible NIS2 maturity
assessment costs a user** — if the RECOSA set produces materially fewer, check
for thinness.

**Vendor/supply-chain risk register (unscheduled) — extend to AI tools.** DPO
Europe sells a "vendor and external AI tools compliance checklist" as a
deliverable. The same register serves NIS2 Art. 21 supply-chain security and
AI Act deployer duties over third-party AI. Builds on the S24 criticality field
plus S51.

#### S26B — renumbered to S55

Registered mid-session as a sub-sprint, then renumbered. The letter suffix
means work running adjacent in time to its parent — S26A ran immediately after
S26, before anything else. Consistency checks run after the S33 beta gate, so a
suffix would have read as a scheduling error rather than a subject grouping.
See section 6.

#### S28A — AI deployer document pack

**Priority:** immediately after S28. **Tier:** 1 to low 2.

DPO Europe's Deployer track lists what an SME using third-party AI actually
needs. S28 covers the transparency notice; these are the next two.

- **Acceptable Use Policy (AI)** — permitted and prohibited uses, data that
  must not be entered into third-party models, approval route for new tools,
  consequences of breach. EN + FR.
- **Human Oversight Policy** — who oversees which system, competence
  requirement, escalation protocol, override authority, review cadence.

Neither competitor generates these: Adequacy has no document library, and DPO
Europe charges €9,900 for a manual pack containing them.

#### S50 — Skills matrix and training register

**Priority:** high value-to-cost. Pre-beta if S33 allows. **Cost:** low —
two tables, one form, two documents, no engine.

Informational only; RECOSA does not deliver training. It produces the evidence
a regulator asks for.

Scope: `employees` and `training_records` tables with RLS on both INSERT and
SELECT; a matrix view of employees against regulations showing current /
expiring / absent against required-competence definitions held in Postgres per
the S24 reference-data decision; a training plan document and an attendance
attestation, both Tier 1; a content-free staleness nudge per the Brevo
constraint.

Out of scope: delivering or hosting training; LMS integration; and any claim
that a filled matrix satisfies the obligation. **The output is evidence of a
plan, not evidence of competence** — a client who confuses the two is worse off
than one with no matrix.

Anchors: AI Act Art. 4 (in force since 2 Feb 2025, binds Providers *and*
Deployers, requires demonstrable completion); NIS2 Art. 20(2) (management
bodies must follow training); GDPR Art. 39(1)(b), Art. 32 and Art. 5(2).

Both competitors have shipped a training module — Adequacy's "Plan de
formation RGPD" is marked NEW, DPO Europe sells AI literacy training as a line
item. Two independent signals that training-and-evidence is a real surface.

#### S51 — AI Act system inventory (three-layer)

**Priority:** post-beta, ahead of CRA.

Adequacy separates three entities that are easy to collapse: **use cases**,
the **SIA register** (deployed systems) and the **model repository**. DPO
Europe independently determines role per system and per legal entity.

- `ai_models` — model or service used or trained.
- `ai_systems` — a deployed system built on one or more models.
- `ai_use_cases` — a business use of a system. **Risk classification and role
  attach here**, not to the model.
- Role per use case: Provider / Deployer / Importer / Distributor. One client
  routinely holds several at once.
- Art. 25 substantial-modification flag — a Deployer who materially modifies a
  system becomes a Provider.
- Deployer intake asks only what a Deployer can answer; technical attributes
  inherit from the provider's documentation rather than being demanded of an
  SME deploying a third-party chatbot.

Out of scope: Provider-track conformity assessment, Annex IV technical
documentation, CE marking, bias and fairness auditing.

Rationale: one model underlies many systems; one system serves many use cases.
Flattening produces wrong classifications the moment a client uses one vendor
model for two purposes with different risk profiles. Arrived at independently
by both competitors, and not the obvious model.

#### S52 — Annual compliance report ("Bilan")

**Priority:** post-beta, near S38. **Depends on:** S27, S21.

Period-bounded, board-facing: obligations in force during the period, documents
adopted or superseded, incidents, training completed (S50), open actions,
regulatory changes affecting the client (S34). Rendered through the existing
template engine plus `document_xlsx.py`, stamped and registered like any other
document. S27 gives the auditor a register; this gives management a narrative,
and management-level accountability is an explicit NIS2 duty.

#### S53 — Dutch (NL) language support

**Priority:** post-beta, but it constrains work starting now.

Adequacy supports seven interface languages including Dutch. For a Belgian
market this is not optional: a Flemish SME will not adopt a French-and-English
tool, and **Dutch is more commercially relevant in Belgium than the sovereignty
claim**.

Scope: NL interface labels; NL reference-data labels across every seeded table;
NL siblings for every Tier 1 and Tier 2 template; GBA/APD naming and language
routing.

**Constrains present work.** Every template authored before S53 needs an NL
sibling, so the sprint's cost grows with every document shipped. Keep templates
language-parallel — same block IDs, merge fields and materiality — so NL is
translation, not re-derivation. Estimate against the S27–S32 template output
before committing to a date, and consider pulling NL forward for Tier 1 only.

Note: `reference_values` already carries `label_nl` / `label_de` / `note_nl` /
`note_de`, and `inventory.py`'s `LANGUAGES` already declares four. Only the
seeder is behind.

#### S54 — Competitive monitoring

**Priority:** low, alongside S49. Not beta-blocking.

Regulatory and marketing monitoring exist; competitive does not.

Scope: competitor source table (name, URL, page type, cadence, last-seen hash);
change detection with the diff summarised rather than the page. Initial
sources: `adequacy.app` homepage, `/adequacy-ai-act`, `/adds-on/adequacy-nis2`
and blog (release notes appear there); `data-privacy-office.eu`
`/compliance-automation-tools/` (Agentic DPO and OS4DPO listed as coming soon)
and `/services/ai-compliance-services/` (prices published, will move);
ComplyOne and Kalipso, sources TBC. Admin back-office only; no client-facing
output; no email unless a pricing page changes. Nothing behind a login, and no
competitor content in RECOSA output.

**Merge with S49.** Adding a third monitoring type to the current duplicate
`pages_admin/` modules makes the tangle worse. One monitoring-consolidation
sprint.

#### Task register — unnumbered, needs a number

Audit infrastructure, pairs with the S21 audit trail and the S27 document
register.

Unresolved work is currently surfaced where it is found and nowhere else:
`readiness()` gaps, outstanding `[[ TO COMPLETE ]]` placeholders, S26B
consistency findings, vendor DPA gaps, and now translation review. A client
cannot see everything outstanding in one place, and an auditor cannot see that
a gap was found on one date and closed on another.

S26C writes into it rather than inventing a translation-specific mechanism, and
S55 is given the same instruction. Until it exists, translation review has
nowhere to land beyond a column in the activity summary.

S27 adds two more producers: documents whose template source revision has moved
on, and uploaded revisions that need a client-written change note.

---

### S55 and S56 — post-beta sprints

Both were briefly registered as sub-sprints of S26 and renumbered. The letter
suffix means work running adjacent in time to its parent (S26A ran immediately
after S26, before anything else). These run after the S33 beta gate, so a
suffix would have read as a scheduling error rather than a subject grouping.

---

### S55 — RoPA consistency checks

**Priority:** post-beta. Small.
**Depends on:** S26 (RoPA schema), **S26C** (structured retention and the
`retention_basis` vocabulary — several rules below are only checkable because
those fields stopped being free text). Do not schedule ahead of S26C on the
strength of the number alone.

#### Why

Adequacy sells "contrôle de cohérence" in its entry tier, described for
mid-market as the software identifying non-compliance points inside each
processing record. It is validation over structured register data, which now
exists here.

It is also the cheapest credible answer to "how do I know my register is any
good" — the question an SME cannot answer for itself, and the reason a client
pays for a compliance tool rather than a template pack.

#### Scope

A pure function over a processing activity row returning a list of findings,
each with a severity (`error` / `warning` / `info`), a message, and the
field(s) implicated. Rules encoded as executable checks in the
`catalogue_principles` pattern, not prose.

Candidate rules:

- special-category flag set with no Art. 9(2) condition selected
- Art. 9(2) condition selected with no special category flagged
- third-country transfer with no Art. 46 safeguard named
- retention absent, or still recorded as free text where structured fields
  exist (S26C leaves these deliberately un-backfilled, D-48 — this rule is how
  a client finds them)
- archive phase recorded with no basis (the DB constraint catches new writes;
  this catches anything written by another path)
- legal basis `consent` on an activity whose data subjects are employees
- legal basis `legitimate_interests` with no balancing test recorded
- processor-role activity with no counterparty row in `activity_counterparties`
- counterparty marked processor with no DPA recorded against the system
  (`dpa_status`) — available once S27 lands
- retention marked statutory with a period the client set by hand and no
  statutory basis code

Surfaced on the activity detail form and aggregated on the RoPA page. Findings
are advisory.

#### Out of scope

- Auto-remediation.
- Any LLM. These are deterministic rules; that is the point.
- **Scoring impact.** Findings must not feed the gap score. Mixing register
  hygiene into document scoring re-creates the `DOC_OBLIGATIONS` /
  `DOC_SCORING_OBLIGATIONS` conflation, where "which obligations should I check
  when reviewing this" and "which obligations does this satisfy" were treated
  as the same question and complete documents scored as partial.

#### Rationale

The S24 retention self-check caught three Microsoft 365 activities minutes
after being written. Same pattern, wider surface, and the S26C seed self-check
repeated the result — encoding a rule as an executable constraint catches
violations at the moment of authoring rather than at audit.

#### Where the findings should land

The task register (unnumbered, see the session log). Until it exists, findings
surface only where they are computed, and an auditor cannot see that a gap was
found on one date and closed on another. S55 should write into it rather than
inventing a second mechanism — the same instruction given to S26C for
translation review.

---

### S56 — Cookie Policy purpose granularity

**Priority:** post-beta, with a caveat below.
**Depends on:** S26C (the i18n pattern this extends).

#### The problem

`systems.purpose` is one free-text field per system, rendered into the Cookie
Policy against each vendor. The unit that matters legally is not the vendor —
it is the cookie, or at least the vendor-purpose pair.

A single vendor routinely serves several distinct purposes. Google is the
obvious case: analytics, advertising, personalisation and fraud prevention from
one company. Art. 5(3) ePrivacy requires clear and comprehensive information
about the purposes of the storage or access, and consent must be specific and
informed under Art. 4(11) GDPR. Bundling distinct purposes under one label does
not produce valid consent.

The current schema can only describe a vendor as doing one thing. That is true
regardless of language.

#### Relationship to S26C

Two problems were conflated during S26C and should not be again:

1. **Language** — one string rendered into every language. Solved by the i18n
   pattern; `purpose_i18n` and `translation_status` are already on `systems`,
   and `template_store._load_vendor_rows()` already reads them.
2. **Granularity** — the entity is wrong. Not solved, and not solvable by
   translating a field that describes the wrong thing.

Same shape as D-49 (retention has two phases, not one period) and S51 (one
model, many systems, many use cases), arrived at from a third direction. **When
a field cannot hold two true answers, the entity is usually wrong.**

#### Scope

- A `system_purposes` child of `systems`: purpose category code (the existing
  vendor category vocabulary), per-language description, and the cookie names
  or identifiers it covers where known.
- Cookie Policy renders one row per vendor-purpose pair rather than per vendor.
- Migration path from the existing single `purpose` / `purpose_i18n`, which
  becomes the first row.
- The input path is the open question — see below.

#### The input path is unresolved

The Systems tab uses `st.data_editor`, chosen because every field is scalar and
the task is confirmation rather than authoring. A repeating child table is not
a scalar, and `st.data_editor` has no place to review a per-language draft —
the same constraint that put activities on list-plus-detail in the first place.

S56 therefore probably needs a detail form for systems, which is a UX change
beyond the schema work. Scope that before building, not during.

#### Caveat on deferring past beta

Defensible, **provided the free-text purpose stays in place**. It was proposed
during S26C that `purpose` be dropped from the Cookie Policy vendor table in
favour of the coded category, on the grounds that the category renders
correctly in every language. That would be a downgrade: "Analytics" against
Google Ireland Limited is arguably too coarse to inform the consent the policy
is asking for, and the free text is what carries the legal weight.

The residual risk while deferred: a Cookie Policy is **published**. Unlike a
register, which sits in a drawer until an auditor asks, it is the document a
supervisory authority can read without contacting the client. A beta client who
publishes one is publishing a document with a known granularity weakness under
RECOSA's name.

Mitigated by the fact that most SME cookie setups have one purpose per vendor,
and by the free text remaining available for clients who want to be specific.
It is Google specifically that breaks the model.

---

### S57 — Compliance heartbeat (scheduled checks)

**Priority:** post-beta, but see the beta caveat.
**Depends on:** S27 (register, retention, legal hold), S21 (audit trail).
**Related:** S33 (retention sweep — different job, same schedule), S50 (training
expiry), S55 (RoPA consistency checks), the task register (unnumbered).

---

#### Why

Everything RECOSA checks today is checked when a client happens to open a page.
Nothing looks at a client's compliance while they are not looking at it.

That is the wrong model for most of what compliance actually requires. Records
go stale, retention dates pass, training expires, a legal hold set during a
complaint outlives the complaint by two years because nobody revisited it.
None of those are events a client triggers; they are things that become true
through time passing, and a product that only reports on demand reports them
late or never.

Regulatory monitoring already runs on a schedule. This is the same idea pointed
at the client's own data rather than at the law.

---

#### First check: stale legal holds

The case that prompted this sprint.

A hold suspends deletion for a version relevant to a live complaint,
investigation, audit or proceeding (S27). Proceedings end. Holds do not — they
are set in a moment of urgency and released, if ever, by someone remembering.

A hold that outlives its reason is not harmless: it retains personal data past
the retention period the client set, which is a storage-limitation problem
under Art. 5(1)(e) rather than a tidiness one. The client is over-retaining
because a flag was never cleared.

**Rule:** hold set more than 30 days ago and still on →
- warning on the dashboard,
- email asking whether it is still needed.

Wording is a question, not an instruction: RECOSA does not know whether the
proceeding is over, and telling a client to release a hold on evidence in a
live matter would be worse than saying nothing. "Is this still necessary?" is
the whole message.

`legal_hold` needs a `hold_set_on` timestamp — S27 stores the flag and the
reason but not when it was set, so the 30-day clock has nothing to run from.
**Small migration, and it should land before any hold is set in anger.**

---

#### Other checks to fold in

Not exhaustive; the point of the sprint is the mechanism, and each rule is
cheap once it exists.

- **Published policy has drifted from the in-force version.** Crawl the
  client's site and compare what is live against the register. "Your website is
  showing v2; you adopted v3 in September" is a real finding — an unpublished
  policy discharges nothing under Art. 12. Uses S27's `published_at`.
  *(Added 8 Sept from the S28 scope lock.)*
- **Retention dates approaching.** A superseded version reaching `retain_until`
  within 30 days, so the client can archive a copy before it goes. Pairs with
  the S33 sweep — this warns, that deletes.
- **Documents not reviewed in a year.** In force, never superseded, never
  looked at. Not a breach, but a register nobody has revisited is usually a
  register that has drifted from the business.
- **Drafts never adopted.** Generated months ago and never put in force. Either
  the client meant to and forgot, or they abandoned it and it should be
  discarded. Both are worth a nudge.
- **Training expiring** (S50) — AI Act Art. 4 literacy, NIS2 Art. 20(2)
  management training.
- **Consistency findings** (S55) that have sat unresolved.
- **Unreviewed machine translations** (S26C `machine_unreviewed`) still
  rendering into documents.
- **Inventory not touched since a system was added.** A new vendor with no
  processing activity attached is a gap that only shows up when someone looks.

---

#### Design constraints

**Brevo content-free rule applies.** Notification emails must name no
regulation, no document name, no ticket subject — all client-authored content
may be sensitive, and Brevo click-tracking rewrites links through
`sendibt3.com` regardless. A heartbeat email says something has come up and
carries a link. Nothing more.

**One digest, not one email per finding.** A client with six stale items should
receive one message. Per-finding emails are how a product teaches people to
filter it out, and then the one that mattered is filtered too.

**Findings go to the task register**, not only to an email. An email is a
prompt; the register is the record. Without it there is no way to show an
auditor that a gap was found on one date and closed on another — and no way for
a client who deleted the email to find out what it was about.

**Nothing acts automatically.** The heartbeat warns; it never releases a hold,
never deletes, never adopts. S33's retention sweep is the only scheduled job
that removes anything, and it is deliberately a separate one.

**Idempotent and quiet.** A rule that fires every night on the same unchanged
finding is a rule the client mutes. Findings persist in the task register and
re-notify on a schedule, not on every run.

---

#### Beta caveat

The mechanism is post-beta, but **`hold_set_on` is not**. A hold set during
beta with no timestamp cannot be aged later — the information is simply not
there. Add the column with S27 or immediately after, even though nothing reads
it yet.

Same reasoning as metering the analysis feature in S27 before S41 prices it:
the data has to start accumulating before the feature that consumes it exists,
because it cannot be reconstructed afterwards.

---

### Open checks

**Is AI Act Art. 4 (AI literacy) in the obligations catalogue as in-force?**
Applies since 2 February 2025 to Providers and Deployers alike and requires
evidence of completion. The most universally applicable AI Act duty in the
target market and among the cheapest to satisfy. If absent, add with
`applies_from = 2025-02-02` and link the evidence artifact to S50.

**Is there an `applies_from` row for 2 December 2026?** DPO Europe's timeline
states additional prohibited AI practices introduced by the AI Omnibus begin to
apply then, with transitional requirements. The Omnibus deferral of standalone
Annex III to 2 December 2027 is recorded; this is not. **Verify against the OJ
text of Regulation (EU) 2026/1744 — a competitor marketing page is not a
source.**

**Is AI Act role resolved per client or per system?** Both competitors resolve
Provider/Deployer/Importer/Distributor per system and per legal entity. If the
current applicability logic holds a single role on the client record,
obligations are wrong for any client that both builds and uses AI — which is
most of them. Possible live modelling bug, not merely an S51 dependency.

**`chat.py`'s system prompt contradicts the obligations catalogue.** It tells
clients Annex III high-risk applies from 2 August 2026. The Digital Omnibus
deferred the standalone Annex III deadline to 2 December 2027, and
`applies_from` already reflects it. A client asking the chat gets a date their
dashboard contradicts, and the date has now passed. **Client-visible wrong
answer about a legal deadline.** Not S26C; fix separately.

**Art. 9(2) conditions beyond `employment_social_security`** *(carried from
S24)*. Both seeded paths use the same condition; the other nine are untested.
The S26B rule "special-category flag with no Art. 9(2) condition" exercises
them.

*(The S24 `selected_client["language"]` check is resolved: `pages/inventory.py`
reads `document_languages`, and S26C now derives `doc_langs` from it.)*

---

### Deferred

**Rolling retention start dates.** Some periods run from a resetting event:
prospect data three years from last contact, candidate CVs two years, each new
contact restarting the clock. A register stating "3 years" without "from last
contact" is incomplete under Art. 30(1)(f). The honest fix is a
`retention_starts_from` field, not a basis code — the code answers *why*, this
answers *when the clock starts*. An `until_last_contact` code was proposed and
dropped for conflating the two.

**Citations in reference notes.** D-51. Needs counsel review.

**Generate `reference_values_type_valid` from `VOCABULARIES.keys()`.** The
constraint is a hardcoded list of 17 value_types, edited by hand — a second
place the vocabulary list lives. It failed loudly when `retention_basis` was
seeded, which is the right direction to fail in, but it is the
derived-list-maintained-by-hand shape the single-source-of-truth principle
warns about. `inventory_seed.py` already emits the vocabularies; emitting the
`ALTER` alongside them closes it.

**Reference membership triggers.** `retention_unit`, `retention_archive_unit`,
`retention_basis_code` and `retention_archive_basis_code` are guarded only by
`validate_activity()`, which is UX rather than safety. The CHECK constraint on
`reference_values.value_type` is a different mechanism and does not cover these.

**`inventory_seed.py` writes only EN and FR.** `reference_values` has
`label_nl`, `label_de`, `note_nl`, `note_de`. The `note_fr` gap was closed this
session — every note in the table had been NULL since creation, so
`note_for(..., lang="fr")` silently returned English for every code. NL and DE
remain unwritten. S53.

**Systems grid purpose.** Resolved: absorbed into S56, which addresses the
underlying modelling problem rather than only the language one. See S26C "Not
shipped" for why translation alone would not have fixed it.

---

### External findings

**CNIL published a new RH retention référentiel on 2 April 2026** —
délibération n° 2026-031 of 29 January 2026, JO 3 April 2026, complementing the
2019 référentiel. Post-cutoff; not in scope when S26C was planned. It separates
durations imposed by legislation from recommended durations serving as
reference points — the same `statutory_*` / `regulatory_guidance` split arrived
at independently. It covers whistleblowing under the law of 21 March 2022,
where report data is kept until the final decision, which is why
`until_procedure_concluded` exists.

**CNIL named recruitment a 2026 enforcement priority** the day after
publishing, with checks on automated decision-making, candidate information and
retention periods. Direct hit on the target market; an argument for S54 to
track CNIL référentiels specifically.

**Belgian retention periods genuinely diverge.** CDE art. III.86: accounting
books seven years. Law of 20 November 2022: tax and VAT ten years from
1 January 2023. VAT revision on immovable property longer again. Social
documents — personnel register, special register, individual account and
annexes — five years. See D-50.

---

### Competitor reference data

Captured 2 September 2026. Verify before reuse.

#### DPO Europe GmbH — consultancy (Berlin, DP Group)

Fixed-price AI Act engagements: Startup Fast-Track €9,900 (4–6 wks, up to 5 AI
systems, 1 jurisdiction); Startup Premium €14,900 (+ investor DD pack);
Enterprise Standard €24,900 (8–10 wks, 5–10 systems, 2 jurisdictions);
Enterprise Premium €39,900 (12–16 wks, 11–20 systems, 3+ jurisdictions, GPAI).
Additional system €1,200; multi-jurisdiction +€2,500. Training separate
(AICP-E €1,050 + VAT; AI4DPO from €590).

Method: three phases — applicability/role/risk with separate Provider and
Deployer inventory tracks; obligations per track; governance, entity-level
obligation distribution, bias framework, vendor AI checklist.

Guarantees: evidence pack by week 4 or free extension; free documentation if a
regulator asks within 90 days; money-back if a corporate deal is lost on their
materials. Markers: €2m Hiscox indemnity, 250 projects, 50 jurisdictions.

Products: Applicability App (live — AI-assisted pre-fill from public company
information, question-tree personalisation, report plus routing to local
consultants), GDPR-Text (live), OS4DPO and **Agentic DPO** coming soon.

*Read: the apps are lead generation into billable hours. Structurally unlikely
to build depth that cannibalises consulting. Agentic DPO is the one to watch.*

#### Adequacy — SaaS (France, hosted OVHcloud)

Tiers, cumulative, **no published prices, every CTA is demo or quote**:
Start (registre, PIA, contrôle de cohérence, cartographie des transferts, plan
d'action, tiers); Essentiel (+ sollicitation, droits, contrats, mentions,
incident/violation, plan de formation); Expert (+ évaluation, bilan du DPO,
gouvernance, audit, management du risque, privacy by design). Add-ons: Form,
Legacy, Administration locale, **NIS 2** (standalone), Options IT. AI Act
module: cas d'usages, registre SIA, référentiel des modèles, dossiers de
conformité, gouvernance IA.

Platform: multi-user with fine-grained profiles, multi-entity, seven languages
(FR, EN, **NL**, IT, DE, PT, ES), multi-regulation "Multiverse", SSO plus
documented API, médiathèque, cartographie applicative, bulk edit.

Claimed: 10,000 legal entities, 99.8% uptime, 50% time saved on the register,
75% on impact assessments.

References: Solvay, OVHcloud, Naval Group, Dassault Aviation, Bolloré,
TotalEnergies, Valeo, Sopra Steria, Bouygues, Le Figaro, Generali France, AFP,
Europcar; public sector, départements, CHU Rouen, CHU Montpellier, a dozen
universities.

*Read: enterprise and public sector, sold through demos, with attached services
and AFNOR DPO training. PME is listed but nothing suggests they win there. The
risk is downmarket movement, which S54 should catch.*

#### Positioning consequences

**Adequacy manages compliance documents; RECOSA produces them.** Adequacy's
modules are registers, assessments, action plans and dashboards; its input
assistance is contextual suggestions, not generation. It has no document
library — no cookie policy, privacy policy, DPA, InfoSec policy. Its product
assumes a professional user who writes the documents. DPO Europe writes them by
hand at €9,900. The template engine is the differentiator.
*Rejected:* leading on regulation breadth — Adequacy already covers GDPR +
AI Act + NIS2 and is adding more.

**EU sovereignty demoted from headline to supporting claim in French-market
copy.** Adequacy's three headline claims are simple, secure, sovereign — hosted
at OVHcloud, 100% French, with OVHcloud itself a reference customer citing
sovereignty as the deciding factor. Sovereignty is table stakes in France, not
a wedge. Keep EU-native infrastructure and the no-CLOUD-Act statement as a
trust page and a procurement answer. In Belgium "European" reads differently
from "French" and retains some force — worth an A/B test, not an assumption.
*Rejected:* competing on sovereignty directly. Loses to an incumbent hosting at
OVHcloud.

**Published pricing retained as a deliberate differentiator.** Neither
competitor serves a founder with a credit card. Adequacy is bought by a DPO
with a budget line; RECOSA by an SME with no DPO at all.
---

## 4. Decision register

The load-bearing decisions. Each records what was chosen, what was rejected,
and why — the last being the part that matters.

### D-01 — Template-first document generation
*Aug 2026. Supersedes per-client LLM generation.*

The LLM builds and maintains **versioned templates offline** under review;
runtime does merge-field rendering, with the LLM reserved for genuinely
client-specific inserts.

Reasons, in priority order:

1. **Legal reviewability.** A lawyer can review a template once. A lawyer
   cannot review every document the platform emits. For a product whose value
   proposition is "this makes you compliant," this is close to decisive.
2. **Determinism.** Generation ran at temperature 0.3, so identical inputs
   produced different documents.
3. **Regulatory-update propagation.** You can only tell a client what changed
   if you know what is in their document.
4. **Omission risk.** An LLM can silently drop a required element; a template
   with fixed required sections cannot.

*Supporting evidence:* privacy policy review scores went from 30–40% to ~80%
precisely by constraining the prompt toward a fixed structure. The logical
endpoint of that trajectory is to stop paying a model to rediscover the
structure each time.

**Tiers:** Tier 1 pure template, no runtime LLM (RoPA — inventing processing
activities is actively wrong; DPA — Art. 28(3) clauses are prescribed; Cookie
Policy). Tier 2 template with ~10–20% LLM inserts (Privacy Policy, InfoSec,
BCP, Data Breach). Tier 3 genuine per-client assessment (DPIA — closer to the
gap engine than to docgen).

**Design rules:** block on missing required fields, visible placeholders for
optional ones; boolean conditionals only, no loops or nesting; materiality per
version (`minor` = silent, `recommended` = in-app flag, `required` = flag +
email); every generated document stamps `template_version_id` (cheap now,
impossible to retrofit); staleness nudges are content-free and escalate at day
7 and day 30 then stop, with every flag written to the audit trail.

**Open:** language scope. Templates are maintained per language, so four
languages is 4× maintenance forever. Decide FR/EN first vs all four rather than
drifting into it.

### D-02 — Single source of truth for obligations
*S23.*

Everything derives from `obligations.py`. Never maintain a parallel mapping in
another file — three of them existed and all three disagreed.

The distinction that fixed the scoring bug: **"which obligations should I check
when reviewing this document" and "which obligations does this document
actually satisfy" are different questions.** Hence `DOC_OBLIGATIONS` (wider
review set, reported) vs `DOC_SCORING_OBLIGATIONS` (primary `doc_type` only,
scored). The old code conflated them, so a complete privacy policy scored as
partial.

### D-03 — Reference data in Postgres, authored in Python
*S24. Deliberately reverses D-02's precedent for this data only.*

Vocabularies and the vendor catalogue live in Postgres tables, not Python
constants. Three roadmap items force it:

- The S41 scanner resolves domains to vendors **by query**, against a table
  growing to hundreds of rows.
- Labels need per-language translation; codes do not.
- S45 Enterprise taxonomies are per-workspace **by definition**, which a module
  constant cannot express.

Authoring still happens in Python: `inventory_seed.py` holds the content, emits
idempotent seed SQL, and is **never read at runtime**. `inventory.py` reads the
tables. Authoring wants a reviewable diff; serving wants a queryable table.

**Consequence:** vocabulary codes are **append-only**. Never rename or delete —
client rows hold them as plain text in `TEXT[]` columns, so a rename orphans
live compliance data and only the orphan check would notice. Retire via
`active = FALSE`.

### D-04 — Business rules as data, not comments
*S24.*

`catalogue_principles` stores the rules behind the catalogue defaults, with an
`audience` column separating client-facing statements from internal reasoning.
RLS filters on audience, so internal notes are unreadable from the client app
rather than merely unrendered.

**The stronger form of this rule: write principles as executable checks, not
prose.** The retention principle was encoded as a `self_check` rule — an
activity cannot both mark its retention statutory and carry a default — and it
immediately caught three Microsoft 365 activities written minutes earlier that
violated it. The prose version had been stated and violated in the same file.

Client-facing principles as of S24:

1. Catalogue values are **starting points, not findings**.
2. **Retention comes from the law, not the vendor.** Pre-fill only where the
   vendor genuinely determines the period (Google Analytics' 14 months is a GA
   setting). "5 years after end of employment" is Belgian social-document law
   and wrong for a French client.
3. **Processor by default, joint controller where arguable.** Meta Pixel and
   LinkedIn Insight Tag ship as joint controllers per *Fashion ID* (C-40/17);
   Google Analytics ships as processor with the counter-argument surfaced.
4. **AI features assumed off.** Copilot, Gemini and Slack AI seed as `none` and
   ask — assuming Copilot is on attaches AI Act deployer duties to a tenant
   that never touched it.
5. **An unanswered question is a gap, not an error.** Block only on
   contradiction.
6. **Deleting a system keeps its activities.** Swapping payroll providers must
   not erase the payroll RoPA row.
7. **Cookies recorded at vendor level** until the S41 scanner supplies names
   and durations.

### D-05 — EU sovereignty and the Brevo boundary

No CLOUD Act exposure anywhere. Brevo is limited to **content-free** nudge
notifications: compliance content — document bodies, ticket subjects,
categories, severities, regulation names — must never leave RECOSA by email.
Internal workflow messaging stays in-app (see S46).

### D-06 — RLS covers every operation, always
*Learned from three S21 incidents.*

Write all policies for a table together. A table with RLS enabled and no
policies denies everything silently; partial coverage fails in ways that take
days to find.

**The one intentional exception**, documented so a later audit does not "fix"
it: the S24 reference tables have SELECT-only policies. The **absence** of
INSERT/UPDATE/DELETE is the access control, and the service-role seed bypasses
RLS.

### D-07 — Sequencing by GTM priority

Commercial-launch essentials (deletion, billing, onboarding, audit) before
Advisory and Enterprise segment features. Multi-user for Professional before
billing. Advisory and Enterprise only after the commercial cluster is stable.

### D-08 — Sprint methodology

Small, single-purpose, coherent sprints with explicit scope-lock before
building. Honest scope assessment over optimistic commitment. Features deferred
cleanly rather than patched in. Full file replacements over diffs.

---

### D-09 — RECOSA is a compliance command centre, not a document generator
*Aug 2026. Reconstructed 4 Sept from session notes — original text lost.*

Generating a document is the start of an obligation, not the end of one. A
client needs to know what they adopted, when it took effect, what replaced it,
and which versions are now out of date because the law moved. None of that is
answerable from a folder of files.

This inserted the document register as **S27** and moved every sprint below it
by one, putting the beta gate at S33.

It also accepts a premise: **generated documents will never fully match a
client's design wishes.** That is what makes S43 theme-only — logo, primary
colour, footer, font — rather than an attempt at full layout control.

### D-10 — Templates carry semantics, not presentation
*Aug 2026. Reconstructed 4 Sept — original text lost.*

A template says "this is a level 2 heading", never "this is 14pt bold navy".
One template then serves every client theme, which is what keeps template-first
intact: a lawyer reviews one template, not one per client.

Two consequences acted on in S25 at no cost: a `theme` parameter threaded
through the renderer and every block renderer from the first line, unused until
S43; and a nullable `brand_profile_version` alongside `template_version_id`,
because a regenerated document differs on two independent axes and without both
"why does this look different from what we filed?" has no answer in the data.

### D-11 — Template bodies are markdown
*Aug 2026. Recovered 4 Sept — largely intact.*

Bodies are stored as **markdown text**, with all tabular content handled by
block renderers so markdown never has to express a table.

*Rejected — DOCX as the template.* Tempting: authoring in Word, native styling,
`docxtpl` exists for exactly this. Ruled out by D-10, because styling baked
into the file means either one template per client per document type — which
destroys template-first — or rewriting styles inside a `.docx` at render time.
It also makes version history a series of opaque zip archives, removing the
readable diff D-01's reviewability argument depends on, and forecloses HTML
output for clients who want to publish a policy on their own site.

*Rejected — structured JSON section list.* Maps one-to-one onto `python-docx`
calls, so styling is explicit and there is no conversion layer to debug. Lost
on two counts: authoring and reviewing a legal document as a JSON array is
unpleasant and the diffs are noisy, which cuts against the property D-01 needs
most; and it is the format most at risk under D-10, since nothing stops a
`color` key being added when one document needs a tweak, and once one has, all
subsequent ones will.

*Why markdown wins.* `##` is semantic and markdown can barely express anything
else, so D-10 is enforced by the format rather than by discipline. Diffs are
readable by a non-technical reviewer. In-app preview is cheap. HTML output
comes nearly free.

*The cost, accepted.* A markdown→`python-docx` converter plus a style map, and
markdown carries no information about *which* Heading 2 style. That style map
is where D-10's branding lives, so the work is not wasted — it is the same work
arriving earlier. Because tables are block renderers, the converter handles
only headings, paragraphs, lists and inline emphasis: a small closed set
written once, not an open-ended markdown implementation.

---

### D-12 to D-42 — LOST

**These numbers were used. Their text did not survive.**

`docs/SPRINT_LOG.md` was never committed to git. D-12 through D-42 were added
to a local copy across the S25, S26 and S26A sessions and are gone, except
where a working document happened to record them — D-42 and D-43 below were
recovered that way.

**Do not reuse these numbers**, and do not reconstruct them from chat
summaries. A summary records what was decided, not the rejected alternative,
and the rejected alternative is the load-bearing part. On 3 Sept 2026 a
correct decision (D-40) was nearly reversed by accident; what caught it was its
recorded *rejected alternative*, not its conclusion. A summary saying "decided
X" would not have.

Known from use, without their reasoning:
- **D-40** — `doc_type = "dpa"` unambiguously means the processor-side
  agreement. *Rejected: a second doc_type for the vendor side — two codes
  differing only in direction is the `"rop"`/`"ropa"` shape, and the vendor
  side is not a document at all.* (Reasoning survives because it was quoted in
  the 3 Sept session.)
- **D-41** — Annex I is left blank for the controller to complete on signature.
- **D-42** — clause text must be *verified* rather than trusted: counsel
  reviews a diff against the Official Journal.

---

### D-43 — commercial terms on the client's own contract are not scored

*Referenced by D-44 as its basis; the original entry did not survive.*

Where a DPA clause calls for a term between the client and THEIR customer —
a notice period, an assistance commitment — RECOSA supplies a defensible
default the client can edit, and does not score the answer.

It is their contract. A period they negotiate is a commercial choice, not a
compliance failure, and scoring it would tell a client they are non-compliant
for agreeing something lawful.

### D-44 — Annex III parts 2 and 3 get RECOSA defaults, editable, not scored

Clause 8(d) requires Annex III to set out the measures by which the processor
assists the controller, and the scope and extent of that assistance. The
closing paragraph of Clause 9.2 requires the further elements provided when
assisting with breach notification.

Neither has an S24 source: `security_measures` are controls, assistance is a
service commitment. They answer different questions.

*Rejected:* leaving them blank — emits a DPA that fails its own clauses.
*Rejected:* deriving them from `security_measures` — answers a different
question and would read as an assertion the client never made.

**Adopted:** a RECOSA-authored default the client edits, on the D-43 reasoning.
Part 3 is the more determinate of the two, since Clause 9.2(a)–(c) already
fixes the minimum content and the default adds only the routing.

**Not a `readiness()` check.** Columns landed in `migration_s26a.sql`:
`sub_processor_notice_days`, `dpa_assistance_text`, `dpa_breach_elements_text`.

### Correction 5 — Section I as first committed modified clause text

Clauses 1(b), 1(e), 1(f), 3(a), 3(b) and 3(c) carry "and/or Regulation (EU)
2018/1725" in the Official Journal with **no** `[OPTION]` markers. Only five
places in the whole instrument are marked choices: Clause 1(a), 8(c)(4),
9.1(b), 9.1(c), and the closing paragraph of 9.2.

Stripping the unmarked EUDPR references is a Clause 2(a) modification. It is
also self-defeating: the verification method is a diff against the OJ, so a
body containing authorised deviations can never diff clean and the reviewer has
to hold a mental list of which differences are acceptable.

Resolved by construction — the body is no longer transcribed at all.

### Correction 6 — Annex IV is emitted, not omitted

Annex IV is not used (Option 2 is taken), but Clause 1(d) makes Annexes I to IV
integral to the Clauses. An annex stating why it is empty reads better than a
dangling reference to one that is missing.

### Correction 7 — the sub-processor scoping was wrong twice over

First: `role` is not on `systems`. It is on `activity_systems`, because a
vendor can be processor for one activity and joint controller for another.

Second, and worse: filtering the whole inventory lists every vendor the client
uses, including those touching only their own controller-side data. That names,
in a signed contract, vendors which never see the customer's data — and each
name is one the controller may object to under Clause 7.7(a). **Over-naming is
not the safe direction.**

Correct predicate: systems joined to activities with
`controller_role = 'processor'`, excluding `_NON_RECIPIENT_ROLES`.

### File layout — the clause text is downloaded, not authored

- `templates/raw/dpa_scc_{en,fr}.oj.md` — the Annex of CELEX:32021D0915,
  committed unedited. Never hand-edited.
- `template_seed_dpa_patch.py` — applies six documented edits and asserts each
  anchor. Contains no clause wording: every resolved option is regex-captured
  out of the raw text and re-emitted.
- `templates/dpa_scc_{en,fr}.md` — generated. Regenerating reverts any hand
  edit silently, so the header says so.

**Why this beats a transcription (D-42).** A hand-typed transcription needs
100% verification. A downloaded file needs only the patch reviewed — six edits,
each asserted, none rewriting Commission wording. **Counsel reviews a diff, not
a contract.**

### Constraint — `.gitattributes` line endings

`templates/*.md text eol=lf`, and the same for `templates/raw/*.md`.

`body_from_file()` normalises defensively, but the attribute is the real fix:
with `core.autocrlf=true`, an LF-committed file arrives as CRLF on a Windows
checkout through nobody's fault, and the seed's line-ending check would make it
unrunnable there.

### Learning — a ✅ in a handover is a claim about belief, not about disk

`body_from_file()` was marked *written, parses* in the S26A handover. It was
not in `template_seed_lib.py`, and that file did not import `Path`. Two of the
four ✅ items in that handover were carried forward from intent rather than
from the file, and the third contained correction 5.

**Verify against the file, not against the handover** — including handovers
written by Claude at the end of a session.

### Carried forward from S26A, still unresolved

- **`activity_systems.role` vs `system_role` is unverified.** Noted in
  `template_store.py`'s adapter section. The sub-processor loader depends on
  it; a 400 on that select is the cause.
- **`registered_address` gets `"  \\n"` hard breaks in `build_values`.** In
  Annex I it sits indented under a numbered list item — eyeball the first
  render. *(Not observed as a problem in the 3 Sept generated DPA, but not
  specifically checked either.)*

---

### D-54 — `dpa_governing_law` does not exist and never did

Memory carried a fourth D-44 field. `DPA_FIELDS` deliberately shares no
jurisdiction fields: these Clauses are a Union instrument applying identically
in every Member State, and Clause 2(a) forbids varying them. Three columns, not
four.

### D-55 — `doc_type` stays `"dpa"`; the legacy intake is guarded, not renamed

An apparent collision was found between the templated DPA (client as processor)
and the LLM intake in `pages/documents.py` asking for "the company processing
data on your behalf" (client as controller). A rename to `dpa_processor` was
written and then reverted.

**D-40 had already decided this**, and its recorded *rejected alternative* is
what caught the error: a second doc_type differing only in direction is the
`"rop"`/`"ropa"` shape, and the vendor side is not a document at all — it is
discharged by holding the vendor's DPA and recording it against the system.
`"dpa"` is therefore unambiguous.

What looked like a collision was stale code. The intake is now guarded with
`and not use_template`, keeping it for the Advisory path, which has no
`client_id` and so no inventory to build Annex II from. Retirement is an S28
decision.

*The decision register earned its keep here. Without D-40's rejected-alternative
note, a correct decision would have been silently reversed.*

### D-46 — S26C lands before S27

S27 stamps and registers documents; one
stamped into a supersession chain with half-English annexes is harder to
unwind than one not yet generated. The problem also degrades with use.
*Rejected:* post-beta — the cost scales with the number of activities already
in the database.

### D-47 — client text is JSONB; catalogue text stays suffix columns

The
catalogue is RECOSA-authored with a fixed language set, so `name_en`/`name_fr`
is right there. Client data is per-client with a growing set, and suffix
columns would mean `ALTER TABLE` per language forever — the trap flagged for
S53. *Rejected:* suffix columns for consistency. Consistency of mechanism is
worth less than not migrating the table every time a language is added.

### D-48 — retention is not backfilled

Parsing "5 years (social documents,
Belgian law)" back into a number, a unit and a basis is the guesswork this
sprint removes, and a wrong retention period in a filed register is worse than
a blank one. Rows keep legacy text until a human confirms the structure.
*Accepted cost:* mixed structured and unstructured rows for as long as it takes
clients to revisit them, and `build_retention_cells()` must fall back whole.

### D-49 — retention has two phases, not one period

CNIL separates *base
active* from *archivage intermédiaire*; the two have different durations and
different bases. Payroll is active for the employment, then five years as a
social document. Collapsing them either overstates how long data is in use or
understates how long it is held, and Art. 30(1)(f) asks for envisaged erasure
limits — both errors are wrong answers. In a DPA it is worse than imprecise:
Clause 7.3 confines processing to the duration Annex II states, so the
understatement is a breach of the clause. *Rejected:* one period plus a
free-text qualifier — reintroduces the untranslatable prose.

### D-50 — retention basis codes name the KIND of reason, never the period.
Belgium is why: CDE art. III.86 requires accounting books kept seven years; the
law of 20 November 2022 extended tax and VAT retention to ten years from
1 January 2023, aligned with the fraud limitation period; VAT revision on
immovable property runs longer again. Published sources disagree because they
describe different obligations. A code reading "accounting — 7 years" would be
right under the CDE and wrong under the CIR. Hence `statutory_accounting` and
`statutory_tax_vat` are separate codes.

### D-51 — reference notes stay generic; citations deferred

A cited note is
RECOSA asserting what national law requires, inside a filed register, in a
product sold as a compliance tool — the same risk class as D-42, and it needs
counsel review before it ships.

### D-52 — `vendor_determined` is not a retention basis

Who set a period is
not why it is defensible. The catalogue already carries `retention_is_statutory`,
and the S24 catalogue principle — which caught three Microsoft 365 activities
minutes after being written — exists to stop vendor-set periods being filed as
the client's own basis.

### D-53 — translation is generated on save, and failure is not an error

A
widget inside `st.form` does not trigger a rerun (the S26 comment in
`pages/inventory.py` says so, which is why the system multiselect sits outside
it), so an on-demand button is impossible. The save therefore goes through with
the translation outstanding: the client's own text is what matters, and
blocking a save on an LLM call means the inventory form stops working whenever
Mistral is slow. *Accepted cost:* saves can quietly produce untranslated rows,
so the gap must be visible — currently the summary table, properly the task
register.

### D-56 — no privileged source language in the activity form

One column per
document language, side by side, and **no box is ever pre-filled from another
language**.

The first version made the client's UI language the primary input with the
others in an expander. It read as a master language, and worse: the primary box
fell back to the legacy column, so backfilled English appeared under a box
labelled NL. Saving would have written `{"name": {"nl": "human"}}` — the
database asserting a human confirmed an English sentence as Dutch, with the
Dutch register then rendering it. Found in testing, before any data was
written.

Consequences: legacy text whose language is unknown is surfaced as a warning
for the client to place, never guessed into a column; the translation source is
whichever column the client actually filled, so it varies per save; and editing
a draft *is* the confirmation, with no separate approve control to forget.

### D-57 — version numbers are assigned at ADOPTION, not generation.
Drafts carry `version = NULL`.

A version number is a public fact: it appears on the document, a data subject
may cite it, and the Belgian DPA guidance asks for policies to be dated and
version-numbered so a client can say which one applied when. If three drafts
consume v4, v5 and v6 and only the last is adopted, the published sequence
reads v3 → v6 and the gap is unexplainable. "We generated them and threw them
away" invites a question better not asked.

Consequence, and the reason this is not merely cosmetic: **discarding a draft
is now safe**. Nothing points at it and no number was spent, so
`delete_draft_document` can remove it and its storage object without leaving a
hole in the record.

Second consequence: it narrows the race in the old `register_client_document`,
which read the current version and inserted version + 1 with no atomicity. Two
concurrent generations computed the same number and both succeeded. Numbering
now happens rarely and deliberately, and a unique index closes what remains.

### D-58 — generation is not adoption, and the client supplies the date.
Generating wrote `is_current = TRUE`, so the register asserted a DPA was in
force from the moment it was produced, with an effective date RECOSA had
invented. For an unsigned contract that is simply false.

`adopted_at` (system, immutable, audit evidence) and `effective_from` (client
fact, editable) are separate columns. A policy approved on the 3rd and
published on the 15th applies from the 15th; a DPA countersigned last week
applies from last week, before it existed in RECOSA. Collapsing them makes
"what were we operating under in March" unanswerable, which is the whole reason
superseded versions are retained.

*Migration decision:* existing rows backfilled as `in_force`, not `draft`, so
no current client's gap score regressed. Only new documents acquire the step.

### D-59 — six register states, and NOT_GENERATED is not NOT_AVAILABLE.

| state | meaning | whose |
|---|---|---|
| `in_force` | adopted in every required language | — |
| `partial` | adopted in some | client |
| `draft` | produced, never adopted | client |
| `not_generated` | template exists, client has not produced it | client |
| `not_available` | **no RECOSA template in that language** | **ours** |
| `archived` | retired, nothing replaced it | client |

The two middle-red states look identical on a dashboard and are opposite
findings. Showing "not available in NL" as the client's failure blames them for
a template nobody has written.

Consequences: `not_available` renders blue, not red — red on a row the client
cannot act on reads as an accusation. `CLIENT_ACTIONABLE` is a table, not a
judgement each caller re-makes, because it is easy to get backwards and
expensive when it is. And `coverage()` **excludes** `not_available` from the
denominator, reporting it separately as `blocked_on_us`: a client's compliance
percentage must not fall because RECOSA has not written a Dutch template. That
is billing them for our backlog, and it is the kind of thing a competitor
would put in a comparison table.

**Correction, same session.** The first implementation excluded whole documents
whose EVERY language was unavailable, not individual languages. A client with
NL and FR documents, a French DPA in force and no Dutch template scored
`partial`, and `coverage()` counts partial as not covered — so a client who had
done everything available to them read **0 / 7, 0%**. The principle was right
and the code inverted it.

The test is not "is every required language in force" but "is every language we
can actually serve in force". Unavailable languages stay in the breakdown and
in the note, because the gap is real and should be visible — it is just not
theirs. `coverage()` gained `partly_blocked` for documents counted as in force
but still missing a language RECOSA cannot produce, so the headline figure is
not mistaken for full coverage.

### D-60 — `template_languages=None` means "not checked", not "none exist".
An empty set asserts RECOSA has no template; `None` says the lookup failed.
`document_status()` reports `not_generated` on `None` rather than claiming its
own gap, because telling a client we cannot help them on the strength of a
failed query is worse than telling them to generate a document they could.

Related: `pages/documents.py` still infers "no in-force template in that
language yet" by subtracting generated languages from the client's list. That
is a guess and it is sometimes wrong — it says the template does not exist when
the client simply has not generated it. `get_template_languages()` is the fact;
the message should be moved onto it.

### D-61 — compliance logic goes in pure modules; pages only render.
`register.py` has no Streamlit, no Supabase, no I/O. It takes plain data and
returns plain data; the caller fetches rows and picks a colour.

Two reasons. Portability: the logic deciding whether a client is covered should
not be entangled with the framework drawing the screen, so moving off Streamlit
is a rendering job rather than a re-derivation of compliance rules.
Testability: `document_status()` was exercised against seven awkward cases in a
second; the same logic as branches inside a page can only be tested by
clicking, which means it is not tested — and it decides what a client is told
about their own compliance.

**Scope:** applied to new register logic only. Retrofitting the whole app is
its own sprint, not something to absorb here.

### D-62 — the status guard lives in the store, not the page.
`delete_draft_document` refuses anything not in `draft` status. `pages/gap.py`
already writes to `client_documents` outside the store layer, so a check living
only in a page is a check that can be walked around — and the rows it protects
are the accountability record that retention and legal hold exist to preserve.

Deleting a draft also removes its storage object. Deleting the row alone would
orphan the file: invisible in the product, still stored, still the client's
personal data. The `documents` generation-log row is deliberately KEPT — that a
generation happened is true whether or not its output was retained — and an
audit event records the discard.

### D-63 — legal hold set and release are audited

Adoption, archiving and draft deletion wrote audit events from the start.
Legal hold did not, and it is the one where the trail matters most.

A hold is a statement about live litigation or an investigation. Setting one
says the document matters to a live matter; **releasing one is what allows it
to be deleted.** If that decision is later questioned, the absence of a record
is the problem — nobody can show who decided, when, or on what basis, and
spoliation arguments turn on exactly that.

Worse, and self-inflicted: `hold_set_on` is cleared on release so the next hold
ages from its own start (S57). That meant releasing a hold erased the fact it
had ever existed — a document held for two years became indistinguishable from
one never held. `set_legal_hold` now reads the row BEFORE updating, so the
duration survives into the event.

Reasons are **optional on both sides**. This control is used during a live
matter and a required field there is friction at the worst possible moment. But
the reason is recorded whenever given, and the release event carries the reason
the hold was originally placed, so the two read as one story rather than as an
unexplained reversal.

### D-64 — timestamps are written offset-aware and displayed in Brussels time

`datetime.utcnow()` returns a NAIVE datetime that claims to be UTC without
recording it. Written to a `timestamptz` column with no offset, Postgres
interpreted it as the connection's timezone: a 17:04 UTC event was stored and
displayed as 17:04 while Brussels was on 19:04.

Fixed at **six** call sites in `database.py`, not the two that were visible.
The other four — `approved_at`, `read_at`, `detected_at`, `kb_ingested_at` —
had the identical defect and leaving them would have been the divergence
pattern.

Rows written before the fix cannot be reliably corrected: the offset they were
meant to carry was never recorded. `_local()` assumes UTC for naive values,
which is the best available answer rather than a correct one.

Display is a separate choice. Streamlit runs server-side, so there is no
browser timezone to fall back on. `DISPLAY_TZ_NAME = "Europe/Brussels"` for
everyone, **labelled in the caption** — a mislabelled timestamp in an audit log
is worse than an honest one in the wrong zone, because an auditor comparing it
against an email header needs to know which zone they are reading. Falls back
to UTC with the label changed to match if `tzdata` is absent from the image.

*Carried:* this becomes a per-client setting the first time there is a client
outside Belgium. One constant, one place.

### D-65 — `event_subtype` means two different things

| event_type | what event_subtype holds |
|---|---|
| `document` (S27) | the ACTION — `adopted`, `hold_set`, `draft_deleted` |
| `document_generated` (pre-S27) | the DOCUMENT — `dpa`, `ropa_controller` |

Reading it as one produced **"Dpa"** in the Action column of the activity log.
Neither writer is wrong on its own; they were written months apart and never
compared.

Resolved at **display time** via an `ACTION_IN_SUBTYPE` set, not in the data.
Audit rows are immutable by design, and correcting this in the table would mean
rewriting history to make a column render better.

*The general shape, and it is new:* **a column whose meaning depends on a
sibling column.** Not the same as the `if use_template:` family — nothing here
was left behind by a widening assumption. Two writers independently chose a
reasonable meaning for a shared field, and neither could see the other. Worth
watching for wherever a `*_subtype` or `*_kind` column exists.
---

### D-66 — "Zero US cloud exposure" is not true today. Fix the copy this week.

recosa.eu claims **zero US cloud exposure**. It does not hold:

| Layer | Provider | Jurisdiction |
|---|---|---|
| Application | Streamlit Community Cloud | Snowflake, US |
| Database, auth, storage | Supabase | Delaware corporation, **and Frankfurt runs on AWS** — two layers |
| Monitoring cron | GitHub Actions | Microsoft, US |
| Vector store | Qdrant Cloud `eu-central-1` | EU region, but AWS |
| LLM | Mistral | French — clean |

Supabase Frankfurt gives **data residency**, which is what most buyers mean
when they ask. It does not give **sovereignty**: the CLOUD Act reaches US
providers over data they control regardless of where it sits. Data residency
tells you where the bits are; sovereignty tells you which legal system can
compel access.

**This is the most urgent item in this log**, ahead of the outage that surfaced
it. An outage is embarrassing. A marketing claim a prospect's counsel can
disprove in one search is a different order of problem — and RECOSA's buyers
are compliance people who check exactly this. It also sits badly with what
RECOSA sells, which is helping clients avoid unsupportable compliance
statements.

**Adopted, immediately:** change the copy to a claim that is true and
verifiable — EU data residency, data in Frankfurt — and keep it until the
infrastructure supports the stronger one. An afternoon on the Framer site.

*Rejected:* leaving the claim up until the migration lands. The migration will
not complete before beta on any honest estimate, and every week the claim
stands is a week a prospect might act on it.

*Note:* this is a known pattern, not an unusual failure — a B2B SaaS picks
Supabase for the developer experience, grows to enterprise customers, and finds
that Frankfurt-on-AWS fails a Schrems II analysis.

### D-67 — Move to European infrastructure BEFORE beta, not after

Two outages in two months, neither caused by RECOSA, both taking the client app
and the admin back-office down together — the Starlette break and the
8 Sept apt failure. That alone would argue for moving. D-66 decides it.

*Rejected:* migrating after beta. Every client onboarded on the current
infrastructure is a client whose data has been processed there, and a later
migration is a migration with live clients on it — with a cutover, a support
burden, and a conversation about why their data moved.

**Consequence for the roadmap:** this precedes S33 (the beta gate). It is not
optional work that fits if there is time.

**Candidates** consistent with the positioning: Scaleway, OVHcloud, Hetzner,
Clever Cloud. `packages.txt` disappears as a failure mode — LibreOffice becomes
an image layer RECOSA controls rather than an apt call against Debian mirrors
inside someone else's container.

### D-68 — Self-host Supabase; do not replace it

Supabase is open-source and the whole stack self-hosts on EU infrastructure
with full feature parity — **the same `supabase-js` client keeps working.**
Auth, RLS, storage and PostgREST stay exactly as built. What changes is who
operates the servers.

*Rejected — Nhost.* Incorporated in Sweden, which fixes the corporate-HQ half,
but its managed cloud runs on AWS `eu-central-1`, so the jurisdiction problem
remains. It also swaps PostgREST for Hasura GraphQL, which would mean
rewriting every database call in RECOSA. Worse outcome, far more work.

*Rejected — Appwrite Cloud.* Frankfurt region, but US/Israeli company. Same
questions, and a different data model.

*Rejected — Aiven.* Genuinely European and does managed Postgres, but it is a
database service, not a Supabase replacement: no auth, no storage, no
RLS-over-REST. Would mean building three subsystems RECOSA already has.

*Rejected — rewriting the data layer.* Auth, storage, RLS and PostgREST at
once. Not a pre-beta undertaking, and probably never worth it.

**Consequence:** the app migration and the database migration are one piece of
work on one host, not two projects. That is what makes D-67 achievable before
beta.

### D-69 — The UI is reworked in Streamlit, not rewritten

The interface needs real work, and self-hosting invites the question of why not
rebuild the front end properly while moving.

**Not before beta.** A rewrite is months and puts the beta date into next year.
Self-hosted Streamlit plus a serious UI pass is weeks.

**D-61 is the hedge that makes a later move cheap.** Every compliance verdict
now lives in pure modules with no Streamlit in them — `register.py`,
`obligations.py`, `template_store.py`. A future front end is a rendering job,
not a re-derivation of the rules. That discipline was adopted for testability;
it also happens to be the exit route.

Recorded so the question is not reopened at a bad moment.

---

### D-70 — Document generation filters retrieval by regulation. S31 stays at 31.

Measured 8 Sept 2026, nine queries across four regulations, seven clean.

`retrieve()` filtered on language, country and doc_type but **not on
parent_regulation**, so all six regulations competed on semantic similarity
alone. Collection mix: EU AI Act 38.9%, GDPR 27.3%, NIS2 15.4%, EAA 8.2%,
Consumer Rights 7.4%, ePrivacy 2.8%.

Both failures were NIS2, and neither is a ranking bug:

| Query | Returned | Why |
|---|---|---|
| "What are the incident reporting deadlines?" | 3/3 EU AI Act | Art. 73 AI Act is serious-incident reporting, and the AI Act is 39% of the collection |
| "Do I have to tell anyone if we get hacked?" | 3/3 GDPR | Art. 33 breach notification is a defensible answer to that question as asked |

The third NIS2 query, using NIS2's own vocabulary ("supply chain security
measures for essential entities"), returned 3/3. **NIS2 wins when the language
is distinctive and loses when the concept is shared across three regulations.**
Not a volume problem.

**The two callers need opposite behaviour.**

*Chat* — the ambiguity is real and should be preserved. A client asking about
being hacked may genuinely need the GDPR answer, and returning it is correct.

*Document generation* — there is no ambiguity to resolve. When S29 generates a
NIS2 breach procedure, the regulation is known before the query is sent.
Retrieval was never told, so it guessed, and on the shared concepts it guessed
wrong.

**Adopted:** a `regulations` parameter on `retrieve()` and
`retrieve_from_qdrant()`, defaulting to `None`. Chat is unchanged. Document
generation passes the regulation it is generating for. **Filtered, not
re-ranked** — a NIS2 document must not be able to cite the AI Act at all,
however well the chunk scores. Supplementary guidance is filtered too, since
EDPB and ENISA material carries the regulation it interprets and a NIS2
document pulling EDPB guidance on GDPR is the same error one layer down.

Roughly twenty lines, plus `ensure_payload_indexes()` — `PayloadSchemaType`
was imported and never used, so `parent_regulation` may have had no index and
every filtered query would have scanned.

**S31 is NOT brought forward.** Regulation-aware *allocation* — splitting
`top_k` across regulations by relevance — addresses ranking quality in the
genuinely ambiguous chat case. Different problem, less urgent, and not what
gated S28, S29 and S30.

*Rejected:* moving S31 ahead of S28 on the raw 7/9 count. The count measured
the wrong thing. Two sprints of work were avoided by reading why the failures
happened rather than how many there were.

---

### D-71 — The Privacy Policy is Tier 1. No LLM.

The roadmap called S28 "Tier 2, first LLM inserts". It did not need them.

Art. 13 and 14 prescribe the content, and after S26, S26C and S28 part 1 every
prescribed item is structured data: purposes, bases, categories, recipients,
transfers, retention, and where the data came from. **A privacy policy is the
controller register rendered for a public audience** — same source, different
reader.

The evidence pointed the same way. This document went from 30-40% to 80% review
scores by constraining toward fixed structure. The reading is that constraint
produced the gain, and the remaining 20% is more constraint rather than better
prose.

*Consequence:* the first genuine LLM inserts move to **S29** (InfoSec, BCP),
where content varies by organisation rather than by data.

*Rejected:* generating the prose per client. It would reintroduce the review
burden template-first exists to remove, for sections whose wording is
prescribed anyway.

### D-72 — Data subject rights are conditional on the legal basis

Rights are **not universal**, and a template listing them all is wrong:

| Right | Applies when |
|---|---|
| Withdraw consent (Art. 7(3)) | consent is a basis for at least one activity |
| Object (Art. 21) | legitimate interests or public task |
| Portability (Art. 20) | consent or contract, processing automated |
| Access, rectification, restriction | always |
| Erasure (Art. 17) | qualified — not available against a legal obligation |

A policy promising portability of records held under a statutory retention duty
is a promise the client cannot keep, in a published document. Where any
activity relies on legal obligation, the template says plainly that some data
cannot be deleted, that the client will say which and why, and that everything
not caught is deleted.

Implemented as `rights_in_play()` over the activity set — an executable check,
not prose, per the S24 constraint. Verified against five basis combinations.

### D-73 — `data_source` and the Art. 14 disclosure

Nothing in the inventory recorded where personal data came from. Fifteen
vocabularies, none of them this.

Without it every generated policy silently discharges **Art. 13 only** — the
"you gave it to us" case. Wrong for most SMEs: an employee's emergency contact,
a supplier's accounts contact, a referred prospect and a bought list are all
Art. 14, and almost every client has at least one.

Ten codes, `data_source_codes TEXT[]` on `processing_activities`. An array
because one activity routinely holds data from several sources — an HR record
carries data from the employee AND their referees, and both must be
disclosable.

`metadata.art14` marks the nine codes that trigger the disclosure;
`metadata.public` marks the two that also answer Art. 14(2)(f), which asks
specifically whether the source was publicly accessible.

**Empty means NOT RECORDED, never "from the data subject".** Same shape as
D-60: a policy must not assert Art. 13 on the strength of a blank field. The
inventory form says so where a source is missing.

Rendered per activity, as a line under the table and only where it applies. A
column that is empty for four rows in five teaches the reader to ignore it.

### D-75 — Interface language and document languages are different questions

`pages/inventory.py` read:

```
lang = session_state["ui_language"] or client["document_languages"][0]
```

Nothing ever set `ui_language`, so it fell through to the first DOCUMENT
language — and a client whose documents are produced in NL and FR saw their
activity table rendered in Dutch while every label around it was English. The
comment in that file admitted the compromise: the first document language was
"the closest available signal" until a user language column existed.

- **UI language** — what the person reading the screen prefers. One value, per
  user, a profile setting.
- **Document languages** — which languages this client's documents are produced
  in. A list, per client, driven by who the documents are for. *"I want this
  policy in EN and DE" says nothing about what language the person configuring
  it reads.*

`profiles.ui_language`, CHECK-constrained, **defaulting to `en` rather than to
anything derived** — a default borrowed from a different question is how this
went wrong the first time. No selector until S32B provides a profile page, so
it is English for everyone today, which is correct.

*Related defect, same root:* the save handler wrote the legacy `name` column
from `_i18n[_source]`, where `_source` is the first document language with
content. A client who filled NL and left EN empty had their legacy column
overwritten with Dutch, and the activity dropdown — which read that column
directly — showed Dutch. The legacy columns are a FALLBACK, not a copy of
whichever language was typed first: they now prefer English, then their
existing value.

### D-76 — Re-saving confirms a draft translation

The caption says "edit or re-save to confirm". Re-saving did nothing: the
promotion to `human` was conditional on the value having CHANGED, so an
untouched draft stayed a draft however many times it was saved.

Any text in a box at submit is the client's, whether they edited it or not.
The drafting runs after that loop and marks what IT fills as
`machine_unreviewed`, so a fresh draft is not confirmed by the save that
created it — but the next one confirms it, which is what was promised.

### D-74 — Recipients are described by the capacity they act in

The first version told the reader that every named recipient "acts on our
instructions and may not use your data for their own purposes". True of a
processor. **False of a joint controller, about a named company, in a published
notice.**

The role is on `activity_systems`, not on `systems` (S24) — a vendor can be a
processor for one activity and a joint controller for another. Where a vendor
holds both across activities the **stronger role wins**: describing a joint
controller as acting only on instructions is a misstatement, whereas the
reverse is merely incomplete.

The table carries an "in what capacity" column, and a paragraph — conditional
on a non-processor existing — explains that a joint controller has its own
notice and its own responsibilities, and that rights may be exercised against
either party (Art. 26(3)).

*Note:* this publishes the client's role classification to the world. The S24
catalogue ships Google Analytics as processor with the counter-argument
surfaced, and *Fashion ID* (C-40/17) makes the joint-controller reading live
for embedded third-party tags. Higher stakes here than in a register.

### Known gaps, declared rather than hidden

- **Art. 13(2)(e)** — whether providing the data is statutory or contractual,
  and the consequences of not providing it. No field exists.
- **Art. 13(2)(f) / Art. 22** — automated decision-making. No field. Deferred
  with S51.

Both are flagged in the template's FOR COUNSEL block. Inventing a field would
be a placeholder in different clothing.

---

### D-77 — Obligation verdicts have a precedence order

Two evaluators already existed: a profile questionnaire (21 obligations) and
LLM analysis of a document (16). That left most of the catalogue unevaluated,
and one obligation — `gdpr_04`, "DPO appointed if required" — where RECOSA
asked the client a question it could answer from the client record it already
held.

S29 does not add a third parallel verdict. It adds the missing one and imposes
an order on all of them:

| | source | why it outranks the next |
|---|---|---|
| 1 | `derived` | RECOSA computed it from the inventory |
| 2 | `document` | the register says a document is in force |
| 3 | `analysed` | a model read the document and judged it |
| 4 | `declared` | the client answered a question |
| 5 | `none` | nothing recorded |

**Each level is harder to be wrong about than the one below.** A DPA recorded
against every processor system is a fact; a client answering "yes, we have
DPAs" is a claim.

Where a derivation exists, **the profile question should be retired** rather
than both being kept. Two answers to one question is the divergence pattern,
and the point of a source of truth is that there is one.

*A derivation says what the inventory RECORDS, never what is true.* "Every
processor system has a DPA recorded" is a statement about the register — and
it is the statement an auditor wants, because they can check the register
against reality themselves. Every derived verdict therefore carries the
evidence it was computed from.

Two derivations are deliberately conservative. `gdpr_17` never returns
compliant: RECOSA cannot see whether an Art. 26 arrangement exists, and saying
so would assert a document nobody has seen. `gdpr_20` reports coverage and
states outright that whether measures are *appropriate* under Art. 32 is a
judgement it does not make.

### D-78 — The task register derives its state and stores only its history

A task register can hold rows or compute them. Neither alone works.

**Stored rows drift.** A task whose underlying gap was fixed elsewhere — the
translation confirmed, the document adopted, the retention structured — sits
there claiming to be open until something reconciles it. Reconciliation is
where these systems rot.

**Derived rows cannot remember.** Who is working on it, that it was dismissed
and why, that it was found in March and closed in April. That last one is the
entire audit value.

So the open list is **derived from its producers on every read**, and only the
history is stored. A task is open because a producer still reports it, not
because a row says so. When the producer stops, `reconcile()` writes the
closure — *the producer stopping IS the closure* — and that event survives the
task, which was never stored.

`finding_key` is the stable identity of a finding, producer plus subject:
`translation:activity:<uuid>:purpose:fr`. Without it a finding that disappears
and returns cannot be told from a new one, and the history degenerates into
unrelated events. It must contain nothing that changes while the finding is the
same thing — not a name, not a date, not a count.

*Consequence:* a dismissal holds only while the finding is **continuously**
reported. If it disappears and comes back, the dismissal does not carry over —
the situation changed, and a decision about the old finding should not silently
apply to the new one.

*Weakness, recorded rather than hidden:* `readiness()` returns prose, so
`inventory_gaps` builds its key from the message text. Reword a message and the
old finding closes and a new one opens. First thing to replace if `readiness()`
ever returns structured findings.

### D-79 — Not every obligation is answered the same way

Five kinds, resolved per obligation in `response_kind()` — a classification,
not a rendering decision, so it is testable rather than living in the page.

`derived` (7) · `document` (16) · `acknowledge` (3) · `tracked` (0, awaiting
S50) · `statement` (28).

Forcing one shape on all 54 is what makes compliance tools feel like paperwork:
an obligation RECOSA can answer, one that needs a document, and one that needs
a person to confirm they did something are three different questions, and
asking them the same way makes two of them wrong.

An acknowledgement is **a name and a date, or nothing** — enforced by a CHECK,
because an unattributed tick is not evidence of anything. `not_applicable`
requires a reason for the same reason, and both live in the database rather
than the page, since the page is not the only thing that writes there.

**No `infosec_policy`.** Seven of the ten Art. 21(2) areas are already
operational obligations, so the document would be assertions over data RECOSA
does not hold. It becomes worth writing once this register holds a statement
against each of those seven.

---

## 5. Constraints and gotchas

Hard-won. Each cost real debugging time.

### PostgREST
- **No `GROUP BY`.** Aggregate in Python; convert to a Postgres RPC at scale.
- **Partial unique indexes cannot serve as `ON CONFLICT` arbiters** (error
  42P10). Use a real `UNIQUE` constraint.
- **`st.query_params.pop()` does not exist** on `QueryParamsProxy`. Use a
  guarded `del`.

### Postgres
- `UNIQUE NULLS NOT DISTINCT` requires **Postgres 15+**. Without it, NULLs are
  distinct and duplicate global rows slip through the constraint that matters
  most.
- Migrations must be idempotent: `DROP CONSTRAINT IF EXISTS` before adding.
- Service-role client (`get_supabase_admin()`) for writes that must bypass RLS.

### Streamlit
- **Streamlit Cloud reinstalls from `requirements.txt` on every reboot** —
  including reboots triggered by merely saving a secret. An upstream release
  can take both apps down at an arbitrary moment.
- `starlette` is pinned `<1.4`: Starlette 1.4 added a required
  `thread_minimum_size` kwarg to `GZipResponder.__init__()` that Streamlit's
  subclass does not pass, producing 500s on health checks before any app code
  runs. **Remaining packages are still unpinned. Pin before beta.**
- `database.py` uses lazy Streamlit imports (`_st()`) because a module-level
  `import streamlit` broke the GitHub Actions cron.
- Navigation `PAGE_CONTEXT` must key on `pg.url_path`, **not** `pg.title` —
  titles are display strings and the Support title becomes "Support (2)" when
  replies are unread.
- `st.data_editor`'s session-state delta uses **positional** indices that
  survive across reruns. Diff by ID against the returned frame instead; see
  `inventory_store.diff_by_id`.

### Brevo
- **Click tracking cannot be disabled on transactional sends** (campaigns
  only; long-standing refused feature request). Links are rewritten through
  `sendibt3.com`. Mitigation is anonymous tracking in Brevo settings — clicks
  counted but not linked to a contact.
- Reply notifications throttle on the 0→1 unread transition, and **the unread
  check must run before the insert** or the new message is itself the unread
  one and every reply looks like a repeat.

### Ingestion
- EUR-Lex blocks automated fetching. Manual PDF download → Colab upload.
- Qdrant collection is `regulations`, not `complai_kb`. Needs
  `QDRANT_COLLECTION` in Streamlit secrets.

### Codebase hygiene
- A global find-and-replace on one file while leaving 13 call sites intact
  creates a self-consistent but broken definition that **fails loudly at
  module-level imports and silently inside bare `except` blocks for weeks**.
  Bare `except` blocks are a debt item.
- Admin BO auth lives entirely in `admin_app.py`; pages in `pages_admin/` must
  not carry their own guards.
- Cruft accumulates — unused packages, duplicate admin modules. Clear at sprint
  boundaries.

### Added Sept 2026

**A condition that reads a field is a dependency on that field continuing to be
written.** Six instances so far, all the same shape — a change made where the
name matched rather than where the behaviour lives:

1. The templated preview block in `pages/documents.py`, written in S25 when
   `cookie_policy` was the only templated document, described the cookie vendor
   list and called `_load_vendor_rows` unconditionally. S26 added two registers
   and S26A a DPA; all three inherited a caption about systems "marked as
   setting cookies" on documents that read neither.
2. The legacy `dpa` LLM intake, asking for a vendor name to satisfy an
   obligation that D-40 had made operational.
3. `seed_from_catalogue`'s guidance note tested `retention_period` — once the
   catalogue stopped writing it, the branch would have fired for *every*
   seeded activity.
4. The S27 adoption panel was added to the LLM generation branch only, so every
   templated document silently had no way to be put in force.
5. A blanket replace of `.order("created_at")` in `database.py` hit all seven
   call sites; five belonged to other tables that legitimately have that column.
6. Declaring an `st.Page` without adding it to `st.navigation` — fails
   silently, no error, just an absent link. `PAGE_CONTEXT` is a third place.

**When a doc_type joins `TEMPLATE_DOC_TYPES`, check every `if use_template:`
branch.** They describe whichever document was there first.

**Streamlit: a button nested inside a button-gated block can never fire.**
Streamlit reruns the whole script on every interaction. A block gated on
`if generate:` is True for exactly one run; clicking a button inside it starts a
new run where `generate` is False, the branch never executes, and the panel
disappears. Same family as widgets inside `st.form`. Controls belong in sections
that render on every run.

**Streamlit: a module in `pages/` must not share a name with a root module it
imports.** `pages/register.py` importing `register` resolved to itself, because
Streamlit puts a page's own directory on `sys.path`. Silent until runtime, and
the traceback points at the import line rather than at the collision.

**Do not nest `st.columns` inside an already-narrow column.** Two buttons placed
inside the narrowest of six left the second with nowhere to render, and it did
not appear at all.

**`datetime.utcnow()` returns a naive datetime that claims to be UTC without
recording it.** Written to a `timestamptz` column with no offset, Postgres
interprets it as the connection's timezone. Use `datetime.now(timezone.utc)`.
Rows already written cannot be reliably corrected — the offset they were meant
to carry was never recorded.

**`save_activity` sends every allowlisted column, `None` where absent.** Fine
for nullable columns, fatal for `NOT NULL` JSONB ones. `diff_by_id` guards with
`if c in edited_df.columns`; `save_activity` does not.

**Structured data can be half-set in ways prose cannot.** A value with no unit,
a unit with no value, an unrecognised code. Seed self-checks gained rules for
each; a half-set period renders as a bare number or vanishes.

**A column whose meaning depends on a sibling column** (D-65). Not the same as
the list above — nothing was left behind by a widening assumption. Two writers
independently chose a reasonable meaning for a shared field and neither could
see the other. Watch for it wherever a `*_subtype` or `*_kind` column exists.

**A state change the interface does not show is indistinguishable from data
loss.** Retiring rather than deleting protects the data. It does not protect the
person looking at the screen, and was never meant to.

**`packages.txt` makes availability depend on Debian mirror health inside
someone else's base image.**

8 Sept 2026: both apps down. `apt-get` failed on an expired
`bullseye-security` release file in Streamlit Cloud's container — nothing to do
with RECOSA's code, unfixable from the repo, and unaffected by rebooting.
Platform-wide; other apps reported the identical error the same morning.

`packages.txt` contains one line, `libreoffice`, and it is genuinely needed:
`document_generator.py` shells out to `soffice` for both PDF and ODT
conversion. So it cannot simply be deleted.

Two consequences to act on:

1. **PDF/ODT conversion has no fallback.** `convert_docx_to_pdf` raises
   `RuntimeError` when `soffice` is absent. A system-package failure therefore
   takes out document delivery rather than one output format. DOCX and XLSX are
   pure Python and would survive — the code should let them.
2. **Second infrastructure outage of this class**, after the Starlette break.
   Both took both apps down at once, and neither was caused by RECOSA. See the
   hosting question below.

### Streamlit session state — three failures in one hour, 8 Sept

All three surfaced while entering data through the S26C inventory form. Each
looked like a different bug and all three are the same mechanism.

**`value=` is IGNORED once a widget key exists in session state.**
The per-language name and purpose boxes rendered empty on first load,
registering their keys with empty values. After a save the freshly drafted
translations were passed as `value=` and silently discarded — the boxes stayed
blank while the database held all three languages, correct and complete.

Self-perpetuating and destructive: on the NEXT save an empty box took the
clear-on-empty branch, deleting the translation, which the drafting then
regenerated. **Every save destroyed and rebuilt the same text**, which is why
it never left `machine_unreviewed` no matter how many times it was saved.

Fix: drop the per-language widget keys in the save handler so they
re-initialise. Any widget whose `value=` is expected to change after a rerun
needs its key cleared, or it will not.

**You cannot assign to `session_state[k]` when `k` is a widget key
instantiated in the same run.** It raises `StreamlitAPIException`. The save
handler now writes `inv_act_keep`, which the selectbox reads as an `index=`,
leaving the widget's own key untouched.

**A button nested inside a button-gated block can never fire** — recorded
earlier with S27, same root cause: the branch is True for exactly one run.

*The pattern:* Streamlit's session state takes precedence over the arguments a
widget is called with, in both directions. Anything that needs to change
programmatically after a rerun has to go through a key the widget does not own.

### Chesterton's fence — twice in one session

**The selector `pop()` was a workaround, not sloppiness.** The activity form
cleared `inv_act_select` after every save. It looked gratuitous and was
removed; it existed because assigning to that key raises. The removal produced
the exception the `pop()` had been avoiding.

**The nesting constraint was documented at the top of the file it governs.**
`template_renderer.py` states that conditionals do not nest and why. S28 nested
twice anyway.

Both are the same error: existing code doing something that looks needlessly
indirect, where the indirection is load-bearing. **When code is oddly shaped,
find out why before straightening it.**

### Note on attribution

Five bugs in the inventory form in one hour, four of them introduced in this
session. The form has accumulated per-language columns, two-phase structured
retention, a source multiselect and translation-on-save, all on a layout built
for a flat activity record.

Each fix worked. The reason they kept coming is that the page now does
considerably more than it was designed to. **That is the argument for S32B**,
and it is a better one than "the interface needs polish".

Also worth recording: two of the three friction points reported by the user
were real bugs and only one was framework behaviour. Reaching for "that is
just Streamlit" was the wrong instinct twice.

**An absent value has no status to read, so a check built on status cannot see
it.** Third instance this session.

1. **D-60** — `template_languages=None` means "not checked", not "none exist".
2. **`data_source_codes` empty** means "not recorded", never "from the data
   subject". A privacy policy must not assert Art. 13 on a blank field.
3. **The task register was blind to missing translations.** The producer read
   `translation_status`, which only exists for text that HAS been drafted. An
   activity with no French text at all produced no finding — so the task list
   said "nothing outstanding" to a client whose French policy was rendering
   English.

The third is the worst of the three because it was **reassuring**: an empty
task list is read as good news. And the missing translation is the more serious
of the two findings — an unconfirmed draft still renders in the right language,
whereas a missing one falls back and the document silently carries text the
reader cannot read.

**Where absence is meaningful, check for the absence, not for a marker of it.**

**A wrong obligation id fails silently.** Every set and dict keyed by
obligation id — derivations, acknowledgements, tracked — classifies an unknown
id as the default and reports nothing. `ai_04` was written where `ai_01` was
meant and the only symptom was an obligation getting the wrong control.
`obligation_register.check_ids()` returns ids named in the module that are not
in the catalogue; empty is the pass.

**The EEA test is a country list, not `country != "EU"`.**

The inventory stores real country codes. A test of `!= "EU"` treated `BE` as a
third country and would have told a Belgian client their Belgian payroll
provider was an international transfer — **a Chapter V finding, in a published
privacy policy, about processing that never leaves the country.** It had not
surfaced only because the seeded systems were recorded as `EU`.

One definition in `obligation_register._EEA`, imported by `template_privacy`.
The UK is deliberately outside: adequacy makes a Chapter V transfer easy to
justify, not something other than a transfer. An unrecorded country counts as
inside — absence of a country is an inventory gap that `readiness()` already
reports, not evidence of a transfer.

**Conditionals do not nest, and `template_renderer.py` says so at the top of
the file.**

S28 nested twice — `has_non_processor` inside `has_recipients`,
`has_public_source` inside `has_art14`. The non-greedy match ends the OUTER
conditional at the INNER closing tag, so the leftover markers survive into the
document.

The generator's unresolved-syntax warning caught it. Without that check a
published privacy policy would have carried `{{#if:has_non_processor}}` in its
body. The second nesting had not fired yet and would have failed identically
the moment a public source was recorded — a latent instance of the same bug.

The constraint is deliberate and stated: nesting is where template languages
become programming languages, and these bodies are reviewed by lawyers rather
than developers. **The condition belongs in the code, where it can be tested.**
Both were flattened by computing flags that imply their parent.

*The constraint was written where it should be. It was read past.*

**A ✅ in a handover is a claim about what was believed, not about what is on
disk.** Two of four ✅ items in the S26A handover were carried from intent
rather than from the file. Verify against the file — including handovers
written by Claude.

---

## 6. Commercial model

*Effective when S40 ships.*

| Plan | Monthly | Credits | Annual | Top-up |
|---|---|---|---|---|
| Starter | €49 | 100 | ~€490 | €0.40/credit |
| Professional | €149 | 500 | ~€1,490 | €0.25/credit |
| Enterprise | Contact us | — | — | — |

Annual is ~15–17% off, framed as "2 months free". Credits refresh **monthly
even on annual billing**, to prevent hoarding and dumping. Top-ups price at the
standard per-credit rate regardless of plan term, valid 12 months. Upgrade
monthly→annual any time with proration; downgrade only at period end.

7-day free trial → 7-day read-only extension → data deletion at day 14.

**For Starter and Professional the user *is* the company** — no client
selector. The multi-client selector is Advisory-only (S44).

---

## 7. Open questions

| Question | Blocks | Notes |
|---|---|---|
| ~~Does S31 come before S28?~~ | — | **Resolved 8 Sept: no. D-70.** Document generation needed a regulation filter, not regulation-aware allocation. |
| Task register — which number? | S55, S57, S26C | Three sprints depend on it. Currently unnumbered. |
| Systems grid purpose granularity | S56 | `st.data_editor` has nowhere to review a per-language draft. Detail form, or accept single-language, or drop from the Cookie Policy. |
| Retention basis citations in `note_*` | — | D-51 deferred them. Needs counsel review before RECOSA asserts national law. |
| Belgian DPA cookie guidance + 5-year figure | S27 | Recorded from a working note, not a checked primary source. **Verify before it becomes a client-facing default.** |
| Rolling retention start dates | S55 | "3 years from last contact" needs `retention_starts_from`, not a basis code. |
| AI Act role: per client or per system? | S51 | Both competitors resolve per system and per legal entity. Possible live modelling bug. |
| Art. 4 AI literacy in the catalogue? | S50 | In force since 2 Feb 2025, binds Providers *and* Deployers. |
| `applies_from` for 2 Dec 2026? | — | Additional prohibited practices per the AI Omnibus. **Verify against the OJ, not a competitor's marketing page.** |
| `chat.py` says Annex III applies from 2 Aug 2026 | — | Contradicts `obligations.py`. Client-visible wrong answer about a date now past. |
| Art. 9(2) coverage | S55 | Both seeded paths use `employment_social_security`; the other nine untested. |
| Anthropic contracting entity | — | Ships as `dpa_status = 'unknown'` rather than an asserted default. |
| `DISPLAY_TZ_NAME` | — | Brussels for everyone. Becomes per-client on the first non-Belgian client. |
| ~~Hosting before beta~~ | — | **Resolved: D-66 to D-69. Now S32A.** |
| Marketing copy correction | — | **D-66. This week, independent of any sprint.** Framer site. |
| PDF/ODT fallback | S33 | `convert_docx_to_pdf` raises when `soffice` is missing; generation should degrade to DOCX rather than fail. |
| Beta date | — | Six sprints to the S33 gate. The lever if it slips is moving S30 (DPIA) post-beta. |

### The hosting question — resolved 8 Sept 2026

See D-66 to D-69 in section 4. Summary: move to European infrastructure before
beta, self-host Supabase rather than replace it, rework the UI in Streamlit
rather than rewrite the front end, and correct the marketing copy this week
regardless.

**Resolved since the last revision:** language scope (FR/EN now, NL as S53, with
templates authored language-parallel so NL is translation not re-derivation);
`selected_client` language key (`pages/inventory.py` reads `document_languages`,
and S26C derives `doc_langs` from it).

---

*End of record. Append at sprint close.*

*Revised 4 September 2026. **This file was not in git before this revision** —
D-12 to D-42 were lost as a result. Commit it.*
