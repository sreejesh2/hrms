"""Print-ready ReportLab PDF for the wide company salary sheet."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from setup.models import OrganizationSettings


NAVY = colors.HexColor("#16283F")
TEAL = colors.HexColor("#0F8E84")
TEAL_SOFT = colors.HexColor("#E8F6F4")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#667085")
BORDER = colors.HexColor("#AEB9C5")
ROW_ALT = colors.HexColor("#F6F8FA")
TOTAL_BG = colors.HexColor("#DDEDEA")

# 39.2 cm total; fits landscape A3 with 1.2 cm side margins.
COL_WIDTHS = [
    0.8 * cm,   # Sl.No
    1.8 * cm,   # EMP-Code
    5.0 * cm,   # Name
    1.3 * cm,   # W-Days
    1.8 * cm,   # Basic
    1.8 * cm,   # COL
    1.5 * cm,   # OT Hours
    1.8 * cm,   # OT Amt
    2.0 * cm,   # Total Salary
    1.8 * cm,   # Food
    1.5 * cm,   # HRA
    1.8 * cm,   # Extra OT
    1.9 * cm,   # Extra Allow
    2.0 * cm,   # Gross
    2.0 * cm,   # Other Ded.
    2.0 * cm,   # Net
    2.1 * cm,   # Bank
]

MONEY_COLS = {4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15}
SUM_COLS = {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}


def _escape(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_escape(value), style)


def _number(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _display(value: Any, col: int) -> str:
    if value in (None, ""):
        return ""
    if col in MONEY_COLS:
        return f"{_number(value):,.2f}"
    if col in {3, 6}:
        number = _number(value)
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def build_company_salary_sheet_pdf(
    *,
    title: str,
    period_label: str,
    currency: str,
    status_label: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> bytes:
    org = OrganizationSettings.load()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A3),
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=0.9 * cm,
        bottomMargin=1.2 * cm,
        title=title,
        author=org.display_name,
        subject=f"Salary sheet · {period_label}",
    )

    styles = getSampleStyleSheet()
    company_style = ParagraphStyle(
        "SalaryCompany",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
        textColor=NAVY,
    )
    meta_style = ParagraphStyle(
        "SalaryMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=MUTED,
    )
    title_style = ParagraphStyle(
        "SalaryTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        alignment=TA_RIGHT,
        textColor=NAVY,
    )
    period_style = ParagraphStyle(
        "SalaryPeriod",
        parent=meta_style,
        alignment=TA_RIGHT,
    )
    header_style = ParagraphStyle(
        "SalaryHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.2,
        leading=7,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    text_style = ParagraphStyle(
        "SalaryText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
        alignment=TA_LEFT,
        textColor=INK,
    )
    center_style = ParagraphStyle(
        "SalaryCenter",
        parent=text_style,
        alignment=TA_CENTER,
    )
    number_style = ParagraphStyle(
        "SalaryNumber",
        parent=text_style,
        alignment=TA_RIGHT,
    )
    total_style = ParagraphStyle(
        "SalaryTotal",
        parent=number_style,
        fontName="Helvetica-Bold",
    )

    brand_parts: list[Any] = []
    if org.logo:
        try:
            logo = Image(org.logo.path)
            logo._restrictSize(2.6 * cm, 1.25 * cm)
            brand_parts.append(logo)
        except (OSError, ValueError):
            pass
    company_meta = " · ".join(
        part
        for part in (
            org.address_block.replace("\n", ", "),
            org.phone,
            org.email,
        )
        if part
    )
    brand_copy = Table(
        [
            [_paragraph(org.display_name, company_style)],
            [_paragraph(company_meta, meta_style)],
        ],
        colWidths=[16.8 * cm],
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
    brand = Table(
        [brand_parts],
        colWidths=[3.0 * cm, 16.8 * cm] if len(brand_parts) == 2 else [19.8 * cm],
    )
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

    meta = (
        f"Period: {period_label}  |  "
        f"Currency: {currency or '—'}  |  Status: {status_label or '—'}"
    )
    report_title = Table(
        [
            [_paragraph("COMPANY SALARY SHEET", title_style)],
            [_paragraph(meta, period_style)],
        ],
        colWidths=[19.4 * cm],
    )
    report_title.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    heading = Table(
        [[brand, report_title]],
        colWidths=[19.8 * cm, 19.4 * cm],
    )
    heading.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 1.3, TEAL),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story: list[Any] = [heading, Spacer(1, 0.22 * cm)]
    if not rows:
        story.append(_paragraph("No payslips are available for this payroll period.", text_style))
    else:
        table_data: list[list[Any]] = [
            [_paragraph(header, header_style) for header in headers]
        ]
        totals = [Decimal("0") for _ in headers]
        for raw_row in rows:
            row: list[Any] = []
            for col, value in enumerate(raw_row):
                if col in SUM_COLS:
                    totals[col] += _number(value)
                style = number_style if col in MONEY_COLS or col in {3, 6} else text_style
                if col in {0, 1, 16}:
                    style = center_style
                row.append(_paragraph(_display(value, col), style))
            table_data.append(row)

        total_row: list[Any] = []
        for col in range(len(headers)):
            if col == 2:
                total_row.append(_paragraph("TOTAL", total_style))
            elif col in SUM_COLS:
                total_row.append(_paragraph(_display(totals[col], col), total_style))
            else:
                total_row.append("")
        table_data.append(total_row)

        table = LongTable(
            table_data,
            colWidths=COL_WIDTHS,
            repeatRows=1,
            hAlign="LEFT",
        )
        last = len(table_data) - 1
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("TOPPADDING", (0, 1), (-1, -2), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -2), 3),
            ("BACKGROUND", (0, last), (-1, last), TOTAL_BG),
            ("LINEABOVE", (0, last), (-1, last), 1.1, TEAL),
            ("TOPPADDING", (0, last), (-1, last), 4),
            ("BOTTOMPADDING", (0, last), (-1, last), 4),
        ]
        for row_index in range(2, last, 2):
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), ROW_ALT))
        table.setStyle(TableStyle(commands))
        story.append(table)

    def draw_page(canvas, pdf_doc):
        canvas.saveState()
        width, _ = landscape(A3)
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(0.7)
        canvas.line(1.2 * cm, 0.72 * cm, width - 1.2 * cm, 0.72 * cm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(1.2 * cm, 0.42 * cm, f"{org.display_name} · {period_label}")
        canvas.drawRightString(
            width - 1.2 * cm,
            0.42 * cm,
            f"Page {pdf_doc.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()


def build_monthly_payroll_register_pdf(
    *,
    title: str,
    period_label: str,
    currency: str,
    status_label: str,
    sheets: Sequence[Any],
    earning_codes: Sequence[str],
    deduction_codes: Sequence[str],
) -> bytes:
    """Readable A3 payroll register with summary and component sections."""
    org = OrganizationSettings.load()
    register = sheets[0] if sheets else None
    headers = list(register.headers) if register else []
    rows = list(register.rows) if register else []

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A3),
        leftMargin=1.15 * cm,
        rightMargin=1.15 * cm,
        topMargin=0.85 * cm,
        bottomMargin=1.15 * cm,
        title=title,
        author=org.display_name,
        subject=f"Payroll register · {period_label}",
    )

    styles = getSampleStyleSheet()
    company_style = ParagraphStyle(
        "RegCompany",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
        textColor=NAVY,
    )
    meta_style = ParagraphStyle(
        "RegMeta",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=MUTED,
    )
    title_style = ParagraphStyle(
        "RegTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        alignment=TA_RIGHT,
        textColor=NAVY,
    )
    section_style = ParagraphStyle(
        "RegSection",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=NAVY,
        spaceAfter=5,
    )
    header_style = ParagraphStyle(
        "RegHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.3,
        leading=7,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "RegCell",
        parent=styles["Normal"],
        fontSize=6.5,
        leading=7.5,
        textColor=INK,
    )
    center_style = ParagraphStyle("RegCenter", parent=cell_style, alignment=TA_CENTER)
    number_style = ParagraphStyle("RegNumber", parent=cell_style, alignment=TA_RIGHT)
    total_style = ParagraphStyle(
        "RegTotal",
        parent=number_style,
        fontName="Helvetica-Bold",
    )

    company_meta = " · ".join(
        part
        for part in (
            org.address_block.replace("\n", ", "),
            org.phone,
            org.email,
        )
        if part
    )
    brand_items: list[Any] = []
    if org.logo:
        try:
            logo = Image(org.logo.path)
            logo._restrictSize(2.6 * cm, 1.2 * cm)
            brand_items.append(logo)
        except (OSError, ValueError):
            pass
    brand_copy = Table(
        [
            [_paragraph(org.display_name, company_style)],
            [_paragraph(company_meta, meta_style)],
        ],
        colWidths=[16.7 * cm],
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
    brand_items.append(brand_copy)
    brand = Table(
        [brand_items],
        colWidths=[3 * cm, 16.7 * cm] if len(brand_items) == 2 else [19.7 * cm],
    )
    brand.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    report_copy = Table(
        [
            [_paragraph("MONTHLY PAYROLL REGISTER", title_style)],
            [
                _paragraph(
                    f"{period_label}  |  {currency or '—'}  |  {status_label or '—'}",
                    ParagraphStyle(
                        "RegPeriod",
                        parent=meta_style,
                        alignment=TA_RIGHT,
                    ),
                )
            ],
        ],
        colWidths=[19.5 * cm],
    )
    report_copy.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    heading = Table([[brand, report_copy]], colWidths=[19.7 * cm, 19.5 * cm])
    heading.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 1.3, TEAL),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    def money(value: Any) -> str:
        return f"{_number(value):,.2f}"

    def make_table(
        table_headers: Sequence[str],
        table_rows: Sequence[Sequence[Any]],
        widths: Sequence[float],
        money_indexes: set[int],
        total_indexes: set[int],
    ) -> LongTable:
        data: list[list[Any]] = [
            [_paragraph(header, header_style) for header in table_headers]
        ]
        totals = [Decimal("0") for _ in table_headers]
        for raw in table_rows:
            rendered = []
            for col, value in enumerate(raw):
                if col in total_indexes:
                    totals[col] += _number(value)
                style = number_style if col in money_indexes or col in total_indexes else cell_style
                if col == 0:
                    style = center_style
                text = money(value) if col in money_indexes else str(value if value is not None else "")
                rendered.append(_paragraph(text, style))
            data.append(rendered)
        total_row = []
        for col in range(len(table_headers)):
            if col == 1:
                total_row.append(_paragraph("TOTAL", total_style))
            elif col in total_indexes:
                text = money(totals[col]) if col in money_indexes else f"{totals[col]:g}"
                total_row.append(_paragraph(text, total_style))
            else:
                total_row.append("")
        data.append(total_row)
        last = len(data) - 1
        table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("TOPPADDING", (0, 1), (-1, -2), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -2), 3),
            ("BACKGROUND", (0, last), (-1, last), TOTAL_BG),
            ("LINEABOVE", (0, last), (-1, last), 1.1, TEAL),
            ("TOPPADDING", (0, last), (-1, last), 4),
            ("BOTTOMPADDING", (0, last), (-1, last), 4),
        ]
        for row_index in range(2, last, 2):
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), ROW_ALT))
        table.setStyle(TableStyle(commands))
        return table

    story: list[Any] = [heading, Spacer(1, 0.2 * cm)]
    if not rows:
        story.append(_paragraph("No payslips are available for this period.", cell_style))
    else:
        # Overview keeps the operational numbers readable on a single page.
        summary_indexes = [0, 1, 2, 5, 9, 10, 11, 12, len(headers) - 3, len(headers) - 2, len(headers) - 1]
        summary_headers = [headers[i] for i in summary_indexes]
        summary_rows = [[row[i] for i in summary_indexes] for row in rows]
        summary_widths = [
            2.2 * cm,
            6.5 * cm,
            4.0 * cm,
            4.0 * cm,
            1.8 * cm,
            1.8 * cm,
            1.8 * cm,
            2.7 * cm,
            3.0 * cm,
            3.0 * cm,
            3.0 * cm,
        ]

        gross_total = sum((_number(row[-3]) for row in rows), Decimal("0"))
        ded_total = sum((_number(row[-2]) for row in rows), Decimal("0"))
        net_total = sum((_number(row[-1]) for row in rows), Decimal("0"))
        ot_total = sum((_number(row[12]) for row in rows), Decimal("0"))
        kpi_data = [
            [
                _paragraph("PAYSLIPS", meta_style),
                _paragraph("OT PAY", meta_style),
                _paragraph("GROSS", meta_style),
                _paragraph("DEDUCTIONS", meta_style),
                _paragraph("NET PAY", meta_style),
            ],
            [
                _paragraph(str(len(rows)), company_style),
                _paragraph(money(ot_total), company_style),
                _paragraph(money(gross_total), company_style),
                _paragraph(money(ded_total), company_style),
                _paragraph(money(net_total), company_style),
            ],
        ]
        kpis = Table(kpi_data, colWidths=[7.84 * cm] * 5)
        kpis.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), TEAL_SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, 0), 5),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                ]
            )
        )
        story.extend(
            [
                kpis,
                Spacer(1, 0.25 * cm),
                _paragraph("Employee payroll summary", section_style),
                make_table(
                    summary_headers,
                    summary_rows,
                    summary_widths,
                    {7, 8, 9, 10},
                    {4, 5, 6, 7, 8, 9, 10},
                ),
            ]
        )

        def add_component_sections(codes: Sequence[str], label: str):
            valid_codes = [code for code in codes if code in headers]
            for offset in range(0, len(valid_codes), 8):
                chunk = valid_codes[offset : offset + 8]
                indexes = [0, 1, 2] + [headers.index(code) for code in chunk]
                part_rows = [[row[i] for i in indexes] for row in rows]
                suffix = (
                    f" ({offset // 8 + 1})"
                    if len(valid_codes) > 8
                    else ""
                )
                story.extend(
                    [
                        PageBreak(),
                        _paragraph(f"{label}{suffix} · {period_label}", section_style),
                        make_table(
                            [headers[i] for i in indexes],
                            part_rows,
                            [2.1 * cm, 5.2 * cm, 3.5 * cm]
                            + [3.2 * cm] * len(chunk),
                            set(range(3, 3 + len(chunk))),
                            set(range(3, 3 + len(chunk))),
                        ),
                    ]
                )

        add_component_sections(earning_codes, "Earnings breakdown")
        add_component_sections(deduction_codes, "Deductions breakdown")

    def draw_page(canvas, pdf_doc):
        canvas.saveState()
        width, _ = landscape(A3)
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(0.7)
        canvas.line(1.15 * cm, 0.7 * cm, width - 1.15 * cm, 0.7 * cm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(1.15 * cm, 0.4 * cm, f"{org.display_name} · {period_label}")
        canvas.drawRightString(width - 1.15 * cm, 0.4 * cm, f"Page {pdf_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()
