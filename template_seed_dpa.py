"""
template_seed_dpa.py — S26A

Authoring script for the Data Processing Agreement: Standard Contractual
Clauses between controllers and processors, Commission Implementing Decision
(EU) 2021/915 of 4 June 2021 (OJ L 199, 7.6.2021, p. 18).

NEVER IMPORTED AT RUNTIME. Same contract as inventory_seed.py.

WHY THIS FILE IS SHORTER THAN THE REGISTER SEEDS
------------------------------------------------
The registers author both language bodies inline, because the prose is
RECOSA's. This document's body is not RECOSA's: Clauses 1 to 10 are Commission
text, and Clause 2(a) forbids modifying them. So the body arrives from
templates/dpa_scc_{lang}.md, which template_seed_dpa_patch.py derives
mechanically from the Official Journal.

That leaves this file with nothing to author but metadata — which is the point.
It is also why the French body is the official French text rather than a
translation of the English: the Decision is published in every official
language, so translating would produce a text with no legal standing where an
authoritative one already exists.

BUILD ORDER
-----------
    1. Save the Annex of CELEX:32021D0915 (EN and FR, unedited) to
       templates/raw/dpa_scc_en.oj.md and templates/raw/dpa_scc_fr.oj.md
    2. python template_seed_dpa_patch.py        -> templates/dpa_scc_{lang}.md
    3. python template_seed_dpa.py > seed_s26a_dpa.sql
    4. Apply the SQL to Postgres

Step 2 is a build step, not a one-off. Re-running it after a correction to the
raw text regenerates both bodies; hand-editing templates/dpa_scc_*.md means the
next run silently reverts the change.

MERGE FIELDS — ALL BUT ONE LAND IN THE ANNEXES
-----------------------------------------------
Clause 2(a) confines client data to the annexes, so the clause text carries
exactly one substitution: {{sub_processor_notice_period}} at Clause 7.7(a),
which fills [SPECIFY TIME PERIOD] — a blank the instrument itself expects the
parties to complete (D-43). Everything else appears in Annex I, II or III, or
in Schedule 1, which sits outside the Clauses.

Annex IV is emitted but not completed. Its explanatory note confines it to
Clause 7.7(a) Option 1, and these Clauses are entered into on Option 2. It is
still emitted because Clause 1(d) makes Annexes I to IV integral to the
Clauses, and a dangling reference to a missing annex reads worse than an annex
that states why it is empty.

WHAT COUNSEL REVIEWS
--------------------
Not a contract. Two things: that templates/dpa_scc_{lang}.md matches the OJ
(a diff, and template_seed_dpa_patch.py --check asserts the structure), and
that the annex generation is sound. The clauses themselves are Commission text
reproduced unmodified, which is what Clause 2 requires of anyone using them.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, body_from_file, run


DOC = TemplateDoc(
    doc_type="dpa",
    title="Data Processing Agreement — Standard Contractual Clauses (Art. 28(7) GDPR)",
    tier=1,
    # TODO(fabrice): confirm against the S25/S26 seeds. Cookie Policy and the two
    # registers already occupy sort positions; this is a guess, not a decision.
    sort_order=40,
    sprint="S26A",
    # A DPA is required only of a client that processes on someone else's behalf.
    # The obligation is real when it applies, so the materiality is 'required';
    # applicability is handled by the gate in pages/documents.py, which hides the
    # document entirely when the client has no activity with
    # controller_role='processor'. Materiality answers "how badly does this
    # matter"; the gate answers "does this apply at all". Conflating them would
    # put a required-but-inapplicable document on every client's dashboard.
    materiality="required",
    # Bumped when the OJ text or the annex structure changes — NOT when a client's
    # data changes. source_revision 1 = Decision (EU) 2021/915 as published
    # 7.6.2021, unamended as at the date below.
    source_revision=1,
    version_no=1,
    bodies={
        "en": body_from_file("templates/dpa_scc_en.md"),
        "fr": body_from_file("templates/dpa_scc_fr.md"),
    },
    # Only the two tabular annexes are blocks. Annex III's three slots are
    # merge fields — a joined measure string and two pieces of client-editable
    # prose (D-44). check_bodies() rule 4c would flag any block declared here
    # and not referenced in both bodies.
    blocks={
        "dpa_annex_ii_table",
        "dpa_subprocessor_table",
    },
    change_note=(
        "Initial version (S26A). Clauses 1-10 transcribed from Commission "
        "Implementing Decision (EU) 2021/915; OPTION 1 (GDPR) resolved "
        "throughout; Clause 7.7(a) Option 2 (general written authorisation). "
        "DRAFT — not yet reviewed by counsel."
    ),
)


if __name__ == "__main__":
    run(DOC, "seed_s26a_dpa.sql")
