"""
ai_rules.py — S61 (D-160). The AI Act inventory: what each use is, and what
it requires.

NO STREAMLIT. NO SUPABASE. NO I/O. (D-61)

THREE LAYERS
------------
    model     — what a system is built on (ai_models). One model, many systems.
    system    — an inventory system with ai_role != 'none'. One system, many uses.
    use case  — a business use of a system (ai_use_cases). ROLE AND RISK ATTACH
                HERE: the same vendor chatbot is minimal risk answering
                customer questions and high risk screening job applicants.

THE RISK CLASS IS WORKED OUT, NOT ENTERED
-----------------------------------------
From the answers: Art. 5 screening -> prohibited; an Annex III area without
a valid Art. 6(3) derogation -> high; an Art. 50 trigger -> limited; all
answered and none apply -> minimal. An unanswered question is not a "no"
(D-60): the class stays unknown until it is answered.

Annex I (AI as a safety component of a regulated product, Art. 6(1)) is a
provider question this intake does not ask an SME deployer; the page says so.

THE ROLE CAN CHANGE (Art. 25(1))
--------------------------------
A deployer, distributor or importer becomes a provider when it puts its name
or trademark on the system, modifies it substantially, or changes its
intended purpose so it becomes high-risk.
"""

from __future__ import annotations
from i18n import tr  # S64 interface translation (D-164)

from datetime import date
from typing import Any, Iterable, Mapping

PROHIBITED = "prohibited"
HIGH       = "high"
LIMITED    = "limited"
MINIMAL    = "minimal"
UNKNOWN    = "unknown"

RISK_LABELS = {PROHIBITED: "Prohibited", HIGH: "High risk", LIMITED: "Transparency duties",
               MINIMAL: "Minimal risk", UNKNOWN: "Not assessed"}
RISK_ICON = {PROHIBITED: "⛔", HIGH: "🔴", LIMITED: "🟡", MINIMAL: "🟢", UNKNOWN: "⚪"}

ROLES = {"deployer": "Deployer — we use it", "provider": "Provider — we build or brand it",
         "importer": "Importer", "distributor": "Distributor"}

ART6_3 = {
    "narrow_procedural":     "(a) performs a narrow procedural task",
    "improves_human_result": "(b) improves the result of a previously completed human activity",
    "detects_patterns":      "(c) detects decision patterns or deviations, without replacing or "
                             "influencing a completed human assessment without proper review",
    "preparatory":           "(d) performs a preparatory task to an assessment",
}

TRANSPARENCY = [
    ("interacts_with_people", "Interacts directly with people (a chatbot, a voice assistant)", "ai_04"),
    ("emotion_or_biometric", "Recognises emotions or categorises people biometrically", "ai_05"),
    ("deep_fake", "Publishes images, audio or video resembling real people or events", "ai_06"),
    ("public_interest_text", "Publishes AI-written text informing the public", "ai_07"),
    ("generates_content", "Generates synthetic audio, images, video or text", None),
]

HIGH_RISK_FROM = date(2027, 12, 2)


def _d(v: Any) -> date | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def is_ai_system(system: Mapping[str, Any]) -> bool:
    return (system.get("ai_role") or "none") != "none"


def active(uc: Mapping[str, Any]) -> bool:
    return (uc.get("status") or "in_use") != "retired"


# ── Role ──────────────────────────────────────────────────────────────────

def effective_role(uc: Mapping[str, Any], system: Mapping[str, Any] | None) -> tuple[str | None, str]:
    """(role, why). Art. 25(1) wins over what was entered."""
    triggers = [t for k, t in (("own_name_or_brand", "it carries your name or trademark"),
                               ("substantially_modified", "you modified it substantially"),
                               ("purpose_changed", "you changed its intended purpose"))
                if uc.get(k)]
    entered = uc.get("role") or ((system or {}).get("ai_role") if is_ai_system(system or {}) else None)
    if triggers and entered != "provider":
        return "provider", "Provider under Art. 25(1) because " + " and ".join(triggers) + "."
    if uc.get("role"):
        return entered, "As recorded for this use."
    if entered:
        return entered, "The system's role on the Systems page."
    return None, "Not recorded."


def art25_answered(uc: Mapping[str, Any]) -> bool:
    return all(uc.get(k) is not None for k in
               ("own_name_or_brand", "substantially_modified", "purpose_changed"))


# ── Risk ──────────────────────────────────────────────────────────────────

def classify(uc: Mapping[str, Any], area_labels: Mapping[str, str] | None = None) -> dict[str, Any]:
    """{risk, reasons, open, transparency}. open: the questions still
    unanswered; while one of them could still make the use prohibited or
    high-risk, the class stays unknown."""
    reasons: list[str] = []
    open_: list[str] = []
    blocking_open = False

    practices = uc.get("prohibited_practices")
    if practices is None:
        open_.append("Art. 5 screening")
        blocking_open = True
    elif practices:
        return {"risk": PROHIBITED, "reasons": [f"Matches a prohibited practice: {', '.join(practices)}."],
                "open": [], "transparency": []}

    high = False
    area = uc.get("annex_iii_area")
    area_name = (area_labels or {}).get(area, area)
    if area is None:
        open_.append("Annex III area")
        blocking_open = True
    elif area != "none":
        cond = uc.get("art6_3_condition")
        if not cond:
            high = True
            reasons.append(f"Annex III area: {area_name}.")
        elif uc.get("profiles_people") is None:
            open_.append("whether it profiles people (Art. 6(3))")
            blocking_open = True
        elif uc.get("profiles_people"):
            high = True
            reasons.append(f"Annex III area: {area_name}. The Art. 6(3) derogation does not apply "
                           "because it profiles people.")
        else:
            reasons.append(f"Annex III area: {area_name}, but not high-risk under Art. 6(3) {ART6_3[cond]}. "
                           "Document this assessment (Art. 6(4)).")

    flags = []
    for key, label, _ob in TRANSPARENCY:
        v = uc.get(key)
        if v is None:
            open_.append(label[0].lower() + label[1:])
        elif v:
            flags.append(key)

    if high:
        risk = HIGH
    elif blocking_open:
        risk = UNKNOWN
    elif flags:
        risk = LIMITED
        reasons.append("Transparency duties under Art. 50.")
    elif open_:
        risk = UNKNOWN
    else:
        risk = MINIMAL
        reasons.append("No prohibited practice, no Annex III area, no Art. 50 trigger.")
    return {"risk": risk, "reasons": reasons, "open": open_, "transparency": flags}


# ── What it requires ──────────────────────────────────────────────────────

def duties(uc: Mapping[str, Any], system: Mapping[str, Any] | None) -> list[str]:
    """Obligation ids (obligations.py) this use case brings into play."""
    c = classify(uc)
    role, _ = effective_role(uc, system)
    out = ["ai_01", "ai_02", "ai_10", "ai_03", "ai_09", "ai_11"]
    for key, _label, ob in TRANSPARENCY:
        if ob and uc.get(key):
            out.append(ob)
    if uc.get("generates_content") and role == "provider":
        out.append("ai_08")
    if c["risk"] == HIGH and role == "deployer":
        out += ["ai_12", "ai_13"] + (["ai_14"] if uc.get("used_on_workers") else [])
    return out


# ── Obligation register (obligation_register.DERIVATIONS) ────────────────

def _v(status: str, detail: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "source": "derived", "detail": detail, "evidence": evidence or []}


def _ctx(ctx: Mapping[str, Any]) -> tuple[list, list, dict] | None:
    a = ctx.get("ai")
    if not a:
        return None
    systems = [s for s in a["systems"] if is_ai_system(s)]
    by_id = {s["id"]: s for s in a["systems"]}
    ucs = [u for u in a["use_cases"] if active(u)]
    return systems, ucs, by_id


_TAIL = (" This says what the inventory records; whether the answers are right is "
         "for you to judge.")


def verdict(obligation_id: str, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    got = _ctx(ctx)
    if not got:
        return None
    systems, ucs, by_id = got
    if not systems and not ucs:
        return None
    name = lambda u: u.get("name") or "?"  # noqa: E731

    if obligation_id == "ai_09":
        bare = [s.get("name") or "?" for s in systems if not any(u["system_id"] == s["id"] for u in ucs)]
        unassessed = [name(u) for u in ucs if classify(u)["open"]]
        if not bare and not unassessed:
            return _v("compliant", f"{len(systems)} AI systems, {len(ucs)} uses, each assessed." + _TAIL)
        done = len(ucs) - len(unassessed)
        return _v("partial" if done else "missing",
                  f"{len(bare)} AI systems with no use described, {len(unassessed)} uses not "
                  "fully assessed." + _TAIL,
                  sorted(bare) + sorted(unassessed))

    if not ucs:
        return None

    if obligation_id in ("ai_02", "ai_10"):
        bad = [name(u) for u in ucs if u.get("prohibited_practices")]
        unscreened = [name(u) for u in ucs if u.get("prohibited_practices") is None]
        if bad:
            return _v("missing", f"{len(bad)} uses match a prohibited practice. Stop them." + _TAIL, sorted(bad))
        if unscreened:
            return _v("partial", f"{len(unscreened)} of {len(ucs)} uses not screened against Art. 5." + _TAIL,
                      sorted(unscreened))
        return _v("compliant", f"All {len(ucs)} uses screened against Art. 5; none matches." + _TAIL)

    if obligation_id == "ai_03":
        missing = [name(u) for u in ucs
                   if not effective_role(u, by_id.get(u["system_id"]))[0] or not art25_answered(u)]
        if not missing:
            return _v("compliant", f"A role is recorded for all {len(ucs)} uses, with the Art. 25 "
                                   "questions answered." + _TAIL)
        return _v("partial" if len(missing) < len(ucs) else "missing",
                  f"{len(missing)} of {len(ucs)} uses lack a role or the Art. 25 answers." + _TAIL,
                  sorted(missing))

    if obligation_id == "ai_11":
        missing = [name(u) for u in ucs if u.get("annex_iii_area") is None
                   or (u.get("annex_iii_area") != "none" and u.get("art6_3_condition")
                       and u.get("profiles_people") is None)]
        if not missing:
            return _v("compliant", f"Annex III assessed for all {len(ucs)} uses." + _TAIL)
        return _v("partial" if len(missing) < len(ucs) else "missing",
                  f"{len(missing)} of {len(ucs)} uses not assessed against Annex III." + _TAIL,
                  sorted(missing))

    if obligation_id in ("ai_06", "ai_07"):
        key = "deep_fake" if obligation_id == "ai_06" else "public_interest_text"
        if all(u.get(key) is False for u in ucs):
            return _v("not_applicable", "None of your recorded uses publishes such content." + _TAIL)
        return None

    if obligation_id == "ai_08":
        prov_gen = [u for u in ucs if u.get("generates_content")
                    and effective_role(u, by_id.get(u["system_id"]))[0] == "provider"]
        if not prov_gen and all(u.get("generates_content") is not None for u in ucs):
            return _v("not_applicable", "You provide no generative system among your recorded uses." + _TAIL)
        return None

    if obligation_id == "ai_12":
        high = [u for u in ucs if classify(u)["risk"] == HIGH
                and effective_role(u, by_id.get(u["system_id"]))[0] == "deployer"]
        if not high:
            if all(classify(u)["risk"] != UNKNOWN for u in ucs):
                return _v("not_applicable", "No high-risk use that you deploy is recorded." + _TAIL)
            return None
        without = [name(u) for u in high if not u.get("oversight_employee_id")]
        if not without:
            return _v("compliant", f"An overseer is named for all {len(high)} high-risk uses." + _TAIL)
        return _v("partial" if len(without) < len(high) else "missing",
                  f"{len(without)} high-risk uses have no overseer named." + _TAIL, sorted(without))
    return None


TRACKED = ("ai_02", "ai_03", "ai_06", "ai_07", "ai_08", "ai_09", "ai_10", "ai_11", "ai_12")


# ── Action plan (tasks.py producer) ──────────────────────────────────────

def findings(client: Mapping[str, Any], systems: Iterable[Mapping[str, Any]],
             use_cases: Iterable[Mapping[str, Any]]) -> list[dict]:
    from tasks import _finding, BLOCKING, OPEN
    if "EU_AI_ACT" not in (client.get("regulations") or []):
        return []
    systems = list(systems)
    ucs = [u for u in use_cases if active(u)]
    by_id = {s["id"]: s for s in systems}
    out = []
    for s in systems:
        if is_ai_system(s) and not any(u["system_id"] == s["id"] for u in ucs):
            out.append(_finding("ai", f"no_use:{s['id']}",
                                tr("AI inventory: describe how {s_get_name} is used").format(s_get_name=s.get('name')),
                                OPEN, "Role and risk depend on the use, not the system.",
                                None, link="ai_inventory"))
    for u in ucs:
        c = classify(u)
        if c["risk"] == PROHIBITED:
            out.append(_finding("ai", f"prohibited:{u['id']}",
                                tr("AI inventory: {u_name} matches a prohibited practice").format(u_name=u['name']),
                                BLOCKING, "Art. 5: stop this use.", None, link="ai_inventory"))
        elif c["risk"] == UNKNOWN or c["open"]:
            out.append(_finding("ai", f"assess:{u['id']}",
                                tr("AI inventory: finish assessing {u_name}").format(u_name=u['name']), OPEN,
                                "Still to answer: " + ", ".join(c["open"][:3])
                                + ("…" if len(c["open"]) > 3 else ""), None, link="ai_inventory"))
        role, _ = effective_role(u, by_id.get(u["system_id"]))
        if c["risk"] == HIGH and role == "deployer" and not u.get("oversight_employee_id"):
            out.append(_finding("ai", f"oversight:{u['id']}",
                                tr("AI inventory: name a human overseer for {u_name}").format(u_name=u['name']), OPEN,
                                "Art. 26(2), from 2 Dec 2027.", HIGH_RISK_FROM, link="ai_inventory"))
    return out
