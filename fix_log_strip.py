#!/usr/bin/env python3
"""
Repair the effects of a global find-and-replace of "log" -> "" (case-insensitive)
that was accidentally applied to the RECOSA codebase.

Usage:
    python3 fix_log_strip.py                 # dry run over all .py files
    python3 fix_log_strip.py --apply         # write changes in place
    python3 fix_log_strip.py --apply a.py    # limit to given files
"""
import re
import sys
import pathlib

# (pattern, replacement, label). Applied in a single pass each, with
# lookarounds so a repair can never re-match inside its own output or
# inside an unrelated identifier such as load_token_usage.
REPAIRS = [
    # --- functional damage ---
    (r'(?<![A-Za-z0-9_])_token_usage\b', 'log_token_usage', 'log_token_usage identifier'),
    (r'(?<![A-Za-z0-9_])usage_s(?![A-Za-z0-9_])', 'usage_logs', 'usage_logs table name'),

    # --- comments and docstrings ---
    (r'Token usage ging', 'Token usage logging', 'section header'),
    (r'"""\n\s+a Mistral API call', '"""Log a Mistral API call', 'log_token_usage docstring'),
    (r'Could not {2}token usage', 'Could not log token usage', 'error message'),
    (r'"""\n\s+the start of a monitoring run\.', '"""Log the start of a monitoring run.',
     'start_monitor_run docstring'),
    (r'""" the completion of a monitoring run\."""',
     '"""Log the completion of a monitoring run."""', 'complete_monitor_run docstring'),
    (r'chronoically', 'chronologically', 'docstring typo'),
]

# Residual traces of the same replace that this script does not know how to
# repair automatically. Reported for manual review.
SUSPECT = re.compile(
    r'(?<![A-Za-z0-9_])(?:'
    r'usage_s|_token_usage|chronoically|ging\b|'
    r'in\b(?=\s*=\s*)|ic\b|catao|diaogue|bo\b(?=ger)|'
    r'techno(?!log)|bi(?=ical)|ana(?!log)ue'
    r')(?![A-Za-z0-9_])'
)


def repair(text: str):
    hits = []
    for pattern, replacement, label in REPAIRS:
        text, n = re.subn(pattern, replacement, text)
        if n:
            hits.append((label, n))
    return text, hits


def main() -> int:
    files = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply_ = '--apply' in sys.argv

    if files:
        targets = [pathlib.Path(f) for f in files]
    else:
        targets = [p for p in sorted(pathlib.Path('.').rglob('*.py'))
                   if not {'.venv', 'venv', 'site-packages', '__pycache__'} & set(p.parts)]

    total = 0
    for path in targets:
        try:
            original = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue

        fixed, hits = repair(original)
        if hits:
            n = sum(c for _, c in hits)
            total += n
            print(f"{path}")
            for label, count in hits:
                print(f"    {count}x  {label}")
            if apply_:
                path.write_text(fixed, encoding='utf-8')

        for m in SUSPECT.finditer(fixed):
            line = fixed[:m.start()].count('\n') + 1
            print(f"    ?   {path}:{line} unresolved: {m.group(0)!r}")

    verb = 'Applied' if apply_ else 'Would apply'
    print(f"\n{verb} {total} repair(s) across {len(targets)} file(s).")
    if not apply_ and total:
        print("Re-run with --apply to write changes.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
