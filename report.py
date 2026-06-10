import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from checklist import AuditResult, OK, WARN, FAIL

# ── Brand colors ──────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1B2A4A")
PURPLE = colors.HexColor("#4A3B8C")
TEAL   = colors.HexColor("#0F6E56")
AMBER  = colors.HexColor("#BA7517")
CORAL  = colors.HexColor("#993C1D")
LGRAY  = colors.HexColor("#F4F3F0")
MGRAY  = colors.HexColor("#D3D1C7")
WHITE  = colors.white

RISK_COLORS = {
    "Green": colors.HexColor("#0F6E56"),
    "Amber": colors.HexColor("#BA7517"),
    "Red":   colors.HexColor("#993C1D"),
}

STATUS_COLORS_RL = {
    OK:   colors.HexColor("#0F6E56"),
    WARN: colors.HexColor("#BA7517"),
    FAIL: colors.HexColor("#993C1D"),
}

STATUS_ICONS = {
    OK:   "✓",
    WARN: "!",
    FAIL: "✗",
}

STATUS_LABELS = {
    OK:   "Compliant",
    WARN: "Needs attention",
    FAIL: "Missing",
}


def _styles():
    base = getSampleStyleSheet()
    custom = {}

    custom["title"] = ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=28,
        textColor=WHITE, alignment=TA_LEFT, spaceAfter=4
    )
    custom["subtitle"] = ParagraphStyle(
        "subtitle", fontName="Helvetica", fontSize=12,
        textColor=colors.HexColor("#CCCCCC"), alignment=TA_LEFT
    )
    custom["h1"] = ParagraphStyle(
        "h1", fontName="Helvetica-Bold", fontSize=16,
        textColor=NAVY, spaceBefore=16, spaceAfter=8
    )
    custom["h2"] = ParagraphStyle(
        "h2", fontName="Helvetica-Bold", fontSize=12,
        textColor=PURPLE, spaceBefore=12, spaceAfter=6
    )
    custom["body"] = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#333333"), spaceAfter=4, leading=14
    )
    custom["small"] = ParagraphStyle(
        "small", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#666666"), spaceAfter=2, leading=12
    )
    custom["label"] = ParagraphStyle(
        "label", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.HexColor("#333333")
    )
    custom["footer"] = ParagraphStyle(
        "footer", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#999999"), alignment=TA_CENTER
    )
    custom["cta_head"] = ParagraphStyle(
        "cta_head", fontName="Helvetica-Bold", fontSize=14,
        textColor=WHITE, alignment=TA_CENTER, spaceAfter=6
    )
    custom["cta_body"] = ParagraphStyle(
        "cta_body", fontName="Helvetica", fontSize=10,
        textColor=WHITE, alignment=TA_CENTER, spaceAfter=8
    )
    return custom


def _cover_table(audit: AuditResult, styles: dict) -> Table:
    """Build the cover header block."""
    risk_col = RISK_COLORS.get(audit.risk_level, NAVY)

    cover_data = [[
        Paragraph("COMPLAI", styles["title"]),
        Paragraph(f"Risk: {audit.risk_level.upper()}", ParagraphStyle(
            "risk", fontName="Helvetica-Bold", fontSize=16,
            textColor=WHITE, alignment=TA_RIGHT
        ))
    ], [
        Paragraph("Website Compliance Audit Report", styles["subtitle"]),
        Paragraph(f"Score: {audit.score}/100", ParagraphStyle(
            "score", fontName="Helvetica", fontSize=11,
            textColor=colors.HexColor("#CCCCCC"), alignment=TA_RIGHT
        ))
    ]]

    t = Table(cover_data, colWidths=[110 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _summary_table(audit: AuditResult, styles: dict) -> Table:
    """Build the summary stats table."""
    data = [
        [
            Paragraph("Audited URL", styles["small"]),
            Paragraph("Date", styles["small"]),
            Paragraph("Checks", styles["small"]),
            Paragraph("Compliant", styles["small"]),
            Paragraph("Attention", styles["small"]),
            Paragraph("Missing", styles["small"]),
        ],
        [
            Paragraph(audit.url, styles["label"]),
            Paragraph(datetime.now().strftime("%d %b %Y"), styles["label"]),
            Paragraph(str(len(audit.checks)), styles["label"]),
            Paragraph(str(audit.ok_count),   styles["label"]),
            Paragraph(str(audit.warn_count), styles["label"]),
            Paragraph(str(audit.fail_count), styles["label"]),
        ]
    ]
    col_w = [60*mm, 25*mm, 20*mm, 22*mm, 22*mm, 21*mm]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), LGRAY),
        ("BACKGROUND",    (0, 1), (-1, 1), WHITE),
        ("BOX",           (0, 0), (-1, -1), 0.5, MGRAY),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, MGRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # Colour the count cells
        ("TEXTCOLOR", (3, 1), (3, 1), TEAL),
        ("TEXTCOLOR", (4, 1), (4, 1), AMBER),
        ("TEXTCOLOR", (5, 1), (5, 1), CORAL),
        ("FONTNAME",  (3, 1), (5, 1), "Helvetica-Bold"),
        ("FONTSIZE",  (3, 1), (5, 1), 11),
    ]))
    return t


def _checklist_table(checks: list, styles: dict) -> list:
    """Build one table per regulation group."""
    elements = []

    # Group by regulation
    groups = {}
    for check in checks:
        groups.setdefault(check.regulation, []).append(check)

    for regulation, items in groups.items():
        elements.append(Paragraph(regulation, styles["h2"]))

        rows = []
        for item in items:
            icon = STATUS_ICONS[item.status]
            col = STATUS_COLORS_RL[item.status]
            label_style = ParagraphStyle(
                f"lbl_{item.id}", fontName="Helvetica-Bold",
                fontSize=9, textColor=colors.HexColor("#222222")
            )
            detail_style = ParagraphStyle(
                f"det_{item.id}", fontName="Helvetica",
                fontSize=8, textColor=colors.HexColor("#555555"), leading=12
            )
            rows.append([
                Paragraph(f'<font color="#{_hex(col)}">{icon}</font>', ParagraphStyle(
                    "icon", fontName="Helvetica-Bold", fontSize=12,
                    textColor=col, alignment=TA_CENTER
                )),
                Paragraph(f"{item.id} — {item.label}", label_style),
                Paragraph(STATUS_LABELS[item.status], ParagraphStyle(
                    "stat", fontName="Helvetica-Bold", fontSize=8,
                    textColor=col, alignment=TA_CENTER
                )),
                Paragraph(item.detail, detail_style),
            ])

        t = Table(rows, colWidths=[8*mm, 60*mm, 28*mm, 74*mm])
        style_cmds = [
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("BOX",           (0, 0), (-1, -1), 0.5, MGRAY),
            ("INNERGRID",     (0, 0), (-1, -1), 0.3, MGRAY),
        ]
        # Alternate row backgrounds
        for i in range(len(rows)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), LGRAY))
        t.setStyle(TableStyle(style_cmds))
        elements.append(t)
        elements.append(Spacer(1, 6))

    return elements


def _hex(color) -> str:
    """Convert ReportLab color to hex string without #."""
    try:
        r = int(color.red * 255)
        g = int(color.green * 255)
        b = int(color.blue * 255)
        return f"{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "333333"


def _cta_table(styles: dict) -> Table:
    """Build the CTA block at the end of the report."""
    cta_data = [[
        Paragraph("Ready to fix these gaps?", styles["cta_head"]),
    ], [
        Paragraph(
            "COMPLAI shows you exactly how to remediate each issue, generates the required documents "
            "(privacy policy, cookie policy, T&Cs), and monitors your compliance continuously.",
            styles["cta_body"]
        ),
    ], [
        Paragraph(
            "Start your free 15-day trial at complai.be — no credit card required.",
            ParagraphStyle("cta_link", fontName="Helvetica-Bold", fontSize=10,
                           textColor=colors.HexColor("#A8F0D8"), alignment=TA_CENTER)
        ),
    ]]
    t = Table(cta_data, colWidths=[170*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def generate_pdf(audit: AuditResult) -> bytes:
    """Generate the audit PDF report and return as bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
        title=f"COMPLAI Audit — {audit.url}",
        author="COMPLAI",
    )

    styles = _styles()
    story = []

    # Cover header
    story.append(_cover_table(audit, styles))
    story.append(Spacer(1, 8))

    # Summary stats
    story.append(_summary_table(audit, styles))
    story.append(Spacer(1, 12))

    # Section: What this audit covers
    story.append(Paragraph("What this audit covers", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=MGRAY, spaceAfter=8))
    story.append(Paragraph(
        "This automated audit checks your public website against key EU compliance requirements across "
        "six regulatory frameworks: GDPR, ePrivacy (Cookie Law), the European Accessibility Act (EAA), "
        "EU Consumer Rights / Distance Selling rules, NIS2 cybersecurity requirements, and the EU AI Act. "
        "It is based on publicly visible content only and does not assess internal processes, data flows, "
        "or technical infrastructure.",
        styles["body"]
    ))
    story.append(Spacer(1, 8))

    # Checklist
    story.append(Paragraph("Detailed findings", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=MGRAY, spaceAfter=8))
    story.extend(_checklist_table(audit.checks, styles))
    story.append(Spacer(1, 12))

    # Disclaimer
    story.append(HRFlowable(width="100%", thickness=0.5, color=MGRAY, spaceAfter=6))
    story.append(Paragraph(
        "Important: This report is generated automatically based on publicly accessible website content. "
        "It does not constitute legal advice. Some checks may produce false positives or negatives depending "
        "on your website's technical implementation. Always consult a qualified compliance professional for "
        "a full legal assessment.",
        styles["small"]
    ))
    story.append(Spacer(1, 12))

    # CTA
    story.append(KeepTogether(_cta_table(styles)))

    doc.build(story)
    return buffer.getvalue()
