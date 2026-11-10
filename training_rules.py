"""
training_rules.py — S60 (D-159). Who needs which training, and who has it.

NO STREAMLIT. NO SUPABASE. NO I/O. (D-61) The Training page, the action plan,
the obligation register, the two PDFs and the monthly reminder all read the
same answers here.

WHAT THE LAW ASKS (reference data: reference_values, 'training_requirement')
---------------------------------------------------------------------------
    gdpr_awareness   GDPR Art. 5(2), 32(4), 39(1)(b)   who handles personal data
    nis2_awareness   NIS2 Art. 21(2)(g)                 all staff
    nis2_management  NIS2 Art. 20(2)                    the management body
    ai_literacy      AI Act Art. 4                      who uses or operates AI
    ai_oversight     AI Act Art. 26(2)                  overseers of high-risk AI
                                                        (from 2 Dec 2027)

The refresh interval is RECOSA's default (12 months). The law says "regular"
or "appropriate", never a number, and the page says so. A session may carry
its own valid_until, which wins.

EVIDENCE OF A PLAN, NOT OF COMPETENCE
-------------------------------------
A full matrix says who attended what, when. It does not say anyone learned
anything, and nothing here claims it does: the register's verdict is about
what is RECORDED, as every derivation is (obligation_register.py).
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any, Iterable, Mapping

# ── States ────────────────────────────────────────────────────────────────

CURRENT      = "current"
EXPIRING     = "expiring"      # current, but ends within EXPIRING_DAYS
EXPIRED      = "expired"       # trained once, no longer current
ABSENT       = "absent"        # required, never trained
NOT_REQUIRED = "not_required"

EXPIRING_DAYS = 60

STATE_LABELS = {
    "en": {CURRENT: "Current", EXPIRING: "Expiring soon", EXPIRED: "Expired",
           ABSENT: "Not trained", NOT_REQUIRED: "Not required"},
    "fr": {CURRENT: "À jour", EXPIRING: "Expire bientôt", EXPIRED: "Expirée",
           ABSENT: "Non formé", NOT_REQUIRED: "Non requis"},
}
STATE_ICON = {CURRENT: "🟢", EXPIRING: "🟡", EXPIRED: "🔴", ABSENT: "⚪", NOT_REQUIRED: "–"}

AUDIENCES = {
    "all":           "All staff",
    "personal_data": "Staff who handle personal data",
    "management":    "Members of the management body",
    "ai_users":      "Staff who use or operate AI systems",
    "ai_overseers":  "People overseeing a high-risk AI system",
}
AUDIENCES_FR = {
    "all":           "Tout le personnel",
    "personal_data": "Personnel traitant des données personnelles",
    "management":    "Membres de l'organe de direction",
    "ai_users":      "Personnel utilisant ou exploitant des systèmes d'IA",
    "ai_overseers":  "Personnes assurant le contrôle d'une IA à haut risque",
}
FORMATS = {"in_person": "In person", "online": "Online, live", "e_learning": "E-learning",
           "reading": "Reading and acknowledgement"}
FORMATS_FR = {"in_person": "En présentiel", "online": "En ligne, en direct",
              "e_learning": "E-learning", "reading": "Lecture et accusé de lecture"}


# ── Dates ─────────────────────────────────────────────────────────────────

def _d(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def add_months(d: date, n: int) -> date:
    """Same day n months later, clamped to the month's end."""
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


# ── Requirements ──────────────────────────────────────────────────────────

def requirement(row: Mapping[str, Any]) -> dict[str, Any]:
    """A reference_values row, flattened."""
    m = row.get("metadata") or {}
    return {
        "code": row["code"],
        "label_en": row.get("label_en") or row["code"],
        "label_fr": row.get("label_fr") or row.get("label_en") or row["code"],
        "note_en": row.get("note_en") or "",
        "note_fr": row.get("note_fr") or row.get("note_en") or "",
        "regulation": m.get("regulation"),
        "audience": m.get("audience") or "all",
        "refresh_months": int(m.get("refresh_months") or 12),
        "obligation_id": m.get("obligation_id"),
        "anchor": m.get("anchor") or "",
        "applies_from": _d(m.get("applies_from")),
        "sort_order": row.get("sort_order") or 100,
    }


def label(req: Mapping[str, Any], lang: str = "en") -> str:
    return req["label_fr"] if lang == "fr" else req["label_en"]


def _nis2_applies(client: Mapping[str, Any]) -> bool:
    if client.get("nis2_in_scope") is not None:
        return bool(client["nis2_in_scope"])
    return "NIS2" in (client.get("regulations") or [])


def applicable(reqs: Iterable[Mapping[str, Any]], client: Mapping[str, Any]) -> list[dict]:
    """The requirements of the client's regulations. NIS2 follows the
    client's own scope answer when given (as incident_rules.nis2_applies)."""
    regs = set(client.get("regulations") or ["GDPR"])
    out = []
    for r in reqs:
        if r["regulation"] not in regs:
            continue
        if r["regulation"] == "NIS2" and not _nis2_applies(client):
            continue
        out.append(dict(r))
    return sorted(out, key=lambda r: r["sort_order"])


def in_force(req: Mapping[str, Any], today: date) -> bool:
    return not req.get("applies_from") or req["applies_from"] <= today


# ── People ────────────────────────────────────────────────────────────────

def is_active(emp: Mapping[str, Any], today: date) -> bool:
    left = _d(emp.get("left_on"))
    return left is None or left > today


def needs(emp: Mapping[str, Any], req: Mapping[str, Any]) -> bool:
    a = req.get("audience") or "all"
    if a == "all":
        return True
    if a == "personal_data":
        return bool(emp.get("handles_personal_data"))
    if a == "management":
        return bool(emp.get("management_body"))
    if a == "ai_users":
        return bool(emp.get("uses_ai") or emp.get("ai_overseer"))
    if a == "ai_overseers":
        return bool(emp.get("ai_overseer"))
    return False


# ── Sessions ──────────────────────────────────────────────────────────────

def valid_until(session: Mapping[str, Any], req: Mapping[str, Any]) -> date:
    own = _d(session.get("valid_until"))
    return own or add_months(_d(session["held_on"]), req["refresh_months"])


def attended(attendance: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """{employee_id: {session_id, ...}}"""
    out: dict[str, set[str]] = {}
    for a in attendance:
        out.setdefault(a["employee_id"], set()).add(a["session_id"])
    return out


def cell(emp: Mapping[str, Any], req: Mapping[str, Any],
         sessions_by_id: Mapping[str, Mapping[str, Any]],
         sessions_of_emp: set[str], today: date) -> dict[str, Any]:
    """One person against one requirement: the latest session covering it."""
    if not needs(emp, req):
        return {"state": NOT_REQUIRED, "held_on": None, "valid_until": None, "session_id": None}
    best = None
    for sid in sessions_of_emp:
        s = sessions_by_id.get(sid)
        if not s or req["code"] not in (s.get("requirement_codes") or []):
            continue
        held = _d(s["held_on"])
        if held > today:            # planned, not attended yet
            continue
        until = valid_until(s, req)
        if best is None or until > best[1]:
            best = (s, until)
    if best is None:
        return {"state": ABSENT, "held_on": None, "valid_until": None, "session_id": None}
    s, until = best
    if until < today:
        state = EXPIRED
    elif (until - today).days <= EXPIRING_DAYS:
        state = EXPIRING
    else:
        state = CURRENT
    return {"state": state, "held_on": _d(s["held_on"]), "valid_until": until, "session_id": s["id"]}


def matrix(employees: Iterable[Mapping[str, Any]], reqs: Iterable[Mapping[str, Any]],
           sessions: Iterable[Mapping[str, Any]], attendance: Iterable[Mapping[str, Any]],
           today: date) -> dict[str, dict[str, dict[str, Any]]]:
    """{employee_id: {requirement code: cell}} for people still employed."""
    reqs = list(reqs)
    by_id = {s["id"]: s for s in sessions}
    att = attended(attendance)
    return {e["id"]: {r["code"]: cell(e, r, by_id, att.get(e["id"], set()), today) for r in reqs}
            for e in employees if is_active(e, today)}


def coverage(mx: Mapping[str, Mapping[str, Mapping[str, Any]]],
             reqs: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per requirement: how many people need it, and in which state they are."""
    out = {}
    for r in reqs:
        c = {"required": 0, CURRENT: 0, EXPIRING: 0, EXPIRED: 0, ABSENT: 0,
             "not_current": [], "next_due": None, "first_lapsed": None}
        for emp_id, row in mx.items():
            x = row.get(r["code"])
            if not x or x["state"] == NOT_REQUIRED:
                continue
            c["required"] += 1
            c[x["state"]] += 1
            if x["state"] in (EXPIRED, ABSENT):
                c["not_current"].append(emp_id)
            if x["state"] == EXPIRED and (c["first_lapsed"] is None or x["valid_until"] < c["first_lapsed"]):
                c["first_lapsed"] = x["valid_until"]
            if x["state"] in (CURRENT, EXPIRING) and (c["next_due"] is None or x["valid_until"] < c["next_due"]):
                c["next_due"] = x["valid_until"]
        out[r["code"]] = c
    return out


def due_list(employees: Iterable[Mapping[str, Any]], mx: Mapping[str, Mapping[str, Any]],
             reqs: Iterable[Mapping[str, Any]], today: date, horizon_days: int = 365) -> list[dict]:
    """Who needs which training by when, within the horizon: the plan.
    Never trained and expired come first, dated today."""
    names = {e["id"]: e for e in employees}
    out = []
    for r in reqs:
        for emp_id, row in mx.items():
            x = row.get(r["code"]) or {}
            st = x.get("state")
            if st in (ABSENT, EXPIRED):
                due = today
            elif st in (CURRENT, EXPIRING) and (x["valid_until"] - today).days <= horizon_days:
                due = x["valid_until"]
            else:
                continue
            out.append({"employee": names.get(emp_id, {}), "requirement": r, "state": st, "due": due})
    return sorted(out, key=lambda d: (d["due"], d["requirement"]["sort_order"],
                                      (d["employee"].get("name") or "").lower()))


def needs_attention(cov: Mapping[str, Mapping[str, Any]]) -> bool:
    """Anything to act on: someone not trained, lapsed, or lapsing soon."""
    return any(c[EXPIRED] or c[ABSENT] or c[EXPIRING] for c in cov.values())


# ── Action plan (tasks.py producer) ──────────────────────────────────────

def findings(client: Mapping[str, Any], reqs: Iterable[Mapping[str, Any]],
             employees: list[Mapping[str, Any]], sessions: list[Mapping[str, Any]],
             attendance: list[Mapping[str, Any]], today: date | None = None) -> list[dict]:
    """One task per requirement in force with someone not current, plus one
    when requirements apply and nobody is recorded yet."""
    from tasks import _finding, DUE, OPEN
    today = today or date.today()
    reqs = [r for r in applicable(reqs, client) if in_force(r, today)]
    if not reqs:
        return []
    active = [e for e in employees if is_active(e, today)]
    if not active:
        return [_finding("training", "no_people",
                         "Training: record your staff to track who needs which training",
                         OPEN, "No one is recorded on the Training page yet.", None,
                         link="training")]
    mx = matrix(active, reqs, sessions, attendance, today)
    cov = coverage(mx, reqs)
    out = []
    for r in reqs:
        c = cov[r["code"]]
        if not c["required"]:
            continue
        lapsing = c[EXPIRED] + c[ABSENT]
        if lapsing:
            detail = (f"{c[ABSENT]} never trained, {c[EXPIRED]} lapsed, "
                      f"of {c['required']} who need it")
            sev = DUE if c[EXPIRED] else OPEN
            out.append(_finding("training", r["code"],
                                f"Training: {r['label_en']} — {lapsing} of {c['required']} not current",
                                sev, detail, c["first_lapsed"], link="training"))
        elif c[EXPIRING]:
            out.append(_finding("training", r["code"],
                                f"Training: {r['label_en']} — {c[EXPIRING]} lapsing within "
                                f"{EXPIRING_DAYS} days",
                                OPEN, f"Next lapses on {c['next_due']:%d/%m/%Y}.",
                                c["next_due"], link="training"))
    return out


# ── Obligation register (obligation_register.DERIVATIONS) ────────────────

def verdict(obligation_id: str, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """What the training register records for one obligation, or None when
    there is nothing to derive from (no training data, nobody who needs it).
    ctx["training"]: {"requirements", "employees", "sessions", "attendance"}."""
    t = ctx.get("training")
    if not t:
        return None
    today = t.get("today") or date.today()
    reqs = [r for r in applicable(t["requirements"], ctx.get("client") or {})
            if r.get("obligation_id") == obligation_id and in_force(r, today)]
    employees = [e for e in t["employees"] if is_active(e, today)]
    if not reqs or not employees:
        return None
    mx = matrix(employees, reqs, t["sessions"], t["attendance"], today)
    cov = coverage(mx, reqs)
    names = {e["id"]: e.get("name") or "?" for e in employees}
    required = sum(c["required"] for c in cov.values())
    if not required:
        return None
    ok = sum(c[CURRENT] + c[EXPIRING] for c in cov.values())
    missing = sorted({names[i] for c in cov.values() for i in c["not_current"]})
    lbl = ", ".join(r["label_en"] for r in reqs)
    tail = (" The register records attendance, not competence: whether the "
            "training was appropriate is a judgement RECOSA does not make.")
    status = "compliant" if ok == required else ("missing" if ok == 0 else "partial")
    if status == "compliant":
        detail = f"All {required} people who need {lbl} have a current session recorded." + tail
    else:
        detail = f"{ok} of {required} people who need {lbl} have a current session recorded." + tail
    return {"status": status, "source": "derived", "detail": detail, "evidence": missing}
