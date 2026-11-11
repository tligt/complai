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


# ── f-strings (D-166) ─────────────────────────────────────────────────────

def _placeholder(expr_src: str, used: set[str]) -> str:
    base = re.sub(r"[^0-9a-zA-Z_]+", "_", expr_src).strip("_").lower() or "x"
    base = re.sub(r"_+", "_", base)[:24].strip("_") or "x"
    if base[0].isdigit():
        base = "x_" + base
    name, i = base, 2
    while name in used:
        name, i = f"{base}{i}", i + 1
    used.add(name)
    return name


def fstring_template(node: ast.JoinedStr, src: str):
    """(template, [(name, expr_source)]) or None when there is nothing to
    translate (no words, or HTML)."""
    parts, args, used = [], [], set()
    text = ""
    for v in node.values:
        if isinstance(v, ast.Constant):
            text += v.value
            parts.append(v.value.replace("{", "{{").replace("}", "}}"))
        elif isinstance(v, ast.FormattedValue):
            expr = ast.get_source_segment(src, v.value)
            if expr is None:
                return None
            name = _placeholder(expr, used)
            conv = {-1: "", 115: "!s", 114: "!r", 97: "!a"}[v.conversion]
            spec = ""
            if v.format_spec is not None:
                if not all(isinstance(x, ast.Constant) for x in v.format_spec.values):
                    return None
                spec = ":" + "".join(x.value for x in v.format_spec.values)
            parts.append("{" + name + conv + spec + "}")
            args.append((name, expr))
        else:
            return None
    if not re.search(r"[A-Za-z]{2,}", text) or "<" in text:
        return None
    return "".join(parts), args


def _fstring_targets(tree: ast.AST, extra_funcs: set[str]) -> list[ast.JoinedStr]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
        if isinstance(f, ast.Attribute) and name in ST_FUNCS:
            cands = node.args[:1] + [k.value for k in node.keywords if k.arg in LABEL_KWARGS]
        elif name in extra_funcs:
            # _finding(producer, key, title, severity, detail, …): only the
            # title (2) and detail (4). The key is an identifier and must
            # never change with the language.
            cands = [a for i, a in enumerate(node.args) if i in (2, 4)] +                     [k.value for k in node.keywords if k.arg in ("title", "detail")]
        else:
            continue
        out += [c for c in cands if isinstance(c, ast.JoinedStr)]
    return out


def wrapf_file(path: Path, extra_funcs: set[str] = frozenset()) -> int:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    starts = _offsets(src)

    def off(lineno: int, col: int) -> int:
        line = lines[lineno - 1].encode("utf-8")
        return starts[lineno - 1] + len(line[:col].decode("utf-8"))

    edits = []
    for n in _fstring_targets(tree, set(extra_funcs)):
        t = fstring_template(n, src)
        if not t:
            continue
        template, args = t
        call = "tr(" + json.dumps(template, ensure_ascii=False) + ")"
        if args:
            call += ".format(" + ", ".join(f"{k}={e}" for k, e in args) + ")"
        edits.append((off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset), call))
    for a, b, call in sorted(edits, reverse=True):
        src = src[:a] + call + src[b:]
    if edits and "from i18n import tr" not in src:
        src = _add_import(src)
    ast.parse(src)
    path.write_text(src, encoding="utf-8", newline="")
    return len(edits)


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
            # guide.notice(key, text): translated inside notice().
            fname = getattr(getattr(node, "func", None), "attr", None) or getattr(getattr(node, "func", None), "id", None)
            if (isinstance(node, ast.Call) and fname == "notice" and len(node.args) > 1
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                found.append(node.args[1].value)
    # The menu section headings (app.py _sections keys) and the page tips are
    # translated where they are shown.
    found += ["Assess", "Records", "Respond", "Tools", "Account", "What is this page for?", "Got it"]
    # Labels kept in dictionaries and read through tr() where shown (D-166):
    # the catalogue (obligations._Translated), AI and training labels.
    try:
        import obligations as O
        import ai_rules as AR
        import training_rules as TRR
        found += [dict(o)["title"] for o in O.OBLIGATIONS]
        found += list(dict(O.DOCUMENT_TYPES).values()) + list(dict(O.REGULATION_LABELS).values())
        found += list(AR.RISK_LABELS.values()) + list(AR.ROLES.values()) + list(AR.ART6_3.values())
        found += [label for _k, label, _o in AR.TRANSPARENCY] + ["not recorded"]
        found += list(TRR.AUDIENCES.values()) + list(TRR.FORMATS.values())
        found += list(TRR.STATE_LABELS["en"].values()) + ["the name", "the purpose"]
        # The incident page (D-169): team roles, alert settings and the
        # assessment choices, kept in English and shown through tr().
        import incident_rules as IR
        found += list(IR.ROLES.values()) + list(IR.ALERT_ON.values())
        found += list(IR.GDPR_RISK.values()) + list(IR.SUBJECTS_EXEMPTIONS.values())
        found += ["Not sure yet", "Yes", "No", "Not decided yet", "None — tell them directly"]
    except Exception as e:
        print(f"(dictionary labels not extracted: {e})", file=sys.stderr)
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
            *(ROOT / f for f in ("active_client.py", "guide.py", "support_widget.py", "subscribe_view.py",
                                 # Action-plan producers (D-166): task titles and details.
                                 "tasks.py", "training_rules.py", "ai_rules.py", "incident_rules.py",
                                 # Shared modules that draw on client pages (D-166).
                                 "audit_view.py", "branding_view.py", "client_setup.py", "funnel_ui.py",
                                 "gap_assessment.py", "obligation_view.py", "work_items_view.py",
                                 # Emails, in the recipient's language (D-168).
                                 "email_sender.py"))]


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:] or ["extract"]
    if cmd == "wrap":
        total = 0
        for f in rest:
            n = wrap_file(Path(f))
            total += n
            print(f"{f}: {n}")
        print(f"wrapped {total}")
    elif cmd == "wrapf":
        extra = {"_finding"}
        total = 0
        for f in rest:
            n = wrapf_file(Path(f), extra)
            total += n
            print(f"{f}: {n}")
        print(f"converted {total}")
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
