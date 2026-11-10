"""
test_template_ai.py — S62 (D-161)

Run: python test_template_ai.py

Renders the three AI pack documents in EN and FR from a small inventory and
checks what would fail silently: a prohibited use listed as approved, personal
data allowed into a tool with no DPA, a high-risk use with no overseer not
said, an empty notice table, and an unfilled merge field.
"""

import sys
from datetime import date, timedelta

import template_ai as TA
import template_seed_ai as SEED
import template_store as TS
import training_rules as TR
from template_renderer import render_template

failures = []


def check(name, cond, detail=""):
    if not cond:
        failures.append(f"{name} {detail}")


NO = {k: False for k, _l, _o in __import__("ai_rules").TRANSPARENCY}
BASE = {"prohibited_practices": [], "annex_iii_area": "none", **NO, "status": "in_use",
        "own_name_or_brand": False, "substantially_modified": False, "purpose_changed": False}
systems = [
    {"id": "s1", "name": "ChatBot Pro", "ai_role": "deployer", "dpa_status": "signed"},
    {"id": "s2", "name": "HireRank", "ai_role": "deployer", "dpa_status": "none"},
    {"id": "s3", "name": "Copilot", "ai_role": "deployer", "dpa_status": "signed"},
    {"id": "s4", "name": "Payroll", "ai_role": "none"},
]
ucs = [
    {**BASE, "id": "u1", "system_id": "s1", "name": "Website chat", "interacts_with_people": True,
     "description": "Answers questions on our website"},
    {**BASE, "id": "u2", "system_id": "s2", "name": "CV screening", "annex_iii_area": "employment",
     "used_on_workers": True, "oversight_employee_id": "e1"},
    {**BASE, "id": "u3", "system_id": "s2", "name": "Interview scoring", "annex_iii_area": "employment"},
    {**BASE, "id": "u4", "system_id": "s1", "name": "Mood tracking", "prohibited_practices": ["emotion_work_education"]},
]
practices = [{"code": "social_scoring", "label_en": "Social scoring", "label_fr": "Notation sociale",
              "metadata": {"article": "Art. 5(1)(c)"}}]
employees = [{"id": "e1", "name": "Ana Overseer", "ai_overseer": True}]
reqs = [TR.requirement({"code": "ai_oversight", "label_en": "Oversight",
                        "metadata": {"regulation": "EU_AI_ACT", "audience": "ai_overseers"}})]
training = {"requirements": reqs,
            "sessions": [{"id": "t1", "held_on": (date.today() - timedelta(days=30)).isoformat(),
                          "requirement_codes": ["ai_oversight"]}],
            "attendance": [{"session_id": "t1", "employee_id": "e1"}]}
ctx = TA.build_ai_context_from(systems, ucs, practices, employees, training)

check("Payroll is not an AI system", all(s["id"] != "s4" for s in ctx["ai_systems"]))
check("two high-risk uses", [u["id"] for u in ctx["ai_high_risk"]] == ["u2", "u3"])
check("notice uses", [u["id"] for u in ctx["ai_notice_uses"]] == ["u1"])

client = {"legal_name": "Test SA", "legal_form": "SA", "ai_policy_owner": "The operations manager",
          "contact_email": "ai@test.example"}

for key, (doc, _out) in SEED.DOCS.items():
    specs = TS.FIELD_SPECS[doc.doc_type]
    for lang, body in doc.bodies.items():
        values = {"legal_name": client["legal_name"], "legal_form": client["legal_form"],
                  "contact_email": client["contact_email"], "policy_effective_date": "10/11/2026"}
        TA.apply_ai_values(values, client, ctx, lang)
        res = render_template(body, values=values, specs=specs, language=lang,
                              block_renderers=TS.DEFAULT_BLOCK_RENDERERS, block_context=ctx)
        md = getattr(res, "markdown", None) or getattr(res, "body", None) or str(res)
        tag = f"[{key}/{lang}]"
        check(f"{tag} not blocked", not res.blocked and not res.unknown_tags,
              f"{res.missing_required} {res.unknown_tags}")
        if key == "hop" and lang == "en" and "--show" in sys.argv:
            print(md)
        check(f"{tag} rendered", "{{" not in md, md[:200])
        check(f"{tag} no TO COMPLETE", "TO COMPLETE" not in md and "À COMPLÉTER" not in md.upper(),
              "a merge field was left unfilled")
        if key == "aup":
            check(f"{tag} prohibited use not approved", "Mood tracking" not in md)
            check(f"{tag} chat approved", "Website chat" in md)
            check(f"{tag} no DPA, no personal data",
                  ("no data processing agreement" in md) if lang == "en" else ("aucun accord" in md))
            check(f"{tag} owner named", "The operations manager" in md)
            check(f"{tag} Art. 5 table", "Social scoring" in md or "Notation sociale" in md)
            check(f"{tag} Copilot has no use", "Copilot" in md)
        if key == "hop":
            check(f"{tag} overseer named", "Ana Overseer" in md)
            check(f"{tag} unassigned said", ("no overseer" in md) if lang == "en"
                  else ("n'ont pas de responsable" in md))
            check(f"{tag} workers section", "Art. 26(7)" in md or "art. 26(7)" in md)
        if key == "notice":
            check(f"{tag} chat listed", "Website chat" in md)
            check(f"{tag} only notice uses", "CV screening" not in md)

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f[:300])
    sys.exit(1)
print("All AI pack template tests passed.")
