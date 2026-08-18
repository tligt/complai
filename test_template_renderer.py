"""
test_template_renderer.py — S25

Run: python3 test_template_renderer.py

Focused on the cases that fail SILENTLY. A blocked generation is loud and gets
fixed; a BE-only client rendering "13 months" because a NULL was treated as a
bound produces a plausible-looking document that is simply wrong.
"""

import sys

from template_renderer import (
    FieldSpec,
    render_template,
    resolve_jurisdictions,
    render_cookie_table,
    DEFAULT_BLOCK_RENDERERS,
)

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILS.append(name)


# Mirrors seed_s25_jurisdictions.sql. BE deliberately carries None.
JURISDICTIONS = {
    "BE": {
        "supervisory_authority_short": "APD/GBA",
        "cookie_max_lifetime_months": None,
        "cookie_data_retention_months": None,
        "consent_renewal_months": None,
        "reject_parity_required": True,
        "cookie_walls_prohibited": True,
    },
    "FR": {
        "supervisory_authority_short": "CNIL",
        "cookie_max_lifetime_months": 13,
        "cookie_data_retention_months": 25,
        "consent_renewal_months": 6,
        "reject_parity_required": True,
        "cookie_walls_prohibited": False,
    },
}


print("\n--- jurisdiction resolution ---")

r = resolve_jurisdictions(["BE"], JURISDICTIONS, establishment_code="BE")
check("BE-only cap stays None", r.rules["cookie_max_lifetime_months"] is None,
      f"got {r.rules['cookie_max_lifetime_months']!r}")
check("BE-only flags no cap", r.rules["has_cookie_lifetime_cap"] is False)
check("BE-only authority is APD", r.authority_code == "BE")
check("BE-only not multi-market", r.rules["is_multi_market"] is False)

r = resolve_jurisdictions(["FR"], JURISDICTIONS, establishment_code="FR")
check("FR-only cap is 13", r.rules["cookie_max_lifetime_months"] == 13)
check("FR-only cookie walls not prohibited",
      r.rules["cookie_walls_prohibited"] is False)

# The case the whole design exists for.
r = resolve_jurisdictions(["BE", "FR"], JURISDICTIONS, establishment_code="BE")
check("BE+FR cap is 13, NOT None", r.rules["cookie_max_lifetime_months"] == 13,
      "None here means a NULL was treated as a bound")
check("BE+FR retention is 25", r.rules["cookie_data_retention_months"] == 25)
check("BE+FR cookie walls prohibited (BE strictest)",
      r.rules["cookie_walls_prohibited"] is True)
check("BE+FR authority is still APD, not CNIL",
      r.authority_code == "BE",
      "authority follows establishment; only the RULES go strictest-wins")
check("BE+FR provenance names FR for the cap",
      r.provenance.get("cookie_max_lifetime_months") == "FR")
check("BE+FR is multi-market", r.rules["is_multi_market"] is True)

r = resolve_jurisdictions(["EU"], JURISDICTIONS, establishment_code=None)
check("unknown code resolves to no rules, no crash",
      r.rules["cookie_max_lifetime_months"] is None and r.codes_applied == [])


print("\n--- required vs optional ---")

SPECS = [
    FieldSpec("legal_name", "Legal name", required=True),
    FieldSpec("registered_address", "Registered address", required=True),
    FieldSpec("enterprise_number", "Company registration number"),
    FieldSpec("dpo_email", "DPO email"),
    FieldSpec("has_dpo", "Has DPO", flag=True),
]

BODY = "Controller: {{legal_name}}, {{registered_address}} ({{enterprise_number}})."

res = render_template(BODY, values={
    "legal_name": "RECOSA SRL",
    "registered_address": "Rue Test 1, 1000 Brussels",
    "enterprise_number": "0123.456.789",
}, specs=SPECS, language="en")
check("complete render is not blocked", not res.blocked)
check("complete render has no outstanding", res.is_complete)
check("values substituted", "RECOSA SRL" in res.body)

res = render_template(BODY, values={
    "legal_name": "RECOSA SRL",
    "registered_address": "Rue Test 1",
}, specs=SPECS, language="en")
check("missing optional does not block", not res.blocked)
check("missing optional yields placeholder",
      "[[ TO COMPLETE: Company registration number ]]" in res.body)
check("outstanding recorded once", len(res.outstanding_fields) == 1)
check("outstanding carries language",
      res.outstanding_fields[0]["language"] == "en")

res = render_template(BODY, values={"legal_name": "RECOSA SRL"},
                      specs=SPECS, language="en")
check("missing required blocks", res.blocked)
check("blocked names the field", res.missing_required == ["registered_address"])
check("blocked returns no body", res.body is None,
      "a blocked render must not hand back a partial document")

res = render_template(BODY, values={
    "legal_name": "   ",
    "registered_address": "Rue Test 1",
}, specs=SPECS, language="en")
check("whitespace-only required blocks", res.blocked,
      "a space is not a legal name")


print("\n--- conditionals ---")

COND = (
    "{{#if:has_dpo}}Contact our DPO at {{dpo_email}}.{{/if:has_dpo}}"
    "{{#ifnot:has_dpo}}We have not appointed a DPO.{{/ifnot:has_dpo}}"
)

res = render_template(COND, values={"has_dpo": True, "dpo_email": "dpo@x.eu"},
                      specs=SPECS, language="en")
check("true branch renders", "dpo@x.eu" in res.body)
check("false branch suppressed", "not appointed" not in res.body)

# The ordering bug this design guards against.
res = render_template(COND, values={"has_dpo": False}, specs=SPECS, language="en")
check("false branch renders", "not appointed" in res.body)
check("field inside false branch is NOT outstanding",
      res.outstanding_fields == [],
      "scanning fields before resolving conditionals causes this")
check("no leaked placeholder", "TO COMPLETE" not in res.body)

res = render_template(COND, values={"has_dpo": "", "dpo_email": "x@y.eu"},
                      specs=SPECS, language="en")
check("empty string is falsy", "not appointed" in res.body)


print("\n--- cookie table block ---")

VENDORS = [
    {"vendor_name": "Google Analytics", "purpose": "Audience measurement",
     "category_label": "Analytics", "role_label": "Processor"},
    {"vendor_name": "Meta Pixel", "purpose": "Advertising",
     "category_label": "Marketing", "role_label": "Joint controller"},
]

out = render_cookie_table({"vendors": VENDORS}, "fr")
check("FR headers used", "Fournisseur" in out and "Finalité" in out)
check("all vendors present", "Google Analytics" in out and "Meta Pixel" in out)
check("row count correct", len(out.strip().split("\n")) == 4)

out = render_cookie_table({"vendors": []}, "nl")
check("empty vendors gives NL sentence, not empty table",
      "geen diensten" in out)

out = render_cookie_table({"vendors": [
    {"vendor_name": "A | B", "purpose": None,
     "category_label": "X", "role_label": "Y"}]}, "en")
check("pipe in vendor name escaped", r"A \| B" in out,
      "an unescaped pipe silently splits the table")
check("None cell renders em dash", "—" in out)

out = render_cookie_table({"vendors": VENDORS}, "es")
check("unknown language falls back to EN headers", "Vendor" in out)

res = render_template(
    "## Cookies\n\n{{#block:cookie_table}}\n",
    values={}, specs=[], language="en",
    block_renderers=DEFAULT_BLOCK_RENDERERS,
    block_context={"vendors": VENDORS},
)
check("block substituted in body", "Google Analytics" in res.body)
check("block render not blocked", not res.blocked)


print("\n--- malformed templates ---")

res = render_template("Hello {{nonexistent_field}}.", values={}, specs=SPECS,
                      language="en")
check("unknown field reported", "nonexistent_field" in res.unknown_tags)
check("unknown field does not block", not res.blocked)

res = render_template("{{#if:has_dpo}}unclosed", values={"has_dpo": True},
                      specs=SPECS, language="en")
check("unclosed conditional stripped from body", "{{" not in res.body,
      "a raw tag must never reach a client document")
check("unclosed conditional reported", len(res.unknown_tags) > 0)

res = render_template("{{#block:does_not_exist}}\n", values={}, specs=[],
                      language="en", block_renderers={})
check("missing block reported", "does_not_exist" in res.unknown_tags)
check("missing block placeholdered not crashed", "TO COMPLETE" in res.body)


print("\n--- theme passthrough ---")
res = render_template("x", values={}, specs=[], language="en", theme="default")
check("theme accepted and ignored", res.body.strip() == "x")


print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    sys.exit(1)
print("All passed.")
