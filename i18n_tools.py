"""
i18n_tools.py — S64 interface slice (D-164). Wrap and extract interface strings.

    python i18n_tools.py wrap app.py app_pages/*.py     # wrap literals in tr()
    python i18n_tools.py extract                        # list every tr("...") string
    python i18n_tools.py missing fr                     # extracted strings with no French

WRAP is mechanical and conservative. It wraps a plain string literal (not an
f-string) when it is:
  - the first argument of a Streamlit call (st.title, col.button, …, any object:
    columns, tabs and containers are called the same way),
  - a label-like keyword of such a call (help, placeholder, label, title),
  - an element of a list literal passed to tabs().
It skips strings with HTML (a "<"), strings without letters, and anything
already wrapped. Strings built at runtime (f-strings, concatenation, dict
labels) are left for a person: wrap them as tr("… {x} …").format(x=…).

Adds `from i18n import tr` to a file it changed.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ST_FUNCS = {
    "title", "header", "subheader", "caption", "markdown", "text", "info", "warning",
    "error", "success", "toast", "button", "form_submit_button", "download_button",
    "link_button", "page_link", "checkbox", "toggle", "radio", "selectbox", "multiselect",
    "text_input", "text_area", "number_input", "date_input", "time_input", "file_uploader",
    "expander", "metric", "tabs", "popover", "spinner", "slider", "select_slider",
    "segmented_control", "pills", "chat_input", "status", "Page", "color_picker",
}
LABEL_KWARGS = {"help", "placeholder", "label", "title"}


def _wrappable(node: ast.AST) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and re.search(r"[A-Za-z]", node.value) is not None and "<" not in node.value
            and not node.value.endswith(".py"))      # st.Page's file path


def _targets(tree: ast.AST) -> list[ast.Constant]:
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ST_FUNCS):
            continue
        if node.args:
            first = node.args[0]
            if node.func.attr == "tabs" and isinstance(first, ast.List):
                out += [e for e in first.elts if _wrappable(e)]
            elif _wrappable(first):
                out.append(first)
        for kw in node.keywords:
            if kw.arg in LABEL_KWARGS and _wrappable(kw.value):
                out.append(kw.value)
    return out


def _offsets(src: str) -> list[int]:
    starts, pos = [0], 0
    for line in src.splitlines(keepends=True):
        pos += len(line)
        starts.append(pos)
    return starts


def wrap_file(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    targets = _targets(tree)
    if not targets:
        return 0
    starts = _offsets(src)
    # Character offsets from (line, utf-8 byte col): convert per line.
    lines = src.splitlines(keepends=True)

    def off(lineno: int, col: int) -> int:
        line = lines[lineno - 1].encode("utf-8")
        return starts[lineno - 1] + len(line[:col].decode("utf-8"))

    spans = sorted({(off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset)) for n in targets},
                   reverse=True)
    for a, b in spans:
        if src[max(0, a - 3):a] == "tr(":
            continue
        src = src[:a] + "tr(" + src[a:b] + ")" + src[b:]
    if "from i18n import tr" not in src:
        src = _add_import(src)
    ast.parse(src)          # never write a file that no longer parses
    path.write_text(src, encoding="utf-8", newline="")
    return len(spans)


def _add_import(src: str) -> str:
    tree = ast.parse(src)
    insert_after = 0
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) \
                and node is tree.body[0]:
            insert_after = node.end_lineno
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_after = node.end_lineno
            continue
        break
    lines = src.splitlines(keepends=True)
    lines.insert(insert_after, "from i18n import tr  # S64 interface translation (D-164)\n")
    return "".join(lines)


def extract(paths: list[Path]) -> list[str]:
    found: list[str] = []
    for p in paths:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "_")
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.append(node.args[0].value)
    # The menu section headings (app.py _sections keys) and the page tips are
    # translated where they are shown.
    found += ["Assess", "Records", "Respond", "Tools", "Account", "What is this page for?", "Got it"]
    # The page tips are translated where they are shown (guide.page_tip).
    try:
        import guide
        for title, text in guide.TIPS.values():
            found += [title, text]
    except Exception:
        pass
    seen, out = set(), []
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def default_paths() -> list[Path]:
    return [ROOT / "app.py", *sorted((ROOT / "app_pages").glob("*.py")),
            *(ROOT / f for f in ("active_client.py", "guide.py", "support_widget.py", "subscribe_view.py"))]


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:] or ["extract"]
    if cmd == "wrap":
        total = 0
        for f in rest:
            n = wrap_file(Path(f))
            total += n
            print(f"{f}: {n}")
        print(f"wrapped {total}")
    elif cmd == "extract":
        for s in extract(default_paths()):
            print(json.dumps(s, ensure_ascii=False))
    elif cmd == "missing":
        lang = rest[0] if rest else "fr"
        cat = json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8")) \
            if (ROOT / "i18n" / f"{lang}.json").exists() else {}
        miss = [s for s in extract(default_paths()) if not cat.get(s)]
        print(json.dumps(miss, ensure_ascii=False, indent=1))
        print(f"{len(miss)} missing", file=sys.stderr)
