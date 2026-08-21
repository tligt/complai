"""
template_seed_dpa_patch.py — derive templates/dpa_scc_{lang}.md from the raw
Official Journal text of the Annex to Commission Implementing Decision (EU) 2021/915.

WHY THIS EXISTS
---------------
D-42 requires the clause transcription to be verified against the OJ rather than
trusted. A hand-typed transcription needs 100% verification. A file downloaded from
EUR-Lex and mechanically patched needs only the patch reviewed — six documented
edits, each asserted. That is the difference between reviewing a contract and
reviewing a diff.

INPUT (you provide, once, unedited):
    templates/raw/dpa_scc_en.oj.md   <- Annex only, from CELEX:32021D0915 EN
    templates/raw/dpa_scc_fr.oj.md   <- Annex only, from CELEX:32021D0915 FR

OUTPUT:
    templates/dpa_scc_en.md
    templates/dpa_scc_fr.md

The French file is the official French text, not a translation of the English
(both are authoritative; translating would produce a text with no legal standing).

EDITS APPLIED — all six are gaps the instrument itself expects to be filled.
No edit rewrites Commission wording; each either selects between options the OJ
marks, or fills a blank the OJ marks.

    E1  Clause 1(a)                        resolve to OPTION 1 (GDPR)
    E2  Clauses 8(c)(4), 9.1(b), 9.1(c),
        9.2 closing paragraph              resolve to OPTION 1 (GDPR)
    E3  Clause 7.7(a)                      drop Option 1, unlabel Option 2
    E4  Clause 7.7(a) [SPECIFY TIME PERIOD] -> {{sub_processor_notice_period}}
    E5  Annexes I-IV                       replace OJ dotted-line forms with
                                           RECOSA merge blocks
    E6  Schedule 1                         appended outside the Clauses

Every resolved option is EXTRACTED FROM THE RAW TEXT BY REGEX, never retyped.
The script contains no legal wording from the clauses themselves.

Run:  python template_seed_dpa_patch.py            (writes both languages)
      python template_seed_dpa_patch.py --check    (asserts only, writes nothing)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "templates" / "raw"
OUT_DIR = ROOT / "templates"


class PatchError(RuntimeError):
    """Raised when an anchor does not match exactly as expected."""


# ---------------------------------------------------------------------------
# Per-language anchors. Anchors are structural markers the OJ prints in caps or
# brackets, never substantive wording, so they are stable across the language
# versions and cannot be confused with clause text.
# ---------------------------------------------------------------------------

LANGS = {
    "en": {
        "clause1_option": re.compile(
            r"\[choose relevant option:\s*OPTION 1:\s*(?P<one>.+?)\]\s*/\s*\[OPTION 2:.+?\]",
            re.DOTALL,
        ),
        "inline_option": re.compile(
            r"\[OPTION 1\]\s*(?P<one>.+?)\s*/?\s*\[OPTION 2\]\s*.+?2018/1725",
            re.DOTALL,
        ),
        "subproc_opt1_start": "OPTION 1: PRIOR SPECIFIC AUTHORISATION",
        "subproc_opt2_label": "OPTION 2: GENERAL WRITTEN AUTHORISATION:",
        "time_period": "[SPECIFY TIME PERIOD]",
        "annex_start": re.compile(r"^\s*ANNEX I\b", re.MULTILINE),
        "expect_inline_options": 4,
    },
    "fr": {
        "clause1_option": re.compile(
            r"\[choisir\s+l[’']option qui convient:\s*OPTION 1:\s*(?P<one>.+?)\]\s*/\s*\[OPTION 2:.+?\]",
            re.DOTALL,
        ),
        "inline_option": re.compile(
            r"\[OPTION 1\]\s*(?P<one>.+?)\s*/?\s*\[OPTION 2\]\s*.+?2018/1725",
            re.DOTALL,
        ),
        "subproc_opt1_start": "OPTION 1: AUTORISATION SPÉCIFIQUE PRÉALABLE",
        "subproc_opt2_label": "OPTION 2: AUTORISATION ÉCRITE GÉNÉRALE:",
        "time_period": "[PRÉCISER LA DURÉE]",
        "annex_start": re.compile(r"^\s*ANNEXE I\b", re.MULTILINE),
        "expect_inline_options": 4,
    },
}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# The OJ PDF hard-wraps mid-sentence and breaks hyphenated compounds across
# lines. Both must be repaired BEFORE anchors are matched, or every regex fails
# on invisible newlines. Repairing is not editing: it restores the text the OJ
# renders, which the PDF layer fragments.
_PDF_ARTEFACTS = [
    (re.compile(r"sub\s*-?\s*\n\s*processor"), "sub-processor"),
    (re.compile(r"soustraitant"), "sous-traitant"),
    (re.compile(r"sous\s*-?\s*\n\s*traitant"), "sous-traitant"),
    (re.compile(r"\bClause(\d)"), r"Clause \1"),
    (re.compile(r"\balsodescribe\b"), "also describe"),
]


def normalise(text: str) -> str:
    """CRLF -> LF, repair PDF line-break artefacts, unwrap hard-wrapped paragraphs.

    Line endings are normalised here rather than in body_from_file() because a
    file saved on Windows must not reach the anchor matching with \\r\\n in it —
    the anchors would silently fail to match and the script would report a clean
    run having applied nothing.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for pattern, repl in _PDF_ARTEFACTS:
        text = pattern.sub(repl, text)
    # Strip OJ running headers/footers: "L 199/21 EN Official Journal ..." etc.
    text = re.sub(
        r"^\s*(?:L 199/\d+\s+(?:EN|FR)|[\d.]+\s+(?:EN|FR))\s+"
        r"(?:Official Journal of the European Union|Journal officiel de l[’']Union européenne)"
        r".*$",
        "",
        text,
        flags=re.MULTILINE,
    )
    # Unwrap: a newline not followed by a blank line, a list marker, or a heading
    # is a PDF wrap, not a paragraph break.
    text = re.sub(r"(?<=[^\n])\n(?![\n\s]|[a-z0-9]\)|\(\w\)|\d\)|#|ANNEX|SECTION|Clause|OPTION)", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def resolve_options(text: str, cfg: dict, label: str) -> str:
    """E1 + E2 — collapse every marked OPTION 1/OPTION 2 pair to OPTION 1.

    The retained wording is captured from the raw text, never supplied by this
    script. If an anchor stops matching because EUR-Lex changes its export
    format, the count assertion fails loudly rather than emitting a contract
    with an unresolved '[OPTION 1] ... / [OPTION 2] ...' left in it.
    """
    text, n1 = cfg["clause1_option"].subn(lambda m: m.group("one").strip(), text)
    if n1 != 1:
        raise PatchError(f"{label}: Clause 1(a) option block matched {n1} times, expected 1")

    text, n2 = cfg["inline_option"].subn(lambda m: m.group("one").strip(), text)
    expected = cfg["expect_inline_options"]
    if n2 != expected:
        raise PatchError(
            f"{label}: inline [OPTION 1]/[OPTION 2] pairs matched {n2} times, expected {expected} "
            "(Clauses 8(c)(4), 9.1(b), 9.1(c), 9.2 closing paragraph)"
        )

    leftover = re.search(r"\[OPTION\s*\d", text)
    if leftover:
        raise PatchError(f"{label}: unresolved option marker survived at offset {leftover.start()}")
    return text


def resolve_subprocessor_option(text: str, cfg: dict, label: str) -> str:
    """E3 + E4 — keep Clause 7.7(a) Option 2, drop Option 1, fill the time period.

    Option 2 (general written authorisation from an agreed list) is the scope-lock
    decision. Its consequence is that Annex IV is not completed: the OJ's own
    explanatory note confines Annex IV to Option 1. Annex IV is still emitted, and
    still says so, because Clause 1(d) makes Annexes I to IV integral and a
    dangling reference to a missing annex is worse than an annex marked unused.
    """
    start = text.find(cfg["subproc_opt1_start"])
    end = text.find(cfg["subproc_opt2_label"])
    if start == -1 or end == -1 or end <= start:
        raise PatchError(
            f"{label}: could not locate Clause 7.7(a) Option 1/Option 2 boundary "
            f"(start={start}, end={end})"
        )
    if text.count(cfg["subproc_opt1_start"]) != 1 or text.count(cfg["subproc_opt2_label"]) != 1:
        raise PatchError(f"{label}: Clause 7.7(a) option markers are not unique")

    # Both options carry [SPECIFY TIME PERIOD]; exactly one must survive the cut.
    before = text.count(cfg["time_period"])
    if before != 2:
        raise PatchError(f"{label}: expected 2 time-period placeholders before cut, found {before}")

    text = text[:start] + text[end:]
    text = text.replace(cfg["subproc_opt2_label"], "", 1).replace("\n \n", "\n\n")

    after = text.count(cfg["time_period"])
    if after != 1:
        raise PatchError(f"{label}: expected 1 time-period placeholder after cut, found {after}")

    return text.replace(cfg["time_period"], "{{sub_processor_notice_period}}", 1)


def truncate_at_annexes(text: str, cfg: dict, label: str) -> str:
    """Cut the OJ annexes off. They are dotted-line forms with no content.

    Per correction 3, the clauses are Commission text and the annexes are RECOSA's
    work. Nothing is lost by discarding blank forms and emitting generated ones.
    """
    match = cfg["annex_start"].search(text)
    if not match:
        raise PatchError(f"{label}: could not locate the start of the annexes")
    return text[: match.start()].rstrip() + "\n"


# ---------------------------------------------------------------------------
# RECOSA-authored annexes. These ARE RECOSA's work and do need counsel review.
#
# Merge fields:
#   REQUIRED  legal_name, registered_address, contact_email,
#             sub_processor_notice_period
#   OPTIONAL  enterprise_number, dpo_name, dpo_email
#   FLAGS     has_enterprise_number, has_dpo, has_subprocessors
#
# Optional identity fields are guarded by flags rather than left to render as
# "[[ TO COMPLETE ]]" — the same reasoning as _ROPA_FIELDS. In a signed
# contract a visible placeholder is worse than an omitted line: it draws the
# counterparty's eye to a gap that may not be one, since a sole trader has no
# enterprise number and most SMEs have no DPO.
#   BLOCKS    annex_ii_processing, annex_iii_security, annex_iii_assistance,
#             annex_iii_breach_elements, subprocessor_schedule
#
# Blocks are pre-rendered in Python and merged as single fields. No loops or
# nesting in the template — the renderer stays a merge-field renderer.
# ---------------------------------------------------------------------------

ANNEXES_EN = """
## ANNEX I — List of parties

**Controller(s):** *Identity and contact details of the controller(s), and, where applicable, of the controller's data protection officer.*

To be completed by the controller on acceptance.

1. Name: ..........................................................
   Address: ..........................................................
   Contact person's name, position and contact details: ..........................................................
   Signature and accession date: ..........................................................

**Processor(s):** *Identity and contact details of the processor(s) and, where applicable, of the processor's data protection officer.*

1. Name: **{{legal_name}}**

   Address: {{registered_address}}

{{#if:has_enterprise_number}}
   Company registration number: {{enterprise_number}}

{{/if:has_enterprise_number}}
   Contact for matters arising under these Clauses: {{contact_email}}

{{#if:has_dpo}}
   Data protection officer: {{dpo_name}}, {{dpo_email}}

{{/if:has_dpo}}
   Signature and accession date: ..........................................................

## ANNEX II — Description of the processing

{{#block:annex_ii_processing}}

## ANNEX III — Technical and organisational measures including technical and organisational measures to ensure the security of the data

### 1. Security measures implemented by the processor (Clause 7.4(a))

{{#block:annex_iii_security}}

### 2. Measures by which the processor assists the controller (Clause 8(d))

{{#block:annex_iii_assistance}}

### 3. Elements provided when assisting with breach notification (Clause 9.2)

{{#block:annex_iii_breach_elements}}

## ANNEX IV — List of sub-processors

**Not completed.** This Annex is completed only in the case of specific authorisation of sub-processors under Clause 7.7(a), Option 1. These Clauses are entered into on the basis of Option 2, general written authorisation from an agreed list. The agreed list is set out in Schedule 1.

<!-- SCC END -->

---

# SCHEDULE 1 — Agreed list of sub-processors

<!-- NOT PART OF THE CLAUSES. Referenced as the agreed list for the purposes of
     Clause 7.7(a), Option 2. Kept outside the Clauses so a change of vendor
     updates a schedule rather than requiring the contract to be re-signed. -->

{{#if:has_subprocessors}}
The processor engages the sub-processors listed below. Changes to this list are notified to the controller at least {{sub_processor_notice_period}} in advance, in accordance with Clause 7.7(a).

{{#block:subprocessor_schedule}}
{{/if:has_subprocessors}}
{{#ifnot:has_subprocessors}}
The processor engages no sub-processors for the processing described in Annex II. Should that change, the controller will be informed at least {{sub_processor_notice_period}} in advance, in accordance with Clause 7.7(a).
{{/ifnot:has_subprocessors}}
"""

ANNEXES_FR = """
## ANNEXE I — Liste des parties

**Responsable(s) du traitement :** *Identité et coordonnées du ou des responsables du traitement et, le cas échéant, du délégué à la protection des données du responsable du traitement.*

À compléter par le responsable du traitement lors de l'acceptation.

1. Nom : ..........................................................
   Adresse : ..........................................................
   Nom, fonction et coordonnées de la personne de contact : ..........................................................
   Signature et date d'adhésion : ..........................................................

**Sous-traitant(s) :** *Identité et coordonnées du ou des sous-traitants et, le cas échéant, du délégué à la protection des données du sous-traitant.*

1. Nom : **{{legal_name}}**

   Adresse : {{registered_address}}

{{#if:has_enterprise_number}}
   Numéro d'entreprise : {{enterprise_number}}

{{/if:has_enterprise_number}}
   Contact pour les questions relevant des présentes clauses : {{contact_email}}

{{#if:has_dpo}}
   Délégué à la protection des données : {{dpo_name}}, {{dpo_email}}

{{/if:has_dpo}}
   Signature et date d'adhésion : ..........................................................

## ANNEXE II — Description du traitement

{{#block:annex_ii_processing}}

## ANNEXE III — Mesures techniques et organisationnelles, y compris mesures techniques et organisationnelles visant à garantir la sécurité des données

### 1. Mesures de sécurité mises en œuvre par le sous-traitant (clause 7.4, point a)

{{#block:annex_iii_security}}

### 2. Mesures par lesquelles le sous-traitant prête assistance au responsable du traitement (clause 8, point d)

{{#block:annex_iii_assistance}}

### 3. Éléments communiqués lors de l'assistance en cas de violation de données (clause 9.2)

{{#block:annex_iii_breach_elements}}

## ANNEXE IV — Liste de sous-traitants ultérieurs

**Non complétée.** La présente annexe n'est complétée qu'en cas d'autorisation spécifique de sous-traitants ultérieurs au titre de la clause 7.7, point a), option 1. Les présentes clauses sont conclues sur la base de l'option 2, autorisation écrite générale sur la base d'une liste convenue. La liste convenue figure à l'annexe technique 1.

<!-- SCC END -->

---

# ANNEXE TECHNIQUE 1 — Liste convenue de sous-traitants ultérieurs

<!-- NE FAIT PAS PARTIE DES CLAUSES. Référencée comme la liste convenue aux
     fins de la clause 7.7, point a), option 2. -->

{{#if:has_subprocessors}}
Le sous-traitant a recours aux sous-traitants ultérieurs énumérés ci-dessous. Toute modification de cette liste est notifiée au responsable du traitement au moins {{sub_processor_notice_period}} à l'avance, conformément à la clause 7.7, point a).

{{#block:subprocessor_schedule}}
{{/if:has_subprocessors}}
{{#ifnot:has_subprocessors}}
Le sous-traitant n'a recours à aucun sous-traitant ultérieur pour le traitement décrit à l'annexe II. En cas de changement, le responsable du traitement en sera informé au moins {{sub_processor_notice_period}} à l'avance, conformément à la clause 7.7, point a).
{{/ifnot:has_subprocessors}}
"""

COVERS = {
    "en": """# Data Processing Agreement

<!-- COVER BLOCK — NOT PART OF THE CLAUSES. Permitted under Clause 2(b)
     (inclusion of the Clauses in a broader contract). -->

Standard Contractual Clauses adopted by the European Commission under Article 28(7) of Regulation (EU) 2016/679 — Commission Implementing Decision (EU) 2021/915 of 4 June 2021, OJ L 199, 7.6.2021, p. 18.

**{{legal_name}}** acts as processor under these Clauses, processing personal data on behalf of the controller identified in Annex I.

---

""",
    "fr": """# Contrat de sous-traitance

<!-- BLOC DE COUVERTURE — NE FAIT PAS PARTIE DES CLAUSES. Autorisé par la
     clause 2, point b) (inclusion des clauses dans un contrat plus large). -->

Clauses contractuelles types adoptées par la Commission européenne au titre de l'article 28, paragraphe 7, du règlement (UE) 2016/679 — décision d'exécution (UE) 2021/915 de la Commission du 4 juin 2021, JO L 199 du 7.6.2021, p. 18.

**{{legal_name}}** agit en qualité de sous-traitant au titre des présentes clauses et traite des données à caractère personnel pour le compte du responsable du traitement identifié à l'annexe I.

---

""",
}

ANNEXES = {"en": ANNEXES_EN, "fr": ANNEXES_FR}

# Fields the renderer must supply. Kept here so FIELD_SPECS["dpa"] can be checked
# against the template rather than drifting from it.
EXPECTED_BLOCKS = {
    "annex_ii_processing",
    "annex_iii_security",
    "annex_iii_assistance",
    "annex_iii_breach_elements",
    "subprocessor_schedule",
}

EXPECTED_FIELDS = {
    "legal_name",
    "registered_address",
    "enterprise_number",
    "contact_email",
    "dpo_name",
    "dpo_email",
    "sub_processor_notice_period",
}

# Flags are tested in conditionals, never substituted (template_seed_lib check 1).
EXPECTED_FLAGS = {"has_enterprise_number", "has_dpo", "has_subprocessors"}


def build(lang: str, raw_dir: Path | None = None) -> str:
    cfg = LANGS[lang]
    raw_path = (raw_dir or RAW_DIR) / f"dpa_scc_{lang}.oj.md"
    if not raw_path.exists():
        raise PatchError(
            f"{lang}: missing {raw_path}. Save the Annex of CELEX:32021D0915 "
            f"({lang.upper()}) there, unedited."
        )

    text = normalise(raw_path.read_text(encoding="utf-8"))
    text = resolve_options(text, cfg, lang)
    text = resolve_subprocessor_option(text, cfg, lang)
    text = truncate_at_annexes(text, cfg, lang)

    body = COVERS[lang] + "<!-- SCC START -->\n\n" + text + "\n" + ANNEXES[lang]
    verify(body, lang)
    return body


def verify(body: str, lang: str) -> None:
    """D-42 structural check. Runs on every build, not only before counsel review."""
    # Count against the rendered document only. HTML comments carry authoring
    # notes that reference clauses by number and would otherwise inflate the count.
    visible = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    # (?![.\d]) so that a cross-reference to "Clause 7.7" is not counted as a heading.
    clauses = len(re.findall(r"(?m)^\s*#*\s*Clause\s+(?:10|[1-9])(?![.\d])", visible))
    sections = len(re.findall(r"(?m)^\s*#*\s*SECTION\s+I{1,3}\b", visible))
    annexes = len(re.findall(r"(?m)^\s*#*\s*ANNEXE?\s+(?:IV|I{1,3})\b", visible))
    fields = set(re.findall(r"\{\{([a-z0-9_]+)\}\}", body))
    blocks = set(re.findall(r"\{\{#block:([a-z0-9_]+)\}\}", body))
    opens = sorted(re.findall(r"\{\{#(if|ifnot):([a-z0-9_]+)\}\}", body))
    closes = sorted(re.findall(r"\{\{/(if|ifnot):([a-z0-9_]+)\}\}", body))
    # template_seed_lib check 4b: the renderer anchors _BLOCK_RE with [ \t]*$,
    # so a block tag with anything beside it never matches and the table
    # vanishes from the document without any error.
    stray = [
        line.strip()[:60]
        for line in body.splitlines()
        if "{{#block:" in line and not (line.strip().startswith("{{#block:") and line.strip().endswith("}}"))
    ]

    problems = []
    if clauses != 10:
        problems.append(f"clause headings: {clauses}, expected 10")
    if sections != 3:
        problems.append(f"section headings: {sections}, expected 3")
    if annexes != 4:
        problems.append(f"annex headings: {annexes}, expected 4")
    if opens != closes:
        problems.append(f"unbalanced conditionals: {opens} vs {closes}")
    if {n for _, n in opens} != EXPECTED_FLAGS:
        problems.append(f"flags: {sorted({n for _, n in opens})}, expected {sorted(EXPECTED_FLAGS)}")
    if blocks != EXPECTED_BLOCKS:
        problems.append(f"blocks: {sorted(blocks)}, expected {sorted(EXPECTED_BLOCKS)}")
    if stray:
        problems.append(f"block tags sharing a line with other text: {stray}")
    if fields != EXPECTED_FIELDS:
        missing = EXPECTED_FIELDS - fields
        extra = fields - EXPECTED_FIELDS
        if missing:
            problems.append(f"missing merge fields: {sorted(missing)}")
        if extra:
            problems.append(f"unexpected merge fields: {sorted(extra)}")
    if problems:
        raise PatchError(f"{lang}: structural verification failed — " + "; ".join(problems))


def _fixture(lang: str) -> str:
    """Structural markers only — no OJ wording. Proves the anchors fire without
    needing the real text, and without any legal wording living in the repo."""
    cfg = LANGS[lang]
    c1 = (
        "[choose relevant option: OPTION 1: GDPR-SIDE]/[OPTION 2: EUDPR-SIDE]"
        if lang == "en"
        else "[choisir l\u2019option qui convient: OPTION 1: COTE-RGPD]/[OPTION 2: COTE-RPDUE]"
    )
    inline = (
        "[OPTION 1] KEEP-{n} of Regulation (EU) 2016/679 / "
        "[OPTION 2] DROP-{n} of Regulation (EU) 2018/1725"
    )
    o1, o2 = cfg["subproc_opt1_start"], cfg["subproc_opt2_label"]
    tp = cfg["time_period"]
    annex = "ANNEX I" if lang == "en" else "ANNEXE I"
    lines = [
        "SECTION I", "Clause 1", f"(a) purpose {c1}.",
        "Clause 2", "x", "Clause 3", "x", "Clause 4", "x", "Clause 5", "x",
        "SECTION II", "Clause 6", "x", "Clause 7",
        f"7.7 (a) {o1}: submit at least {tp} prior. Annex IV applies.",
        f"{o2} general list, informed at least {tp} in advance.",
        "Clause 8", f"(c)(4) the obligations in {inline.format(n=1)}.",
        "Clause 9", f"9.1(b) pursuant to {inline.format(n=2)}, shall be stated.",
        f"9.1(c) in complying, pursuant to {inline.format(n=3)}, with the obligation.",
        f"9.2 elements under {inline.format(n=4)}.",
        "SECTION III", "Clause 10", "x", annex, "dotted form ....",
    ]
    # CRLF on purpose: proves normalise() strips them before anchors are matched.
    return "\r\n".join(lines) + "\r\n"


def self_test() -> int:
    """Exercise E1-E4 against a temp dir. Never touches templates/raw/."""
    import tempfile

    failed = False
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for lang in sorted(LANGS):
            (tmp_path / f"dpa_scc_{lang}.oj.md").write_text(_fixture(lang), encoding="utf-8")
            try:
                body = build(lang, raw_dir=tmp_path)
                checks = [
                    ("option marker survived", not re.search(r"\[OPTION\s*\d", body)),
                    ("OPTION 2 text survived", "DROP-" not in body),
                    ("wrong OPTION 1 count", body.count("KEEP-") == 4),
                    ("time period unfilled", LANGS[lang]["time_period"] not in body),
                    # Clause 7.7(a) plus both branches of the Schedule 1 conditional.
                    ("notice field count", body.count("{{sub_processor_notice_period}}") == 3),
                    ("7.7 Option 1 survived", "Annex IV applies" not in body),
                    ("OJ annex form survived", "dotted form" not in body),
                ]
                bad = [name for name, ok in checks if not ok]
                if bad:
                    raise PatchError(f"{lang}: " + "; ".join(bad))
            except PatchError as exc:
                print(f"FAIL  {exc}", file=sys.stderr)
                failed = True
                continue
            print(f"OK    {lang}: E1-E4 applied, structure verified")
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="assert only, write nothing")
    parser.add_argument("--lang", choices=sorted(LANGS), action="append")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the synthetic fixture in a temp dir; touches no real file",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    langs = args.lang or sorted(LANGS)
    failed = False
    for lang in langs:
        try:
            body = build(lang)
        except PatchError as exc:
            print(f"FAIL  {exc}", file=sys.stderr)
            failed = True
            continue
        if args.check:
            print(f"OK    {lang}: verified, {len(body)} chars (not written)")
        else:
            out = OUT_DIR / f"dpa_scc_{lang}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(body, encoding="utf-8", newline="\n")
            print(f"OK    {lang}: wrote {out} ({len(body)} chars)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
