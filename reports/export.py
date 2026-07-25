"""Excel / PDF exporters for ReportDocument."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from reports.document import ReportDocument, ReportSheet
from reports.excel import (
    add_sheet,
    new_workbook,
    workbook_response,
    write_table,
)
from setup.models import OrganizationSettings


def export_response(doc: ReportDocument, fmt: str = "xlsx") -> HttpResponse:
    fmt = (fmt or "xlsx").lower().strip()
    if fmt in ("pdf", "application/pdf"):
        return pdf_response(doc)
    return excel_response(doc)


def excel_response(doc: ReportDocument) -> HttpResponse:
    wb, ws, start = new_workbook(title=doc.title, subtitle=doc.subtitle)
    first = True
    for sheet in doc.sheets:
        if first:
            target = ws
            target.title = sheet.name[:31] or "Report"
            write_table(
                target,
                start_row=start,
                headers=sheet.headers,
                rows=sheet.rows,
                money_cols=sheet.money_cols,
            )
            first = False
        else:
            target = add_sheet(wb, sheet.name)
            write_table(
                target,
                start_row=1,
                headers=sheet.headers,
                rows=sheet.rows,
                money_cols=sheet.money_cols,
            )
    return workbook_response(wb, doc.filename)


def _fmt_cell(value: Any, *, money: bool = False) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return f"{value:,.2f}" if money else f"{value:g}"
    if isinstance(value, float):
        return f"{value:,.2f}" if money else str(value)
    if isinstance(value, int) and money:
        return f"{value:,.2f}"
    if isinstance(value, datetime):
        dt = timezone.localtime(value) if timezone.is_aware(value) else value
        return dt.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    # Keep cells short so xhtml2pdf can size columns
    if len(text) > 48:
        return text[:45] + "…"
    return text


def _display_rows(sheet: ReportSheet, col_indexes: list[int] | None = None) -> list[list[str]]:
    money = set(sheet.money_cols or ())
    indexes = col_indexes or list(range(1, len(sheet.headers) + 1))
    display_rows = []
    for row in sheet.rows:
        cells = []
        for i in indexes:
            raw = row[i - 1] if i - 1 < len(row) else ""
            cells.append(_fmt_cell(raw, money=i in money))
        display_rows.append(cells)
    return display_rows


def _chunk_sheet_for_pdf(sheet: ReportSheet, *, max_cols: int = 8) -> list[dict]:
    """
    xhtml2pdf struggles with very wide tables. Keep identity columns and
    split the rest into landscape-friendly chunks.
    """
    headers = list(sheet.headers)
    n = len(headers)
    if n == 0:
        return [
            {
                "name": sheet.name,
                "headers": [],
                "rows": [],
                "col_count": 0,
                "wide": False,
            }
        ]

    # Prefer keeping employee code + name when present
    key_cols = 2 if n >= 2 else 1
    if n <= max_cols:
        return [
            {
                "name": sheet.name,
                "headers": headers,
                "rows": _display_rows(sheet),
                "col_count": n,
                "wide": n > 8,
            }
        ]

    chunks = []
    rest = list(range(key_cols, n))
    chunk_size = max(1, max_cols - key_cols)
    part = 1
    for offset in range(0, len(rest), chunk_size):
        idxs_0 = list(range(key_cols)) + rest[offset : offset + chunk_size]
        idxs_1 = [i + 1 for i in idxs_0]  # 1-based for money_cols / _display_rows
        label = sheet.name if part == 1 and offset + chunk_size >= len(rest) else f"{sheet.name} ({part})"
        chunks.append(
            {
                "name": label,
                "headers": [headers[i] for i in idxs_0],
                "rows": _display_rows(sheet, idxs_1),
                "col_count": len(idxs_0),
                "wide": True,
            }
        )
        part += 1
    return chunks


def render_report_html(doc: ReportDocument) -> str:
    org = OrganizationSettings.load()
    sheets: list[dict] = []
    for s in doc.sheets:
        sheets.extend(_chunk_sheet_for_pdf(s))
    landscape = any(s["wide"] or s["col_count"] > 6 for s in sheets)
    return render_to_string(
        "reports/report_pdf.html",
        {
            "company": org,
            "title": doc.title,
            "subtitle": doc.subtitle,
            "sheets": sheets,
            "landscape": landscape,
            "generated_at": timezone.localtime(),
            "row_count": sum(len(s.rows) for s in doc.sheets),
        },
    )


def _html_to_pdf(html: str) -> bytes:
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:
        raise RuntimeError(
            "PDF library missing. Install with: pip install xhtml2pdf pillow"
        ) from exc

    buffer = BytesIO()
    try:
        result = pisa.CreatePDF(html, dest=buffer, link_callback=_link_callback)
    except ValueError as exc:
        raise RuntimeError(
            "This report is too wide for PDF. Download Excel instead, or narrow the filters."
        ) from exc
    if result.err:
        raise RuntimeError("Could not generate PDF from report template.")
    return buffer.getvalue()


def _link_callback(uri, rel):
    if uri.startswith(settings.MEDIA_URL):
        path = Path(settings.MEDIA_ROOT) / uri[len(settings.MEDIA_URL) :]
        return str(path)
    if uri.startswith(settings.STATIC_URL):
        name = uri[len(settings.STATIC_URL) :]
        for d in getattr(settings, "STATICFILES_DIRS", []) or []:
            candidate = Path(d) / name
            if candidate.exists():
                return str(candidate)
        return str(Path(settings.STATIC_ROOT) / name)
    return uri


def pdf_response(doc: ReportDocument) -> HttpResponse:
    pdf_bytes = _html_to_pdf(render_report_html(doc))
    filename = doc.filename
    if filename.endswith(".xlsx"):
        filename = filename[: -len(".xlsx")]
    if not filename.endswith(".pdf"):
        filename = f"{filename}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
