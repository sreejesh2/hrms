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
