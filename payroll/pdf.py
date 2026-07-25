"""Render payslip HTML / PDF from company settings + editable template."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from setup.models import OrganizationSettings

from .currencies import default_currency_code, format_money
from .models import Payslip, PayslipTemplate


def _rows_from_slip(slip: Payslip):
    def fmt(amount):
        return format_money(amount, slip.currency)

    lines = list(slip.lines.all())
    earning_rows = [
        {"code": ln.code, "name": ln.name, "amount_fmt": fmt(ln.amount)}
        for ln in lines
        if ln.kind == "earning" and ln.code != "LWP_INFO"
    ]
    deduction_rows = [
        {"code": ln.code, "name": ln.name, "amount_fmt": fmt(ln.amount)}
        for ln in lines
        if ln.kind == "deduction" and ln.code != "LWP_INFO"
    ]
    info_rows = [{"name": ln.name} for ln in lines if ln.code == "LWP_INFO"]
    totals = {
        "earnings": fmt(slip.earnings_total),
        "deductions": fmt(slip.deductions_total),
        "net": fmt(slip.net_pay),
        "ot": fmt(slip.ot_amount),
    }
    return earning_rows, deduction_rows, info_rows, totals


def payslip_context(slip: Payslip, template: PayslipTemplate | None = None) -> dict:
    company = OrganizationSettings.load()
    layout = template or PayslipTemplate.load_default()
    earning_rows, deduction_rows, info_rows, totals = _rows_from_slip(slip)
    return {
        "company": company,
        "layout": layout,
        "slip": slip,
        "employee": slip.employee,
        "period": slip.period,
        "earning_rows": earning_rows,
        "deduction_rows": deduction_rows,
        "info_rows": info_rows,
        "totals": totals,
        "generated_at": timezone.localtime(),
        "is_sample": False,
    }


def sample_payslip_context(template: PayslipTemplate | None = None) -> dict:
    """Demo payslip using company settings + template (no DB payslip required)."""
    company = OrganizationSettings.load()
    layout = template or PayslipTemplate.load_default()
    currency = company.default_currency or default_currency_code()
    today = timezone.localdate()

    def fmt(amount):
        return format_money(amount, currency)

    basic = Decimal("8000.00")
    hra = Decimal("3200.00")
    special = Decimal("1800.00")
    ot = Decimal("450.00")
    pf = Decimal("960.00")
    earnings = basic + hra + special + ot
    deductions = pf
    net = earnings - deductions

    period = SimpleNamespace(label=f"{today.strftime('%B %Y')} (sample)")
    employee = SimpleNamespace(
        full_name="Sample Employee",
        employee_code="EMP-DEMO",
        department=SimpleNamespace(description="Human Resources"),
        position=SimpleNamespace(description="HR Executive"),
    )
    slip = SimpleNamespace(
        currency=currency,
        paid_days=Decimal("30.00"),
        calendar_days=30,
        unpaid_days=Decimal("0.00"),
        ot_hours=Decimal("6.00"),
        ot_amount=ot,
        earnings_total=earnings,
        deductions_total=deductions,
        net_pay=net,
        get_status_display=lambda: "Sample",
    )

    return {
        "company": company,
        "layout": layout,
        "slip": slip,
        "employee": employee,
        "period": period,
        "earning_rows": [
            {"code": "BASIC", "name": "Basic", "amount_fmt": fmt(basic)},
            {"code": "HRA", "name": "House Rent Allowance", "amount_fmt": fmt(hra)},
            {"code": "SPECIAL", "name": "Special Allowance", "amount_fmt": fmt(special)},
            {"code": "OT", "name": "Overtime", "amount_fmt": fmt(ot)},
        ],
        "deduction_rows": [
            {"code": "PF_EE", "name": "PF Employee", "amount_fmt": fmt(pf)},
        ],
        "info_rows": [],
        "totals": {
            "earnings": fmt(earnings),
            "deductions": fmt(deductions),
            "net": fmt(net),
            "ot": fmt(ot),
        },
        "generated_at": timezone.localtime(),
        "is_sample": True,
    }


def render_payslip_html(slip: Payslip, template: PayslipTemplate | None = None) -> str:
    return render_to_string("payroll/payslip_pdf.html", payslip_context(slip, template))


def render_sample_payslip_html(template: PayslipTemplate | None = None) -> str:
    return render_to_string(
        "payroll/payslip_pdf.html", sample_payslip_context(template)
    )


def _html_to_pdf(html: str) -> bytes:
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:
        raise RuntimeError(
            "PDF library missing. Install with: pip install xhtml2pdf pillow"
        ) from exc

    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=_link_callback)
    if result.err:
        raise RuntimeError("Could not generate PDF from payslip template.")
    return buffer.getvalue()


def render_payslip_pdf(slip: Payslip, template: PayslipTemplate | None = None) -> bytes:
    return _html_to_pdf(render_payslip_html(slip, template))


def render_sample_payslip_pdf(template: PayslipTemplate | None = None) -> bytes:
    return _html_to_pdf(render_sample_payslip_html(template))


def _link_callback(uri, rel):
    """Map /media/… and /static/… to filesystem paths for xhtml2pdf."""
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
