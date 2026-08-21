"""
fetch_oj_text.py — download the Annex of a EUR-Lex act as plain text.

Writes templates/raw/dpa_scc_{lang}.oj.md, the input to
template_seed_dpa_patch.py.

    python fetch_oj_text.py

WHY A SCRIPT AND NOT A BROWSER SAVE
-----------------------------------
D-42 requires the transcription be verified against the OJ rather than
trusted. A browser save is unreproducible: nobody can tell later whether the
committed file is what EUR-Lex served or what someone tidied afterwards.
Running this again reproduces the file byte for byte, so `git diff` after a
re-run is the check that it was never hand-edited.

HTML rather than the PDF. The PDF layer hard-wraps mid-sentence, breaks
hyphenated compounds across lines and interleaves running headers, all of
which normalise() then has to repair. The HTML export keeps one paragraph per
element, so there is far less to undo and far less that can go wrong quietly.

Standard library only, deliberately — the authoring layer must not acquire
dependencies the runtime does not have. Same contract as template_seed_lib.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

CELEX = "32021D0915"
LANGS = ("EN", "FR")
OUT_DIR = Path(__file__).resolve().parent / "templates" / "raw"
OUT_NAME = {"EN": "dpa_scc_en.oj.md", "FR": "dpa_scc_fr.oj.md"}

URL = "https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}"

# EUR-Lex rejects urllib's default agent with 403.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RECOSA-seed/1.0)"}

_BREAKING = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}
_SKIP = {"script", "style"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _BREAKING:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BREAKING:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def _tidy(text: str) -> str:
    # Non-breaking spaces are pervasive in EUR-Lex markup and would otherwise
    # sit inside anchor strings, where they look identical to a space and
    # match nothing.
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# The Annex proper starts at a line that is exactly ANNEX / ANNEXE. Matched
# line-anchored and uppercase, because the recitals refer to "the Annex" in
# prose and a substring match would cut the document in the wrong place.
_ANNEX_START = re.compile(r"(?m)^(?:ANNEX|ANNEXE)\s*$")


def _trim_to_annex(text: str, lang: str) -> str:
    """Keep the Annex; drop recitals and enacting terms.

    Not strictly required — the recitals carry no OPTION markers and no clause
    headings, so the anchors would survive. Dropping them keeps the committed
    file to what the contract actually reproduces, which is what a reviewer
    diffing against the OJ expects to see.
    """
    match = _ANNEX_START.search(text)
    if not match:
        print(
            f"WARN  {lang}: no standalone ANNEX heading found — keeping the whole "
            f"document. The patch script will still work; the committed file is "
            f"just larger than it needs to be.",
            file=sys.stderr,
        )
        return text
    return text[match.start():]


def fetch(lang: str) -> str:
    url = URL.format(lang=lang, celex=CELEX)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    # EUR-Lex serves UTF-8 but does not always declare it.
    html = raw.decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    return _trim_to_annex(_tidy(parser.text()), lang)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failed = False
    for lang in LANGS:
        try:
            text = fetch(lang)
        except Exception as exc:
            print(f"FAIL  {lang}: {exc}", file=sys.stderr)
            failed = True
            continue

        # A silent partial download is the failure mode worth catching: a
        # truncated file still parses, and the patch script would report a
        # missing anchor without saying why.
        if len(text) < 20_000:
            print(
                f"FAIL  {lang}: only {len(text)} chars — expected roughly 40k. "
                f"Likely a truncated response or a EUR-Lex error page.",
                file=sys.stderr,
            )
            failed = True
            continue

        out = OUT_DIR / OUT_NAME[lang]
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"OK    {lang}: wrote {out} ({len(text)} chars)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
