# ---------------------------------------------------------------------------
# APPEND TO template_seed_lib.py
#
# Also add to the imports at the top of that file:
#     from pathlib import Path
# ---------------------------------------------------------------------------

def body_from_file(path: str | Path) -> str:
    """Read a body from a markdown file, normalising line endings on the way in.

    The registers author both language bodies as Python string literals, because
    they are RECOSA's own prose. The DPA does not: its body is a verbatim
    transcription of a Commission instrument, and nobody reviews a contract
    inside a triple-quoted block. Keeping it as a file makes it diffable against
    the Official Journal in a pull request.

    WHY THIS NORMALISES RATHER THAN LETTING CHECK 7 FIRE
    ----------------------------------------------------
    Check 7 rejects a body containing CR, because a template saved on Windows
    lost every block once already. That check must stay for Python-authored
    bodies, where a CR means someone really did save wrong.

    A file in the repo is different. With git's default core.autocrlf=true on
    Windows, an LF-committed .md arrives in the working tree as CRLF through
    nobody's fault. If check 7 fired on that, the seed would be unrunnable on
    Windows for everyone, and the obvious workaround — stripping the check —
    would remove the protection from the Python bodies too.

    So: normalise here, and pin it at the source as well. Add to .gitattributes:

        templates/*.md text eol=lf
        templates/raw/*.md text eol=lf

    Belt and braces on purpose. The .gitattributes line is the real fix; this
    normalisation is what stops a checkout that predates it from reaching
    Postgres and silently losing every {{#block:}} tag.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    if not p.exists():
        raise FileNotFoundError(
            f"{p} does not exist. Generate it first:\n"
            f"    python template_seed_dpa_patch.py"
        )
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{p} is empty")
    return text.replace("\r\n", "\n").replace("\r", "\n")
