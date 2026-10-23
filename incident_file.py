"""
incident_file.py — S53 part 2 (D-118). One PDF per incident: the record.

What an authority or an auditor asks for after the fact, and what GDPR
Art. 33(5) requires to exist: the facts, the effects, what was done, every
decision with its reason, and every notification — the text actually sent,
when, and the authority's reference. Built from the incident and its
append-only timeline, so it can be regenerated at any time and says the
same thing.

NO STREAMLIT, NO SUPABASE: the page passes the data in.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

import incident_rules as R

_YN = {True: "Yes", False: "No", None: "Not decided"}


def _p(text: Any, style) -> Paragraph:
    return Paragraph(escape(str(text if text not in (None, "") else "—")).replace("\n", "<br/>"), style)


def build_pdf(incident: Mapping[str, Any], client: Mapping[str, Any],
              events: Iterable[Mapping[str, Any]], deadlines: list[dict],
              system_names: list[str], contacts: Mapping[str, Mapping] | None = None) -> bytes:
    events = sorted(events, key=lambda e: R._ts(e["occurred_at"]))
    contacts = contacts or {}
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#555555"))
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=16, alignment=0, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor("#003366"))
    mono = ParagraphStyle("m", parent=body, fontName="Courier", fontSize=8, leading=10)

    def table(rows, widths):
        t = Table([[_p(a, body), _p(b, body)] for a, b in rows], colWidths=widths)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
                               ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555"))]))
        return t

    W = (45 * mm, 125 * mm)
    org = client.get("legal_name") or client.get("company_name") or ""
    s = []
    s.append(Paragraph(f"Incident file — {escape(incident['title'])}", h1))
    s.append(_p(f"{org} · status: {incident.get('status')} · generated "
                f"{R.when(datetime.now(timezone.utc))}", small))

    s.append(Paragraph("1. Facts", h2))
    s.append(table([
        ("Found out", R.when(incident["discovered_at"])),
        ("Reported by", incident.get("reported_by")),
        ("Systems affected", ", ".join(system_names) or None),
        ("What happened", incident.get("description")),
    ], W))

    s.append(Paragraph("2. Assessment", h2))
    exemption = incident.get("subjects_exemption")
    s.append(table([
        ("Personal data involved", _YN[incident.get("personal_data")]),
        ("GDPR risk", R.GDPR_RISK.get(incident.get("gdpr_risk"), "Not decided")),
        ("Telling the people — exemption", R.SUBJECTS_EXEMPTIONS.get(exemption) if exemption else None),
        ("Categories of data subjects", incident.get("subject_categories")),
        ("Categories of data", incident.get("data_categories")),
        ("People / records affected (approx.)",
         f"{incident.get('approx_subjects') or '—'} / {incident.get('approx_records') or '—'}"),
        ("Significant incident (NIS2)", _YN[incident.get("significant")] if R.nis2_applies(client) else "NIS2 does not apply"),
        ("Users of the service affected", _YN[incident.get("affects_recipients")]),
        ("Likely consequences", incident.get("likely_consequences")),
        ("Measures taken", incident.get("measures_taken")),
    ], W))

    decisions = [e for e in events if e["event_type"] == "decision"]
    s.append(Paragraph("3. Decisions and reasons", h2))
    if decisions:
        s.append(table([(R.when(e["occurred_at"]), e.get("body")) for e in decisions], W))
    else:
        s.append(_p("No assessment recorded.", body))

    s.append(Paragraph("4. Deadlines", h2))
    s.append(table([(R.label(d["kind"], "en", contacts), R.describe_left(d))
                    for d in sorted(deadlines, key=lambda d: d["kind"])
                    if d["required"] is not False or d["state"] == R.DONE], W))

    s.append(Paragraph("5. Notifications and reports sent", h2))
    sent = [e for e in events if e["event_type"] in ("notification", "followup")]
    if not sent:
        s.append(_p("None recorded.", body))
    for e in sent:
        head = ("Supplementary information — " if e["event_type"] == "followup" else "") \
            + R.label(e.get("kind") or "", "en", contacts)
        block = [_p(f"{head}", ParagraphStyle("hb", parent=body, fontName="Helvetica-Bold")),
                 _p(f"Sent {R.when(e['occurred_at'])}"
                    + (f" — reference {e['reference']}" if e.get("reference") else ""), small)]
        if e.get("body"):
            block.append(Preformatted(e["body"], mono, maxLineLength=110))
        block.append(Spacer(1, 6))
        s.append(KeepTogether(block[:2]))
        s.extend(block[2:])

    s.append(Paragraph("6. Team alerted", h2))
    alerts = [e for e in events if e["event_type"] == "alert"]
    s.append(table([(R.when(e["occurred_at"]), e.get("body")) for e in alerts], W) if alerts
             else _p("No team alert recorded.", body))

    s.append(Paragraph("7. Timeline", h2))
    rows = [(R.when(incident["discovered_at"]), "Found out")]
    for e in events:
        what = {"decision": "Assessment recorded", "notification": "Sent",
                "followup": "Supplementary information sent", "status": "Status",
                "note": "Note", "reminder": "Reminder emailed", "alert": "Team alerted",
                "request": "Request from an authority"}.get(e["event_type"], e["event_type"])
        detail = R.label(e["kind"], "en", contacts) if e.get("kind") and e["event_type"] in ("notification", "followup", "request") else ""
        extra = e.get("body") if e["event_type"] in ("status", "note", "request") else ""
        rows.append((R.when(e["occurred_at"]), " — ".join(x for x in (what, detail, extra) if x)))
    s.append(table(rows, W))

    s.append(Paragraph("8. Review", h2))
    s.append(table([
        ("Closed", R.when(incident.get("closed_at")) or None),
        ("Root cause", incident.get("root_cause")),
        ("What changed", incident.get("lessons")),
    ], W))

    s.append(Spacer(1, 10))
    s.append(_p(f"Times in {R.TZ_LABEL}. Built from RECOSA's incident record, whose timeline cannot "
                "be edited. Kept as the documentation GDPR Art. 33(5) requires.", small))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm,
                      title=f"Incident file — {incident['title']}").build(s)
    return buf.getvalue()
