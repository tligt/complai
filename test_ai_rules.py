"""
test_ai_rules.py — S61 (D-160)

Run: python test_ai_rules.py

The silent failures: an unanswered question read as "no" (a use classed
minimal before anyone screened it), the Art. 6(3) exception surviving
profiling, a rebranded system still treated as deployed, and a register
verdict claiming compliance from an empty inventory.
"""

import sys

import ai_rules as AR

failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


NO_T = {k: False for k, _l, _o in AR.TRANSPARENCY}
BOT = {"id": "s1", "name": "Website bot", "ai_role": "deployer"}
CRM = {"id": "s2", "name": "CRM", "ai_role": "none"}

blank = {"id": "u0", "system_id": "s1", "name": "Blank"}
minimal = {"id": "u1", "system_id": "s1", "name": "Internal search", "prohibited_practices": [],
           "annex_iii_area": "none", **NO_T,
           "own_name_or_brand": False, "substantially_modified": False, "purpose_changed": False}
chatbot = {**minimal, "id": "u2", "name": "Customer chat", "interacts_with_people": True}
hiring = {**minimal, "id": "u3", "name": "CV screening", "annex_iii_area": "employment",
          "used_on_workers": True}
exception = {**hiring, "id": "u4", "name": "CV formatting", "art6_3_condition": "narrow_procedural",
             "profiles_people": False}
profiling = {**exception, "id": "u5", "name": "CV ranking", "profiles_people": True}
banned = {**minimal, "id": "u6", "name": "Mood at desks", "prohibited_practices": ["emotion_work_education"]}
rebrand = {**chatbot, "id": "u7", "name": "Our own assistant", "own_name_or_brand": True}
half = {**chatbot, "id": "u8", "annex_iii_area": None}

check("blank unknown", AR.classify(blank)["risk"], AR.UNKNOWN)
check("minimal", AR.classify(minimal)["risk"], AR.MINIMAL)
check("chatbot limited", AR.classify(chatbot)["risk"], AR.LIMITED)
check("annex open keeps unknown even with a flag", AR.classify(half)["risk"], AR.UNKNOWN)
check("hiring high", AR.classify(hiring)["risk"], AR.HIGH)
check("exception not high", AR.classify(exception)["risk"], AR.MINIMAL)
check("profiling defeats exception", AR.classify(profiling)["risk"], AR.HIGH)
check("prohibited", AR.classify(banned)["risk"], AR.PROHIBITED)
check("exception, profiling unanswered", AR.classify({**exception, "profiles_people": None})["risk"], AR.UNKNOWN)

check("role from system", AR.effective_role(minimal, BOT)[0], "deployer")
check("rebrand becomes provider", AR.effective_role(rebrand, BOT)[0], "provider")
check("role none", AR.effective_role({"system_id": "s2"}, CRM)[0], None)

d = AR.duties(hiring, BOT)
check("high deployer duties", [o for o in ("ai_12", "ai_13", "ai_14") if o in d], ["ai_12", "ai_13", "ai_14"])
check("chatbot gets ai_04", "ai_04" in AR.duties(chatbot, BOT), True)
check("deployer gets no ai_08", "ai_08" in AR.duties({**chatbot, "generates_content": True}, BOT), False)
check("provider gets ai_08", "ai_08" in AR.duties({**rebrand, "generates_content": True}, BOT), True)

ctx = {"ai": {"systems": [BOT, CRM], "use_cases": [minimal, chatbot, hiring], "models": [], "links": []}}
check("ai_02 compliant", AR.verdict("ai_02", ctx)["status"], "compliant")
check("ai_03 compliant", AR.verdict("ai_03", ctx)["status"], "compliant")
check("ai_09 compliant", AR.verdict("ai_09", ctx)["status"], "compliant")
check("ai_11 compliant", AR.verdict("ai_11", ctx)["status"], "compliant")
check("ai_06 n/a", AR.verdict("ai_06", ctx)["status"], "not_applicable")
check("ai_12 missing overseer", AR.verdict("ai_12", ctx)["status"], "missing")
ctx2 = {"ai": {"systems": [BOT], "use_cases": [minimal, banned, blank], "models": [], "links": []}}
check("ai_02 prohibited", AR.verdict("ai_02", ctx2)["status"], "missing")
check("ai_09 partial", AR.verdict("ai_09", ctx2)["status"], "partial")
check("ai_09 high but questions open", AR.verdict("ai_09", {"ai": {"systems": [BOT], "use_cases": [
    {"id": "x", "system_id": "s1", "name": "x", "annex_iii_area": "employment"}], "models": [], "links": []}})["status"], "missing")
check("no ai data", AR.verdict("ai_02", {}), None)
check("no systems", AR.verdict("ai_09", {"ai": {"systems": [CRM], "use_cases": [], "models": [], "links": []}}), None)
check("system with no use", AR.verdict("ai_09", {"ai": {"systems": [BOT], "use_cases": [], "models": [], "links": []}})["status"], "missing")
check("retired ignored", AR.verdict("ai_02", {"ai": {"systems": [BOT], "use_cases": [{**banned, "status": "retired"}, minimal], "models": [], "links": []}})["status"], "compliant")

client = {"regulations": ["GDPR", "EU_AI_ACT"]}
fs = AR.findings(client, [BOT, {"id": "s3", "name": "Copilot", "ai_role": "deployer"}],
                 [minimal, banned, blank, hiring])
keys = sorted(f["finding_key"] for f in fs)
check("findings", keys, ["ai:assess:u0", "ai:no_use:s3", "ai:oversight:u3", "ai:prohibited:u6"])
check("prohibited blocking", [f["severity"] for f in fs if "prohibited" in f["finding_key"]], ["blocking"])
check("no AI Act, no tasks", AR.findings({"regulations": ["GDPR"]}, [BOT], [blank]), [])

import obligation_register as OR
from obligations import OBLIGATIONS
check("register ids", OR.check_ids([o["id"] for o in OBLIGATIONS]), [])
check("ai_09 tracked", OR.response_kind({"id": "ai_09", "doc_type": "ai_transparency"}), OR.KIND_TRACKED)
check("ai_04 still a document", OR.response_kind({"id": "ai_04", "doc_type": "ai_transparency"}), OR.KIND_DOCUMENT)
v = OR.evaluate([o for o in OBLIGATIONS if o["id"] in ("ai_02", "ai_06")],
                {**ctx, "client": client, "activities": [], "systems": [], "links": []})
check("register derives ai_02", (v["ai_02"]["source"], v["ai_02"]["status"]), ("derived", "compliant"))
check("register derives ai_06 n/a", v["ai_06"]["status"], "not_applicable")

try:
    import work_items as W
    check("routing", W.area_of_task({"producer": "ai", "finding_key": "ai:assess:x"}), "ai_act")
except Exception as e:
    print(f"(routing not checked: {e})")

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("All AI rules tests passed.")
