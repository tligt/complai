"""
test_locales.py — S64 (D-163)

Run: python test_locales.py

A document's locale is its language plus the company's country, and a
template version is used only for the locales it lists. The silent failure
this guards: a text written for one country quietly serving another.
"""

import sys

import template_store as TS

failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


check("nl BE", TS.document_locale("nl", {"country": "BE"}), "nl-BE")
check("fr FR", TS.document_locale("fr", {"country": "fr"}), "fr-FR")
check("en any", TS.document_locale("en", {"country": "LU"}), "en")
check("describe", TS.describe_locale("fr-LU"), "French for Luxembourg")


class _Q:
    def __init__(self, rows): self.rows = rows
    def __getattr__(self, name): return lambda *a, **k: self
    def execute(self): return type("R", (), {"data": self.rows})()


def version(locales, language="nl"):
    row = {"id": "v", "template_id": "t", "language": language, "version_no": 1, "source_revision": 1,
           "body_md": "x", "materiality": "required", "effective_from": None, "locales": locales}
    TS._get_client = lambda admin=False: type("C", (), {"table": lambda self, n: _Q([row])})()


version(["nl-BE", "nl-NL"])
check("nl-BE served", TS.load_template_version("cookie_policy", "nl", "nl-BE") is not None, True)
check("nl-NL served (nl-NL = nl-BE for now)", TS.load_template_version("cookie_policy", "nl", "nl-NL") is not None, True)
version(["fr-BE", "fr-FR"], "fr")
check("fr-LU not borrowed", TS.load_template_version("cookie_policy", "fr", "fr-LU"), None)
version(None, "fr")
check("legacy row uses defaults", TS.load_template_version("cookie_policy", "fr", "fr-FR") is not None, True)
check("legacy row still strict", TS.load_template_version("cookie_policy", "fr", "fr-LU"), None)

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("All locale tests passed.")
