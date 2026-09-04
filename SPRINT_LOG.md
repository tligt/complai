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
| S28 | Privacy Policy + AI Transparency Notice | Tier 2, first LLM inserts |
| S28A | AI deployer pack: AUP + Human Oversight Policy | Tier 1–2, from competitor research |
| S29 | NIS2 pack: InfoSec + BCP + Data Breach | Tier 2, Art. 21(2) |
| S30 | DPIA | Tier 3. Target the EDPB model template |
| S31 | Regulation-aware chunk allocation | **See sequencing note below** |
| S32 | Admin user management | |
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
- **Task register** — audit infrastructure, not a nicety. Unresolved work is
  currently surfaced where it is found and nowhere else: `readiness()` gaps,
  outstanding `[[ TO COMPLETE ]]` placeholders, S55 findings, unreviewed
  translations (S26C), S57 heartbeat findings. A client cannot see everything
  outstanding in one place and an auditor cannot see that a gap was found on
  one date and closed on another. **Three sprints already depend on it.**
- UI/navigation redesign — before or alongside S33. The sidebar is now ten
  items across five groups.
- Pinning the remaining `requirements.txt` packages — before beta onboarding.

**Post-S48 backlog:** DB schema import tool; NIS2 vendor risk register (extend
to third-party AI tools); compliance calendar; public compliance badge; RECOSA
trust page; SSO/SAML; document diffing; register export as a document.

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
| Does S31 come before S28? | S28 | S28–S30 all produce LLM inserts. Run a NIS2, an AI Act and a GDPR query through `retrieve()` and look at the chunk mix. |
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
| Beta date | — | Six sprints to the S33 gate. The lever if it slips is moving S30 (DPIA) post-beta. |

**Resolved since the last revision:** language scope (FR/EN now, NL as S53, with
templates authored language-parallel so NL is translation not re-derivation);
`selected_client` language key (`pages/inventory.py` reads `document_languages`,
and S26C derives `doc_langs` from it).

---

*End of record. Append at sprint close.*

*Revised 4 September 2026. **This file was not in git before this revision** —
D-12 to D-42 were lost as a result. Commit it.*
