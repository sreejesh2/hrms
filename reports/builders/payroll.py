"""Payroll MIS report builders."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch

from payroll.models import Payslip, PayslipLine, SalaryStructure
from people.models import Employee
from reports.document import ReportDocument, ReportSheet


def _master_label(obj) -> str:
    if obj is None:
        return ""
    return getattr(obj, "description", None) or str(obj)


def _emp_cols(emp: Employee) -> list:
    return [
        emp.employee_code,
        emp.full_name,
        _master_label(emp.department) if emp.department_id else "",
        _master_label(emp.division) if emp.division_id else "",
        _master_label(emp.location) if emp.location_id else "",
        _master_label(emp.position) if emp.position_id else "",
    ]


EMP_HEADERS = ["Employee code", "Employee", "Department", "Division", "Location", "Position"]


def build_payroll_register(form) -> ReportDocument:
    period = form.cleaned_data["period"]
    slips = (
        Payslip.objects.filter(period=period)
        .select_related(
            "employee__department",
            "employee__division",
            "employee__location",
            "employee__position",
        )
        .prefetch_related(
            Prefetch("lines", queryset=PayslipLine.objects.order_by("sort_order", "code"))
        )
        .order_by("employee__employee_code")
    )

    earn_codes: list[str] = []
    ded_codes: list[str] = []
    seen_e, seen_d = set(), set()
    for slip in slips:
        for line in slip.lines.all():
            if line.kind == PayslipLine.Kind.EARNING and line.code not in seen_e:
                seen_e.add(line.code)
                earn_codes.append(line.code)
            elif line.kind == PayslipLine.Kind.DEDUCTION and line.code not in seen_d:
                seen_d.add(line.code)
                ded_codes.append(line.code)

    headers = [
        *EMP_HEADERS,
        "Status",
        "Currency",
        "Calendar days",
        "Paid days",
        "Unpaid days",
        "OT hours",
        "OT amount",
        *earn_codes,
        *ded_codes,
        "Earnings total",
        "Deductions total",
        "Net pay",
    ]

    rows = []
    detail_rows = []
    for slip in slips:
        by_code = {ln.code: ln.amount for ln in slip.lines.all()}
        rows.append(
            [
                *_emp_cols(slip.employee),
                slip.get_status_display(),
                slip.currency,
                slip.calendar_days,
                slip.paid_days,
                slip.unpaid_days,
                slip.ot_hours,
                slip.ot_amount,
                *[by_code.get(c, Decimal("0.00")) for c in earn_codes],
                *[by_code.get(c, Decimal("0.00")) for c in ded_codes],
                slip.earnings_total,
                slip.deductions_total,
                slip.net_pay,
            ]
        )
        for ln in slip.lines.all():
            detail_rows.append(
                [
                    *_emp_cols(slip.employee),
                    ln.code,
                    ln.name,
                    ln.get_kind_display(),
                    ln.amount,
                ]
            )

    start_money = len(EMP_HEADERS) + 7
    money_cols = list(range(start_money, len(headers) + 1))
    return ReportDocument(
        title="Monthly payroll register",
        subtitle=f"Period: {period.label} · Status: {period.get_status_display()}",
        filename=f"payroll_register_{period.year}_{period.month:02d}",
        sheets=[
            ReportSheet("Register", headers, rows, money_cols),
            ReportSheet(
                "Line detail",
                [*EMP_HEADERS, "Code", "Name", "Kind", "Amount"],
                detail_rows,
                [len(EMP_HEADERS) + 4],
            ),
        ],
        pdf_context={
            "pdf_engine": "reportlab_payroll_register",
            "period_label": period.label,
            "currency": period.currency,
            "status_label": period.get_status_display(),
            "earning_codes": earn_codes,
            "deduction_codes": ded_codes,
        },
    )


def build_payslip_lines(form) -> ReportDocument:
    period = form.cleaned_data["period"]
    lines = (
        PayslipLine.objects.filter(payslip__period=period)
        .select_related(
            "payslip__employee__department",
            "payslip__employee__division",
            "payslip__employee__location",
            "payslip__employee__position",
            "payslip",
        )
        .order_by("payslip__employee__employee_code", "sort_order", "code")
    )
    rows = [
        [
            *_emp_cols(ln.payslip.employee),
            ln.payslip.get_status_display(),
            ln.payslip.currency,
            ln.code,
            ln.name,
            ln.get_kind_display(),
            ln.amount,
        ]
        for ln in lines
    ]
    return ReportDocument(
        title="Payslip line extract",
        subtitle=f"Period: {period.label}",
        filename=f"payslip_lines_{period.year}_{period.month:02d}",
        sheets=[
            ReportSheet(
                "Lines",
                [*EMP_HEADERS, "Payslip status", "Currency", "Code", "Name", "Kind", "Amount"],
                rows,
                [len(EMP_HEADERS) + 6],
            )
        ],
    )


def build_bank_payment(form) -> ReportDocument:
    period = form.cleaned_data["period"]
    slips = (
        Payslip.objects.filter(period=period)
        .select_related(
            "employee__department",
            "employee__division",
            "employee__location",
            "employee__position",
            "employee__bank",
        )
        .order_by("employee__employee_code")
    )
    rows = [
        [
            *_emp_cols(s.employee),
            s.employee.bank.description if s.employee.bank_id else "",
            s.currency,
            s.net_pay,
            s.get_status_display(),
        ]
        for s in slips
    ]
    return ReportDocument(
        title="Bank payment list",
        subtitle=f"Period: {period.label} · Note: IBAN/account not stored — add via custom fields if needed",
        filename=f"bank_payment_{period.year}_{period.month:02d}",
        sheets=[
            ReportSheet(
                "Payments",
                [*EMP_HEADERS, "Bank", "Currency", "Net pay", "Status"],
                rows,
                [len(EMP_HEADERS) + 3],
            )
        ],
    )


def build_statutory_summary(form) -> ReportDocument:
    period = form.cleaned_data["period"]
    lines = (
        PayslipLine.objects.filter(
            payslip__period=period,
            kind=PayslipLine.Kind.DEDUCTION,
        )
        .select_related(
            "payslip__employee__department",
            "payslip__employee__division",
            "payslip__employee__location",
            "payslip__employee__position",
        )
        .order_by("code", "payslip__employee__employee_code")
    )

    by_code: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    detail = []
    for ln in lines:
        by_code[ln.code] += ln.amount
        detail.append(
            [
                *_emp_cols(ln.payslip.employee),
                ln.code,
                ln.name,
                ln.amount,
            ]
        )

    return ReportDocument(
        title="Statutory & deduction summary",
        subtitle=f"Period: {period.label}",
        filename=f"statutory_summary_{period.year}_{period.month:02d}",
        sheets=[
            ReportSheet(
                "Summary",
                ["Deduction code", "Total amount"],
                [[code, total] for code, total in sorted(by_code.items())],
                [2],
            ),
            ReportSheet(
                "By employee",
                [*EMP_HEADERS, "Code", "Name", "Amount"],
                detail,
                [len(EMP_HEADERS) + 3],
            ),
        ],
    )


def build_company_salary_sheet(form) -> ReportDocument:
    """
    Company salary sheet columns matching the printed sample PDF:
    Sl.No, EMP-Code, Name, W-Days, Basic, Cost of Living, OT Hours, OT Amt,
    Total Salary, Food Allow, HRA, Extra OT Amt, Extra Allow Amt, Gross,
    Other Deduction, Net, Bank.
    """
    period = form.cleaned_data["period"]
    slips = (
        Payslip.objects.filter(period=period)
        .select_related("employee__bank")
        .prefetch_related(
            Prefetch("lines", queryset=PayslipLine.objects.order_by("sort_order", "code"))
        )
        .order_by("employee__employee_code")
    )

    headers = [
        "Sl.No",
        "EMP-Code",
        "Name",
        "W-Days",
        "Basic",
        "Cost of Living",
        "OT Hours",
        "OT Amt",
        "Total Salary",
        "Food Allow",
        "HRA",
        "Extra OT Amt",
        "Extra Allow Amt",
        "Gross",
        "Other Deduction",
        "Net",
        "Bank",
    ]

    money_cols = [5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16]  # Basic .. Net (skip OT Hours)

    rows = []
    for idx, slip in enumerate(slips, start=1):
        by_code = {ln.code: ln.amount for ln in slip.lines.all()}
        basic = by_code.get("BASIC", Decimal("0.00"))
        col = by_code.get("COL", Decimal("0.00"))
        food = by_code.get("FOOD", Decimal("0.00"))
        hra = by_code.get("HRA", Decimal("0.00"))
        extra_allow = by_code.get("EXTRA_ALLOW", Decimal("0.00"))
        ot_amt = Decimal(slip.ot_amount or 0)
        special_ot = Decimal(slip.special_ot_amount or 0)
        if special_ot == 0:
            special_ot = by_code.get("SPECIAL_OT", Decimal("0.00"))
        total_salary = Decimal(slip.total_salary or 0)
        if total_salary == 0:
            total_salary = (basic + col + ot_amt).quantize(Decimal("0.01"))
        # Other Deduction = all deduction lines (advances, statutory, OTHER_DED, …)
        other_ded = Decimal(slip.deductions_total or 0)
        bank = ""
        if slip.employee.bank_id:
            bank = getattr(slip.employee.bank, "description", None) or str(
                slip.employee.bank
            )
        rows.append(
            [
                idx,
                slip.employee.employee_code,
                slip.employee.full_name,
                slip.paid_days,
                basic,
                col,
                slip.ot_hours,
                ot_amt,
                total_salary,
                food,
                hra,
                special_ot,
                extra_allow,
                slip.earnings_total,
                other_ded,
                slip.net_pay,
                bank,
            ]
        )

    return ReportDocument(
        title="Company salary sheet",
        subtitle=f"Period: {period.label} · Status: {period.get_status_display()}",
        filename=f"company_salary_sheet_{period.year}_{period.month:02d}",
        sheets=[
            ReportSheet("Salary sheet", headers, rows, money_cols),
        ],
        pdf_context={
            "pdf_engine": "reportlab_salary_sheet",
            "period_label": period.label,
            "currency": period.currency,
            "status_label": period.get_status_display(),
        },
    )


def build_salary_structures(form) -> ReportDocument:
    dept = form.cleaned_data.get("department")
    status = form.cleaned_data.get("status") or ""
    qs = (
        SalaryStructure.objects.filter(effective_to__isnull=True)
        .select_related(
            "employee__department",
            "employee__division",
            "employee__location",
            "employee__position",
        )
        .prefetch_related("lines__component")
        .order_by("employee__employee_code")
    )
    if dept:
        qs = qs.filter(employee__department=dept)
    if status:
        qs = qs.filter(employee__status=status)

    header_rows = []
    line_rows = []
    for st in qs:
        emp = st.employee
        header_rows.append(
            [
                *_emp_cols(emp),
                emp.get_status_display(),
                st.currency,
                st.effective_from,
                st.basic_amount(),
                st.earnings_total(),
            ]
        )
        for ln in st.lines.all():
            line_rows.append(
                [
                    *_emp_cols(emp),
                    ln.component.code if ln.component_id else "",
                    ln.component.name if ln.component_id else "",
                    ln.amount,
                    ln.percent,
                ]
            )

    return ReportDocument(
        title="Salary structure snapshot",
        subtitle="Open (current) structures only",
        filename="salary_structures",
        sheets=[
            ReportSheet(
                "Structures",
                [
                    *EMP_HEADERS,
                    "Status",
                    "Currency",
                    "Effective from",
                    "Basic",
                    "Earnings total",
                ],
                header_rows,
                [len(EMP_HEADERS) + 4, len(EMP_HEADERS) + 5],
            ),
            ReportSheet(
                "Lines",
                [*EMP_HEADERS, "Component code", "Component", "Amount", "Percent"],
                line_rows,
                [len(EMP_HEADERS) + 3],
            ),
        ],
    )
