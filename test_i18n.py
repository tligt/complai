"""
test_i18n.py — S64 interface slice (D-164)

Run: python test_i18n.py

Every French entry must keep the English one's format placeholders ({n}),
its markdown emphasis and its Streamlit colour tags, or the page either
crashes on .format() or renders differently from the English one.
"""

import json
import re
import sys
from pathlib import Path

import i18n

failures = []
cats = {lang: json.loads((Path(__file__).parent / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in ("fr", "nl")}
pairs = [(en, tr_) for c in cats.values() for en, tr_ in c.items()]

for en, fr in pairs:
    if not fr.strip():
        failures.append(f"empty: {en[:60]!r}")
        continue
    # A translation may leave a placeholder out (str.format ignores unused
    # arguments, e.g. an English plural "s"), but never add one.
    ph = lambda t: set(re.findall(r"\{[a-z_0-9]*(?:![rsa])?(?::[^}]*)?\}", t))  # noqa: E731
    if not ph(fr) <= ph(en):
        failures.append(f"placeholder not in the English: {en[:60]!r}")
    if en.count("**") != fr.count("**"):
        failures.append(f"bold markers differ: {en[:60]!r}")
    if re.findall(r":[a-z]+\[", en) != re.findall(r":[a-z]+\[", fr):
        failures.append(f"colour tags differ: {en[:60]!r}")
    if en.startswith("#") and not fr.startswith("#"):
        failures.append(f"heading lost: {en[:60]!r}")

# The function itself: French when asked, English otherwise and as fallback.
if i18n.translate("Save", "fr") != "Enregistrer":
    failures.append("translate fr")
if i18n.translate("Save", "en") != "Save":
    failures.append("translate en")
if i18n.translate("No such string, surely", "fr") != "No such string, surely":
    failures.append("fallback")
if i18n.translate("Save", "nl") != "Opslaan":
    failures.append("translate nl")
if i18n.translate("Save", "de") != "Save":
    failures.append("a language without a catalogue falls back to English")
if set(cats["fr"]) != set(cats["nl"]):
    failures.append(f"fr and nl cover different strings: {len(set(cats['fr']) ^ set(cats['nl']))} differ")

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print(f"All i18n tests passed ({len(cats['fr'])} French, {len(cats['nl'])} Dutch entries).")
