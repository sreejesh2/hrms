from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from django import forms

from reports.forms import (
    AsOfFilterForm,
    DateRangeFilterForm,
    EmployeePeriodFilterForm,
    HeadcountFilterForm,
    MonthFilterForm,
    PeriodFilterForm,
    YearFilterForm,
)


@dataclass(frozen=True)
class ReportSpec:
    slug: str
    title: str
    category: str
    description: str
    form_class: type[forms.Form]
    builder: Callable
    filename_prefix: str


def get_registry() -> list[ReportSpec]:
    # Lazy imports keep app loading light and avoid circular imports.
    from reports.builders import attendance as att
    from reports.builders import leave as lv
    from reports.builders import payroll as pay
    from reports.builders import people as peo

    return [
        ReportSpec(
            slug="payroll-register",
            title="Monthly payroll register",
            category="Payroll",
            description="One row per employee with paid days, OT, earnings, deductions, net, and component columns.",
            form_class=PeriodFilterForm,
            builder=pay.build_payroll_register,
            filename_prefix="payroll_register",
        ),
        ReportSpec(
            slug="company-salary-sheet",
            title="Company salary sheet",
            category="Payroll",
            description=(
                "Printed salary sheet columns: W-Days, Basic, COL, OT, Total Salary, "
                "Food, HRA, Extra OT, Extra Allow, Gross, Other Deduction, Net, Bank."
            ),
            form_class=PeriodFilterForm,
            builder=pay.build_company_salary_sheet,
            filename_prefix="company_salary_sheet",
        ),
        ReportSpec(
            slug="payslip-lines",
            title="Payslip line extract",
            category="Payroll",
            description="Flat extract of every payslip earning and deduction line for a period.",
            form_class=PeriodFilterForm,
            builder=pay.build_payslip_lines,
            filename_prefix="payslip_lines",
        ),
        ReportSpec(
            slug="bank-payment",
            title="Bank payment list",
            category="Payroll",
            description="Net pay by employee with bank for salary transfer prep.",
            form_class=PeriodFilterForm,
            builder=pay.build_bank_payment,
            filename_prefix="bank_payment",
        ),
        ReportSpec(
            slug="statutory-summary",
            title="Statutory & deduction summary",
            category="Payroll",
            description="Deduction lines grouped by code (GPSSA, medical, loan EMI, etc.).",
            form_class=PeriodFilterForm,
            builder=pay.build_statutory_summary,
            filename_prefix="statutory_summary",
        ),
        ReportSpec(
            slug="attendance-month",
            title="Attendance monthly register",
            category="Attendance",
            description="Employee × day status matrix with present/absent/leave/OT/late totals.",
            form_class=MonthFilterForm,
            builder=att.build_attendance_month,
            filename_prefix="attendance_month",
        ),
        ReportSpec(
            slug="attendance-detail",
            title="Daily attendance detail",
            category="Attendance",
            description="One row per employee-day: hours, OT, late, early leave, punches.",
            form_class=DateRangeFilterForm,
            builder=att.build_attendance_detail,
            filename_prefix="attendance_detail",
        ),
        ReportSpec(
            slug="employee-attendance-sheet",
            title="Employee attendance sheet",
            category="Attendance",
            description="Printable per-employee period sheet (Date, punches, hours, OT, deductions, status) — Excel & PDF.",
            form_class=EmployeePeriodFilterForm,
            builder=att.build_employee_attendance_sheet,
            filename_prefix="employee_attendance",
        ),
        ReportSpec(
            slug="overtime",
            title="Overtime MIS",
            category="Attendance",
            description="Days with overtime hours, rate multiplier, and OT context.",
            form_class=DateRangeFilterForm,
            builder=att.build_overtime,
            filename_prefix="overtime_mis",
        ),
        ReportSpec(
            slug="leave-balances",
            title="Leave balance statement",
            category="Leave",
            description="Entitled / used / pending / available by leave type for a year.",
            form_class=YearFilterForm,
            builder=lv.build_leave_balances,
            filename_prefix="leave_balances",
        ),
        ReportSpec(
            slug="leave-utilization",
            title="Leave utilization",
            category="Leave",
            description="Approved leave requests in a date range with days and paid flag.",
            form_class=DateRangeFilterForm,
            builder=lv.build_leave_utilization,
            filename_prefix="leave_utilization",
        ),
        ReportSpec(
            slug="headcount",
            title="Employee master / headcount",
            category="People",
            description="Employee roster with org tree, status, joining date, and manager.",
            form_class=HeadcountFilterForm,
            builder=peo.build_headcount,
            filename_prefix="headcount",
        ),
        ReportSpec(
            slug="gratuity",
            title="EOS gratuity estimates",
            category="People",
            description="UAE Art. 51 end-of-service gratuity estimates as of a chosen date.",
            form_class=AsOfFilterForm,
            builder=peo.build_gratuity,
            filename_prefix="gratuity_estimates",
        ),
        ReportSpec(
            slug="salary-structures",
            title="Salary structure snapshot",
            category="Payroll",
            description="Open salary structures and lines as of today (current packages).",
            form_class=HeadcountFilterForm,
            builder=pay.build_salary_structures,
            filename_prefix="salary_structures",
        ),
    ]


def get_report(slug: str) -> ReportSpec | None:
    for spec in get_registry():
        if spec.slug == slug:
            return spec
    return None


def reports_by_category() -> list[tuple[str, list[ReportSpec]]]:
    grouped: dict[str, list[ReportSpec]] = {}
    order: list[str] = []
    for spec in get_registry():
        if spec.category not in grouped:
            grouped[spec.category] = []
            order.append(spec.category)
        grouped[spec.category].append(spec)
    return [(cat, grouped[cat]) for cat in order]
