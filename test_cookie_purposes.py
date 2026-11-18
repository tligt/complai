"""
test_cookie_purposes.py — S66 (D-187)

Run: python test_cookie_purposes.py

The cases that would mislead silently: a cookie-setting system with no
purposes recorded rendering differently from before S66, a purpose row with an
empty cell in a published policy, a description typed in one language leaking
into another, and an editor row that loses what was typed.
"""

import sys

from inventory_store import clean_cookie_purposes
from template_renderer import render_cookie_table
from template_store import build_vendor_rows

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


LABELS = {
    ("cookie_purpose", "analytics", "fr"): "Statistiques et mesure d'audience",
    ("cookie_purpose", "advertising", "fr"): "Publicité et ciblage",
    ("cookie_purpose", "analytics", "en"): "Analytics and audience measurement",
    ("system_category", "analytics", "fr"): "Analyse et mesure",
    ("system_role", "processor", "fr"): "Sous-traitant",
    ("system_role", "joint_controller", "fr"): "Responsable conjoint",
}


def label_for(vt, code, lang):
    return LABELS.get((vt, code, lang), code)


GOOGLE = {"id": "g", "name": "Google", "vendor_legal_name": "Google Ireland Limited",
          "category": "analytics", "purpose": "Website statistics",
          "purpose_i18n": {"fr": "Statistiques du site"}, "translation_status": {}}
OTHER = {"id": "o", "name": "Hotjar", "vendor_legal_name": None, "category": "analytics",
         "purpose": "Heatmaps", "purpose_i18n": {}, "translation_status": {}}
ROLES = {"g": ["processor", "joint_controller"], "o": []}

# ── No purposes recorded: exactly the pre-S66 row ─────────────────────────
rows = build_vendor_rows([GOOGLE, OTHER], ROLES, {}, "fr", label_for)
check("one row per system without purposes", len(rows) == 2)
check("legacy purpose in the language", rows[0]["purpose"] == "Statistiques du site")
check("legacy category label", rows[0]["category_label"] == "Analyse et mesure")
check("both roles kept", rows[0]["role_label"] == "Sous-traitant; Responsable conjoint")
check("trade name when no legal name", rows[1]["vendor_name"] == "Hotjar")

# ── Purposes recorded: one row per purpose ─────────────────────────────────
P = {"g": [
    {"purpose_code": "analytics", "description_i18n": {"fr": "Compter les visites"},
     "cookie_names": "_ga, _gid", "sort_order": 0},
    {"purpose_code": "advertising", "description_i18n": {"en": "Ads on other sites"},
     "cookie_names": None, "sort_order": 1},
]}
rows = build_vendor_rows([GOOGLE, OTHER], ROLES, P, "fr", label_for)
check("two purposes + one legacy row", len(rows) == 3)
check("vendor named on each purpose row",
      [r["vendor_name"] for r in rows[:2]] == ["Google Ireland Limited"] * 2)
check("description in the language, cookies in brackets",
      rows[0]["purpose"] == "Compter les visites (_ga, _gid)")
check("purpose label as the category", rows[0]["category_label"] == "Statistiques et mesure d'audience")
check("English description when none in French", rows[1]["purpose"] == "Ads on other sites")
check("role on every purpose row", rows[1]["role_label"] == "Sous-traitant; Responsable conjoint")
check("other system unchanged", rows[2]["purpose"] == "Heatmaps")

# No description at all: the purpose label, never a blank cell.
rows = build_vendor_rows([GOOGLE], ROLES, {"g": [
    {"purpose_code": "advertising", "description_i18n": {}, "cookie_names": ""}]}, "fr", label_for)
check("label when no description", rows[0]["purpose"] == "Publicité et ciblage")

# Through the renderer: one table line per purpose.
table = render_cookie_table({"vendors": build_vendor_rows([GOOGLE], ROLES, P, "fr", label_for)}, "fr")
check("table has a line per purpose", len(table.strip().split("\n")) == 2 + 2)

# ── The editor's rows ──────────────────────────────────────────────────────
CODES = {"analytics", "advertising", "strictly_necessary"}
clean, errs = clean_cookie_purposes([
    {"purpose_code": "analytics", "desc_en": " Counting visits ", "desc_fr": "", "cookie_names": " _ga "},
    {"purpose_code": None, "desc_en": "", "desc_fr": "", "cookie_names": ""},   # blank last line
    {"purpose_code": "advertising", "desc_en": None, "desc_fr": "Pub", "cookie_names": None},
], ["en", "fr"], CODES)
check("no errors on good rows", errs == [])
check("blank line dropped", len(clean) == 2)
check("trimmed, empty languages left out",
      clean[0]["description_i18n"] == {"en": "Counting visits"} and clean[0]["cookie_names"] == "_ga")
check("order kept", [c["sort_order"] for c in clean] == [0, 1])
check("None description handled", clean[1]["description_i18n"] == {"fr": "Pub"})

clean, errs = clean_cookie_purposes([
    {"purpose_code": None, "desc_en": "typed something", "cookie_names": ""},
    {"purpose_code": "analytics"}, {"purpose_code": "analytics"},
    {"purpose_code": "made_up"},
], ["en"], CODES)
check("text with no purpose is an error, not dropped", any("Row 1" in e for e in errs))
check("duplicate purpose refused", any("Row 3" in e and "twice" in e for e in errs))
check("unknown purpose refused", any("Row 4" in e for e in errs))
check("the valid one kept", [c["purpose_code"] for c in clean] == ["analytics"])

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All cookie purpose tests passed.")
