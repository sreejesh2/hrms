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
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from setup.models import OrganizationSettings


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
        leftMargin=0.7 * cm,
        rightMargin=0.7 * cm,
        topMargin=0.6 * cm,
        bottomMargin=0.6 * cm,
        title=title,
    )

    styles = getSampleStyleSheet()
    company_style = ParagraphStyle(
        "AttCompany",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "AttTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    emp_style = ParagraphStyle(
        "AttEmp",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        alignment=TA_CENTER,
        spaceAfter=1,
    )
    period_style = ParagraphStyle(
        "AttPeriod",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    th_style = ParagraphStyle(
        "AttTh",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        alignment=TA_CENTER,
        leading=8,
    )
    cell_c = ParagraphStyle(
        "AttCellC",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        alignment=TA_CENTER,
        leading=9,
    )
    cell_r = ParagraphStyle(
        "AttCellR",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        alignment=TA_RIGHT,
        leading=9,
    )
    cell_l = ParagraphStyle(
        "AttCellL",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        alignment=TA_LEFT,
        leading=8,
    )
    group_style = ParagraphStyle(
        "AttGroup",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        alignment=TA_CENTER,
        leading=8,
    )

    story = [
        Paragraph(company, company_style),
        Paragraph("Attendance Report", title_style),
        Paragraph(employee_label, emp_style),
        Paragraph(period_label, period_style),
    ]

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
        ("BACKGROUND", (0, 1), (-1, 1), colors.Color(0.85, 0.85, 0.85)),
        ("GRID", (0, 1), (-1, -1), 0.4, colors.black),
        ("BOX", (0, 1), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        # Span PUNCH over IN/OUT
        ("SPAN", (4, 0), (5, 0)),
        ("BOX", (4, 0), (5, 0), 0.4, colors.black),
        ("BACKGROUND", (4, 0), (5, 0), colors.Color(0.92, 0.92, 0.92)),
        # Span IN HOURS over HOURS..Accr
        ("SPAN", (6, 0), (10, 0)),
        ("BOX", (6, 0), (10, 0), 0.4, colors.black),
        ("BACKGROUND", (6, 0), (10, 0), colors.Color(0.92, 0.92, 0.92)),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
    ]
    # Alternate row shading for data (skip group+header)
    for r in range(2, len(data)):
        if r % 2 == 0:
            style_cmds.append(
                ("BACKGROUND", (0, r), (-1, r), colors.Color(0.97, 0.97, 0.97))
            )
    # Total row
    last = len(data) - 1
    if last >= 2:
        style_cmds.append(("BACKGROUND", (0, last), (-1, last), colors.Color(0.9, 0.9, 0.9)))
        style_cmds.append(("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"))

    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(Spacer(1, 6 * mm))

    if show_signature:
        sig_style = ParagraphStyle(
            "AttSig",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            alignment=TA_LEFT,
            leading=11,
        )
        story.append(
            Paragraph(
                "I agree the above Attendance is correct and True By: "
                "_______________________________",
                sig_style,
            )
        )
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph("Supervisor _______________________________", sig_style)
        )

    doc.build(story)
    return buffer.getvalue()
