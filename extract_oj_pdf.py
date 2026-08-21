"""
extract_oj_pdf.py — turn a EUR-Lex OJ PDF into templates/raw/*.oj.md

    python extract_oj_pdf.py CELEX_32021D0915_EN_TXT.pdf en

Run ONCE per language. The output is a pinned build input, committed to the
repo; Decision 2021/915 has not changed since June 2021 and will not change
without a new instrument. Re-running is a check, not a build step.

WHY NOT pypdf
-------------
pypdf's extractor inserts spaces inside words on this PDF's kerning:
"COMMI SSION", "st andard", "betw een", "Ar ticle". In a contract that is
corruption, not untidiness. poppler's pdftotext reads it correctly.

    pdftotext file.pdf out.txt        # Linux: apt install poppler-utils
                                      # macOS: brew install poppler

If pdftotext is unavailable, pass a .txt you produced some other way and this
script will clean it — but check the word spacing first.

WHY THE CLEANUP LIVES HERE AND NOT IN normalise()
--------------------------------------------------
The D-42 check is `diff raw generated`. Every repair done in the patch script
shows up in that diff as noise, and a reviewer then has to sort real edits from
formatting. Doing it here means the committed raw file is already clean and the
diff shows exactly the six documented edits — nothing else.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "templates" / "raw"

# Running headers. poppler emits these as separate short lines rather than the
# single run the PDF renders, so each is matched on its own.
_HEADERS = [
    re.compile(r"(?m)^\s*(?:EN|FR|NL|DE)\s*$"),
    re.compile(r"(?m)^\s*L \d+/\d+\s*$"),
    re.compile(r"(?m)^\s*\d{1,2}\.\d{1,2}\.\d{4}\s*$"),
    re.compile(r"(?m)^\s*Official Journal of the European Union\s*$"),
    re.compile(r"(?m)^\s*Journal officiel de l['’]Union européenne\s*$"),
]

# Hyphenated compounds the PDF breaks across a line and poppler then joins
# without restoring the hyphen. Both appear in the OJ rendering WITH the
# hyphen, so this restores the text rather than altering it.
_REJOINED = [
    (re.compile(r"\bsubprocessor\b"), "sub-processor"),
    (re.compile(r"\bsubprocessors\b"), "sub-processors"),
    (re.compile(r"\bsoustraitant\b"), "sous-traitant"),
    (re.compile(r"\bsoustraitants\b"), "sous-traitants"),
    # The OJ typesets Clause 7 without the space. Restoring it is a
    # rendering repair, not a change to the text.
    (re.compile(r"\bClause(\d)"), r"Clause \1"),
]

# Structural markers that must start their own line, so a clause heading never
# ends up glued to its body.
_BREAK_BEFORE = [
    re.compile(r"(?<!\n)(?=SECTION [IVX]+\b)"),
    re.compile(r"(?<!\n)(?=ANNEXE? [IVX]+\b)"),
    # (?![.\d(]) so "Clause 7.1" and the cross-reference "Clause 8(b)" are
    # left alone — only a heading starts a new line.
    re.compile(r"(?<!\n)(?=Clauses? \d{1,2}(?![.\d(]))"),
    re.compile(r"(?<!\n)(?=\d\.\d{1,2}\.? [A-ZÀ-Ý])"),      # 7.1. Instructions
]

_ANNEX_START = re.compile(r"(?m)^\s*(?:ANNEX|ANNEXE)\s*$")

# A heading whose TITLE sits on the following line.
_TITLED = re.compile(r"^(?:Clauses? \d{1,2}(?: - Optional| — Facultative)?|SECTION [IVX]+|ANNEXE? [IVX]+)\s*$")
# A heading that carries its own title, e.g. "7.2. Purpose limitation".
_SELF_TITLED = re.compile(r"^\d\.\d{1,2}\.? \S")


def _protect_headings(text: str) -> str:
    """Insert a blank line after each heading so the unwrap cannot absorb it."""
    out: list[str] = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        out.append(line)
        stripped = line.strip()
        if _SELF_TITLED.match(stripped):
            out.append("")
        elif _TITLED.match(stripped):
            # The next line is the title; the break goes after it, not here.
            if i + 1 < len(lines) and lines[i + 1].strip():
                out.append(lines[i + 1])
                out.append("")
                lines[i + 1] = ""
    return "\n".join(out)


def to_text(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    exe = shutil.which("pdftotext")
    if not exe:
        sys.exit(
            "pdftotext not found. Install poppler-utils, or convert the PDF "
            "yourself and pass the .txt.\n"
            "  Ubuntu/Codespaces: sudo apt-get install -y poppler-utils\n"
            "  macOS:             brew install poppler"
        )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.txt"
        subprocess.run([exe, str(path), str(out)], check=True)
        return out.read_text(encoding="utf-8", errors="replace")


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\f", "\n")

    for pattern in _HEADERS:
        text = pattern.sub("", text)
    for pattern, repl in _REJOINED:
        text = pattern.sub(repl, text)

    # Protect headings BEFORE unwrapping.
    #
    # The OJ prints a clause as three lines: "Clause 4", "Hierarchy", then the
    # body. The unwrap cannot tell the title from the sentence after it, so
    # without this the heading reads "Clause 4 Hierarchy In the event of a
    # contradiction...". A blank line is a real break and survives the unwrap.
    text = _protect_headings(text)

    # Unwrap: a single newline inside a paragraph is a PDF wrap. A blank line
    # is a real break. Lettered and numbered sub-points keep their own line.
    text = re.sub(
        r"(?<=[^\n])\n(?!\n|\s*\(?[a-z0-9]\)|\s*ANNEX|\s*SECTION|\s*Clause|\s*OPTION)",
        " ",
        text,
    )

    for pattern in _BREAK_BEFORE:
        text = pattern.sub("\n", text)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit("usage: python extract_oj_pdf.py <file.pdf|file.txt> <en|fr|nl|de>")
    src, lang = Path(sys.argv[1]), sys.argv[2].lower()

    text = clean(to_text(src))

    match = _ANNEX_START.search(text)
    if match:
        text = text[match.start():]
    else:
        print("WARN  no standalone ANNEX heading — keeping the whole act", file=sys.stderr)

    # A silently truncated extraction still parses and would surface later as a
    # missing anchor with no explanation.
    if len(text) < 20_000:
        sys.exit(f"FAIL  only {len(text)} chars — expected roughly 25k for the Annex")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"dpa_scc_{lang}.oj.md"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"OK    wrote {out} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
