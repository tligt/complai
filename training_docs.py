"""
training_docs.py — S60 (D-159). The two training documents, Tier 1 (no LLM).

    build_plan_pdf        the training plan: what the law asks of whom, where
                          each person stands, who is due by when, and what
                          was given in the last twelve months.
    build_attestation_pdf one session's attendance attestation: what was
                          given, when, by whom, to whom, with signature lines.

English or French. Built from the register, so either can be regenerated at
any time and says the same thing. Both state that they are evidence of a plan
and of attendance, not of competence.

NO STREAMLIT, NO SUPABASE: the page passes the data in.
"""

from __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any, Iterable, Mapping
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import training_rules as TR

T = {
    "en": {
        "plan": "Training plan", "att": "Attendance attestation",
        "generated": "Generated", "company": "Organisation",
        "s1": "1. What the law asks, and of whom", "s2": "2. Where each person stands",
        "s3": "3. Due in the next twelve months", "s4": "4. Training given in the last twelve months",
        "req": "Training", "who": "Who needs it", "refresh": "Refresh", "basis": "Legal basis",
        "months": "every {n} months (RECOSA default; the law says \"regular\")",
        "from": "applies from {d}",
        "person": "Person", "role": "Role", "due": "Due by", "status": "Status",
        "now": "now", "none_due": "Nobody is due in the next twelve months.",
        "none_given": "No training recorded in the last twelve months.",
        "none_people": "No one is recorded yet.",
        "date": "Date", "title": "Title", "covers": "Covers", "attendees": "Attendees",
        "legend": "Legend: {c} current · {x} expiring within {d} days · {e} expired · {a} never trained · – not required.",
        "disclaimer": ("This plan records who needs which training and who attended which session. "
                       "It is evidence of a plan and of attendance, not of competence: whether the "
                       "training was appropriate is for the organisation to judge."),
        "session": "Session", "held": "Held on", "duration": "Duration", "format": "Format",
        "provider": "Provider", "trainer": "Trainer", "content": "Content",
        "minutes": "{n} minutes", "valid": "Counts until",
        "certify": ("The undersigned confirms that the people listed below attended the session "
                    "described above."),
        "name": "Name", "jobtitle": "Job title", "signature": "Signature",
        "organiser": "Organiser / trainer — name, date and signature",
        "att_disclaimer": ("This attestation records attendance. It is not a certificate of "
                           "competence."),
    },
    "fr": {
        "plan": "Plan de formation", "att": "Attestation de présence",
        "generated": "Généré le", "company": "Organisation",
        "s1": "1. Ce que la loi exige, et de qui", "s2": "2. Situation de chaque personne",
        "s3": "3. Échéances des douze prochains mois", "s4": "4. Formations données ces douze derniers mois",
        "req": "Formation", "who": "Public concerné", "refresh": "Renouvellement", "basis": "Base légale",
        "months": "tous les {n} mois (défaut RECOSA ; la loi dit « régulière »)",
        "from": "applicable à partir du {d}",
        "person": "Personne", "role": "Fonction", "due": "À faire avant le", "status": "Statut",
        "now": "maintenant", "none_due": "Aucune échéance dans les douze prochains mois.",
        "none_given": "Aucune formation enregistrée ces douze derniers mois.",
        "none_people": "Personne n'est encore enregistré.",
        "date": "Date", "title": "Intitulé", "covers": "Couvre", "attendees": "Participants",
        "legend": "Légende : {c} à jour · {x} expire dans les {d} jours · {e} expirée · {a} jamais formé · – non requis.",
        "disclaimer": ("Ce plan indique qui doit suivre quelle formation et qui a assisté à quelle "
                       "session. Il prouve l'existence d'un plan et la présence, non la compétence : "
                       "l'adéquation de la formation relève de l'appréciation de l'organisation."),
        "session": "Session", "held": "Date", "duration": "Durée", "format": "Format",
        "provider": "Organisme", "trainer": "Formateur", "content": "Contenu",
        "minutes": "{n} minutes", "valid": "Valable jusqu'au",
        "certify": ("Le soussigné confirme que les personnes énumérées ci-dessous ont assisté à "
                    "la session décrite ci-dessus."),
        "name": "Nom", "jobtitle": "Fonction", "signature": "Signature",
        "organiser": "Organisateur / formateur — nom, date et signature",
        "att_disclaimer": ("Cette attestation constate une présence. Elle ne certifie pas une "
                           "compétence."),
    },
}

# Plain markers: the PDF's base fonts have no emoji.
_MARK = {TR.CURRENT: "OK", TR.EXPIRING: "!", TR.EXPIRED: "X", TR.ABSENT: "o", TR.NOT_REQUIRED: "–"}
_MARK_COLOUR = {TR.CURRENT: "#1B7F3B", TR.EXPIRING: "#B7791F", TR.EXPIRED: "#C53030",
                TR.ABSENT: "#555555", TR.NOT_REQUIRED: "#999999"}


def _fd(d: Any) -> str:
    d = TR._d(d)
    return d.strftime("%d/%m/%Y") if d else "—"


def _styles():
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9, leading=12)
    return {
        "body": body,
        "bold": ParagraphStyle("bb", parent=body, fontName="Helvetica-Bold"),
        "small": ParagraphStyle("s", parent=body, fontSize=8, leading=10,
                                textColor=colors.HexColor("#555555")),
        "cell": ParagraphStyle("c", parent=body, fontSize=8, leading=10),
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontSize=16, alignment=0, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10,
                             spaceAfter=4, textColor=colors.HexColor("#003366")),
    }


def _p(text: Any, style) -> Paragraph:
    return Paragraph(escape(str(text if text not in (None, "") else "—")).replace("\n", "<br/>"), style)


def _grid(rows: list[list[Any]], widths, header: bool = True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD"))]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF2"))]
    t.setStyle(TableStyle(style))
    return t


def _org(client: Mapping[str, Any]) -> str:
    return client.get("legal_name") or client.get("company_name") or ""


# ── The training plan ─────────────────────────────────────────────────────

def build_plan_pdf(client: Mapping[str, Any], reqs: list[Mapping[str, Any]],
                   employees: list[Mapping[str, Any]], sessions: list[Mapping[str, Any]],
                   attendance: list[Mapping[str, Any]], today: date,
                   lang: str = "en") -> bytes:
    lang = "fr" if lang == "fr" else "en"
    t = T[lang]
    S = _styles()
    aud = TR.AUDIENCES_FR if lang == "fr" else TR.AUDIENCES
    reqs = TR.applicable(reqs, client)
    active = sorted([e for e in employees if TR.is_active(e, today)],
                    key=lambda e: (e.get("name") or "").lower())
    mx = TR.matrix(active, reqs, sessions, attendance, today)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"{t['plan']} — {_org(client)}")
    width = landscape(A4)[0] - 28 * mm
    s: list[Any] = [Paragraph(escape(f"{t['plan']} — {_org(client)}"), S["h1"]),
                    _p(f"{t['generated']} {_fd(today)}", S["small"]), Spacer(1, 4),
                    _p(t["disclaimer"], S["small"])]

    # 1. Requirements
    s.append(Paragraph(t["s1"], S["h2"]))
    rows = [[_p(t["req"], S["bold"]), _p(t["who"], S["bold"]), _p(t["refresh"], S["bold"]),
             _p(t["basis"], S["bold"])]]
    for r in reqs:
        refresh = t["months"].format(n=r["refresh_months"])
        if r.get("applies_from") and r["applies_from"] > today:
            refresh += " · " + t["from"].format(d=_fd(r["applies_from"]))
        rows.append([_p(TR.label(r, lang), S["cell"]), _p(aud.get(r["audience"], r["audience"]), S["cell"]),
                     _p(refresh, S["cell"]), _p(r["anchor"], S["cell"])])
    s.append(_grid(rows, [width * .27, width * .28, width * .25, width * .20]))

    # 2. Matrix
    s.append(Paragraph(t["s2"], S["h2"]))
    if not active:
        s.append(_p(t["none_people"], S["body"]))
    else:
        head = [_p(t["person"], S["bold"])] + [_p(TR.label(r, lang), S["bold"]) for r in reqs]
        rows = [head]
        for e in active:
            line = [_p(e.get("name") + (f"\n{e['job_title']}" if e.get("job_title") else ""), S["cell"])]
            for r in reqs:
                c = mx[e["id"]][r["code"]]
                txt = _MARK[c["state"]]
                if c.get("valid_until"):
                    txt += f" {_fd(c['valid_until'])}"
                line.append(Paragraph(f'<font color="{_MARK_COLOUR[c["state"]]}">{escape(txt)}</font>',
                                      S["cell"]))
            rows.append(line)
        first = width * .24
        rest = (width - first) / max(len(reqs), 1)
        s.append(_grid(rows, [first] + [rest] * len(reqs)))
        s.append(Spacer(1, 3))
        s.append(_p(t["legend"].format(c="OK", x="!", d=TR.EXPIRING_DAYS, e="X", a="o"), S["small"]))

    # 3. Due within twelve months
    s.append(Paragraph(t["s3"], S["h2"]))
    due = TR.due_list(active, mx, reqs, today)
    if not due:
        s.append(_p(t["none_due"], S["body"]))
    else:
        labels = TR.STATE_LABELS[lang]
        rows = [[_p(t["due"], S["bold"]), _p(t["person"], S["bold"]), _p(t["req"], S["bold"]),
                 _p(t["status"], S["bold"])]]
        for d in due:
            rows.append([_p(t["now"] if d["due"] <= today else _fd(d["due"]), S["cell"]),
                         _p(d["employee"].get("name"), S["cell"]),
                         _p(TR.label(d["requirement"], lang), S["cell"]),
                         _p(labels[d["state"]], S["cell"])])
        s.append(_grid(rows, [width * .15, width * .30, width * .35, width * .20]))

    # 4. Given in the last twelve months
    s.append(Paragraph(t["s4"], S["h2"]))
    since = today - timedelta(days=365)
    recent = [x for x in sessions if since <= TR._d(x["held_on"]) <= today]
    by_session: dict[str, int] = {}
    for a in attendance:
        by_session[a["session_id"]] = by_session.get(a["session_id"], 0) + 1
    req_by_code = {r["code"]: r for r in reqs}
    if not recent:
        s.append(_p(t["none_given"], S["body"]))
    else:
        rows = [[_p(t["date"], S["bold"]), _p(t["title"], S["bold"]), _p(t["covers"], S["bold"]),
                 _p(t["attendees"], S["bold"])]]
        for x in sorted(recent, key=lambda x: x["held_on"], reverse=True):
            covers = ", ".join(TR.label(req_by_code[c], lang) for c in (x.get("requirement_codes") or [])
                               if c in req_by_code)
            rows.append([_p(_fd(x["held_on"]), S["cell"]), _p(x.get("title"), S["cell"]),
                         _p(covers, S["cell"]), _p(by_session.get(x["id"], 0), S["cell"])])
        s.append(_grid(rows, [width * .12, width * .38, width * .38, width * .12]))

    doc.build(s)
    return buf.getvalue()


# ── One session's attendance attestation ─────────────────────────────────

def build_attestation_pdf(client: Mapping[str, Any], session: Mapping[str, Any],
                          attendees: Iterable[Mapping[str, Any]], reqs: list[Mapping[str, Any]],
                          lang: str = "en") -> bytes:
    lang = "fr" if lang == "fr" else "en"
    t = T[lang]
    S = _styles()
    fmts = TR.FORMATS_FR if lang == "fr" else TR.FORMATS
    req_by_code = {r["code"]: r for r in reqs}
    attendees = sorted(attendees, key=lambda e: (e.get("name") or "").lower())

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{t['att']} — {session.get('title')}")
    width = A4[0] - 36 * mm
    s: list[Any] = [Paragraph(escape(t["att"]), S["h1"]),
                    _p(f"{t['company']}: {_org(client)}", S["body"]), Spacer(1, 6)]

    covers = "\n".join(f"{TR.label(req_by_code[c], lang)} ({req_by_code[c]['anchor']})"
                       for c in (session.get("requirement_codes") or []) if c in req_by_code)
    dur = session.get("duration_minutes")
    rows = [
        (t["session"], session.get("title")),
        (t["held"], _fd(session.get("held_on"))),
        (t["duration"], t["minutes"].format(n=dur) if dur else None),
        (t["format"], fmts.get(session.get("format"), session.get("format"))),
        (t["provider"], session.get("provider")),
        (t["trainer"], session.get("trainer")),
        (t["covers"], covers or None),
        (t["content"], session.get("content")),
    ]
    if session.get("valid_until"):
        rows.append((t["valid"], _fd(session["valid_until"])))
    s.append(_grid([[_p(a, S["small"]), _p(b, S["body"])] for a, b in rows],
                   [width * .25, width * .75], header=False))

    s.append(Spacer(1, 10))
    s.append(_p(t["certify"], S["body"]))
    s.append(Spacer(1, 6))
    grid = [[_p("#", S["bold"]), _p(t["name"], S["bold"]), _p(t["jobtitle"], S["bold"]),
             _p(t["signature"], S["bold"])]]
    for i, e in enumerate(attendees, 1):
        grid.append([_p(i, S["cell"]), _p(e.get("name"), S["cell"]), _p(e.get("job_title"), S["cell"]),
                     _p(" ", S["cell"])])
    tbl = Table(grid, colWidths=[width * .06, width * .38, width * .30, width * .26], repeatRows=1,
                rowHeights=[None] + [9 * mm] * len(attendees))
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF2"))]))
    s.append(tbl)

    s.append(Spacer(1, 18))
    s.append(_p(t["organiser"], S["small"]))
    s.append(Spacer(1, 22))
    s.append(_p("_" * 60, S["small"]))
    s.append(Spacer(1, 10))
    s.append(_p(t["att_disclaimer"], S["small"]))
    doc.build(s)
    return buf.getvalue()
