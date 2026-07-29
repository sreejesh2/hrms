"""ReportLab PDF for employee attendance sheet (xhtml2pdf cannot layout this table)."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from setup.models import OrganizationSettings


NAVY = colors.HexColor("#16324F")
TEAL = colors.HexColor("#0D9488")
TEAL_DARK = colors.HexColor("#0F766E")
TEAL_SOFT = colors.HexColor("#E6F6F3")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#667085")
BORDER = colors.HexColor("#D8E0E8")
ROW_ALT = colors.HexColor("#F7F9FB")
WEEKEND = colors.HexColor("#EFF6FF")
ABSENT = colors.HexColor("#FEF2F2")
LEAVE = colors.HexColor("#FFFBEB")


# Column widths for landscape A4 usable width (~27.7cm with margins)
COL_WIDTHS = [
    2.2 * cm,  # DATE
    1.2 * cm,  # WEEK
    1.0 * cm,  # TYP
    1.8 * cm,  # SHIFT
    1.6 * cm,  # IN
    1.6 * cm,  # OUT
    1.5 * cm,  # HOURS
    1.5 * cm,  # OT
    1.5 * cm,  # C.OT
    1.4 * cm,  # Ded
    1.7 * cm,  # Accr. Ded
    5.5 * cm,  # STATUS
]


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    s = "" if text is None else str(text)
    s = (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return Paragraph(s, style)


def _decimal(value: Any) -> float:
    try:
        text = str(value).rstrip("NWH")
        return float(text or 0)
    except (TypeError, ValueError):
        return 0.0


def build_employee_attendance_pdf(
    *,
    title: str,
    employee_label: str,
    period_label: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    company_name: str | None = None,
    show_signature: bool = True,
) -> bytes:
    org = OrganizationSettings.load()
    company = company_name or org.display_name

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.8 * cm,
        rightMargin=0.8 * cm,
        topMargin=0.65 * cm,
        bottomMargin=0.9 * cm,
        title=title,
        author=company,
        subject=f"Attendance report · {employee_label} · {period_label}",
    )

    styles = getSampleStyleSheet()
    company_style = ParagraphStyle(
        "AttCompany",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        textColor=NAVY,
        leading=17,
    )
    title_style = ParagraphStyle(
        "AttTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.white,
        alignment=TA_RIGHT,
        leading=14,
    )
    company_meta_style = ParagraphStyle(
        "AttCompanyMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        textColor=MUTED,
        leading=9,
    )
    label_style = ParagraphStyle(
        "AttLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.5,
        textColor=TEAL_DARK,
        leading=8,
        spaceAfter=1,
    )
    value_style = ParagraphStyle(
        "AttValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=INK,
        leading=11,
    )
    kpi_value_style = ParagraphStyle(
        "AttKpiValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=NAVY,
        alignment=TA_CENTER,
        leading=11,
    )
    kpi_label_style = ParagraphStyle(
        "AttKpiLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=5.8,
        textColor=MUTED,
        alignment=TA_CENTER,
        leading=7,
    )
    th_style = ParagraphStyle(
        "AttTh",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.6,
        textColor=colors.white,
        alignment=TA_CENTER,
        leading=7.5,
    )
    cell_c = ParagraphStyle(
        "AttCellC",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        textColor=INK,
        alignment=TA_CENTER,
        leading=8,
    )
    cell_r = ParagraphStyle(
        "AttCellR",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        textColor=INK,
        alignment=TA_RIGHT,
        leading=8,
    )
    cell_l = ParagraphStyle(
        "AttCellL",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.7,
        textColor=INK,
        alignment=TA_LEFT,
        leading=7.5,
    )
    group_style = ParagraphStyle(
        "AttGroup",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6,
        textColor=TEAL_DARK,
        alignment=TA_CENTER,
        leading=7,
    )

    company_meta = " · ".join(
        part
        for part in (
            org.address_block.replace("\n", ", "),
            org.phone,
            org.email,
            org.website,
        )
        if part
    )
    brand_parts = []
    if org.logo:
        try:
            logo = Image(org.logo.path)
            logo._restrictSize(2.4 * cm, 1.15 * cm)
            brand_parts.append(logo)
        except (OSError, ValueError):
            pass
    brand_copy = Table(
        [
            [Paragraph(company, company_style)],
            [Paragraph(company_meta, company_meta_style)],
        ],
        colWidths=[12.9 * cm],
    )
    brand_copy.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    brand_parts.append(brand_copy)
    brand = Table([brand_parts], colWidths=[2.7 * cm, 12.9 * cm] if len(brand_parts) == 2 else [15.6 * cm])
    brand.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    report_badge = Table(
        [
            [Paragraph("ATTENDANCE REPORT", title_style)],
            [Paragraph(period_label, ParagraphStyle(
                "AttBadgePeriod",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=7.5,
                textColor=colors.HexColor("#CCFBF1"),
                alignment=TA_RIGHT,
                leading=9,
            ))],
        ],
        colWidths=[10.3 * cm],
    )
    report_badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
            ]
        )
    )
    header = Table([[brand, report_badge]], colWidths=[15.6 * cm, 10.3 * cm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    detail = Table(
        [
            [
                [Paragraph("EMPLOYEE", label_style), Paragraph(employee_label, value_style)],
                [Paragraph("ATTENDANCE PERIOD", label_style), Paragraph(period_label, value_style)],
            ]
        ],
        colWidths=[12.95 * cm, 12.95 * cm],
    )
    detail.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), TEAL_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    data_rows = [row for row in rows if row and str(row[0]).upper() != "TOTAL"]
    total_row = next(
        (row for row in rows if row and str(row[0]).upper() == "TOTAL"),
        None,
    )
    total_hours = sum(_decimal(row[6]) for row in data_rows if len(row) > 6)
    total_ot = _decimal(total_row[7]) if total_row and len(total_row) > 7 else sum(
        _decimal(row[7]) for row in data_rows if len(row) > 7
    )
    total_cot = _decimal(total_row[8]) if total_row and len(total_row) > 8 else sum(
        _decimal(row[8]) for row in data_rows if len(row) > 8
    )
    total_ded = _decimal(total_row[9]) if total_row and len(total_row) > 9 else sum(
        _decimal(row[9]) for row in data_rows if len(row) > 9
    )
    kpi_data = [
        [
            [Paragraph(str(len(data_rows)), kpi_value_style), Paragraph("DAYS IN PERIOD", kpi_label_style)],
            [Paragraph(f"{total_hours:.2f}", kpi_value_style), Paragraph("WORKED HOURS", kpi_label_style)],
            [Paragraph(f"{total_ot:.2f}", kpi_value_style), Paragraph("OT HOURS", kpi_label_style)],
            [Paragraph(f"{total_cot:.2f}", kpi_value_style), Paragraph("CREDITED OT", kpi_label_style)],
            [Paragraph(f"{total_ded:.2f}", kpi_value_style), Paragraph("DEDUCTION HOURS", kpi_label_style)],
        ]
    ]
    kpis = Table(kpi_data, colWidths=[5.18 * cm] * 5)
    kpis.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    story = [header, Spacer(1, 2.5 * mm), detail, Spacer(1, 2 * mm), kpis, Spacer(1, 2.5 * mm)]

    # Group header row (PUNCH / IN HOURS)
    group_row = [
        "",
        "",
        "",
        "",
        _p("PUNCH", group_style),
        "",
        _p("IN HOURS", group_style),
        "",
        "",
        "",
        "",
        "",
    ]
    header_row = [_p(h, th_style) for h in headers]

    right_cols = {6, 7, 8, 9, 10}  # HOURS..Accr
    data = [group_row, header_row]
    for i, row in enumerate(rows):
        cells = []
        for col_i, val in enumerate(row):
            if col_i in right_cols:
                style = cell_r
            elif col_i == 11:
                style = cell_l
            else:
                style = cell_c
            text = str(val) if val is not None else ""
            cells.append(_p(text, style))
        data.append(cells)

    table = Table(data, colWidths=COL_WIDTHS, repeatRows=2)
    style_cmds = [
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, 1), NAVY),
        ("LINEBELOW", (0, 1), (-1, 1), 0.8, TEAL),
        ("GRID", (0, 1), (-1, -1), 0.35, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.7, NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        # Span PUNCH over IN/OUT
        ("SPAN", (4, 0), (5, 0)),
        ("BOX", (4, 0), (5, 0), 0.35, BORDER),
        ("BACKGROUND", (4, 0), (5, 0), TEAL_SOFT),
        # Span IN HOURS over HOURS..Accr
        ("SPAN", (6, 0), (10, 0)),
        ("BOX", (6, 0), (10, 0), 0.35, BORDER),
        ("BACKGROUND", (6, 0), (10, 0), TEAL_SOFT),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
    ]
    # Alternate row shading for data (skip group+header)
    for r in range(2, len(data)):
        source_row = rows[r - 2]
        week = str(source_row[1]) if len(source_row) > 1 else ""
        status = str(source_row[11]) if len(source_row) > 11 else ""
        if str(source_row[0]).upper() == "TOTAL":
            continue
        if status.lower().startswith("absent"):
            row_color = ABSENT
        elif "leave" in status.lower():
            row_color = LEAVE
        elif week.lower() == "sun":
            row_color = WEEKEND
        elif r % 2 == 0:
            row_color = ROW_ALT
        else:
            row_color = colors.white
        style_cmds.append(("BACKGROUND", (0, r), (-1, r), row_color))
    # Total row
    last = len(data) - 1
    if last >= 2:
        style_cmds.append(("BACKGROUND", (0, last), (-1, last), TEAL_SOFT))
        style_cmds.append(("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"))
        style_cmds.append(("LINEABOVE", (0, last), (-1, last), 1, TEAL_DARK))

    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(Spacer(1, 1.5 * mm))

    if show_signature:
        sig_style = ParagraphStyle(
            "AttSig",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7,
            textColor=MUTED,
            alignment=TA_CENTER,
            leading=9,
        )
        signature_table = Table(
            [
                [
                    Paragraph("EMPLOYEE CONFIRMATION", label_style),
                    Paragraph("SUPERVISOR APPROVAL", label_style),
                ],
                [
                    Paragraph("<br/>Signature  ____________________ &nbsp;&nbsp; Date  ____________", sig_style),
                    Paragraph("<br/>Signature  ____________________ &nbsp;&nbsp; Date  ____________", sig_style),
                ],
            ],
            colWidths=[12.7 * cm, 12.7 * cm],
        )
        signature_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                    ("BACKGROUND", (0, 0), (-1, 0), ROW_ALT),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, 0), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                    ("TOPPADDING", (0, 1), (-1, 1), 2),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
                ]
            )
        )
        story.append(KeepTogether([signature_table]))

    def draw_page(canvas, pdf_doc):
        canvas.saveState()
        page_width, _ = landscape(A4)
        y = 0.48 * cm
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.35)
        canvas.line(doc.leftMargin, y + 5, page_width - doc.rightMargin, y + 5)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(doc.leftMargin, y - 1, f"{company} · Confidential attendance record")
        canvas.drawRightString(
            page_width - doc.rightMargin,
            y - 1,
            f"Page {pdf_doc.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()
