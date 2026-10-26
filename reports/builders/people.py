"""People / headcount / gratuity MIS builders."""

from __future__ import annotations

from people.models import Employee
from payroll.gratuity import estimate_gratuity
from reports.builders.payroll import EMP_HEADERS, _emp_cols, _master_label
from reports.document import ReportDocument, ReportSheet


def build_headcount(form) -> ReportDocument:
    dept = form.cleaned_data.get("department")
    status = form.cleaned_data.get("status") or ""
    qs = Employee.objects.select_related(
        "department",
        "division",
        "location",
        "position",
        "bank",
        "manager",
    ).order_by("employee_code")
    if dept:
        qs = qs.filter(department=dept)
    if status:
        qs = qs.filter(status=status)

    rows = [
        [
            emp.employee_code,
            emp.full_name,
            emp.first_name,
            emp.last_name,
            emp.email,
            emp.phone_display,
            emp.get_status_display(),
            emp.date_of_joining,
            _master_label(emp.department) if emp.department_id else "",
            _master_label(emp.division) if emp.division_id else "",
            _master_label(emp.location) if emp.location_id else "",
            _master_label(emp.position) if emp.position_id else "",
            _master_label(emp.bank) if emp.bank_id else "",
            emp.manager.employee_code if emp.manager_id else "",
            emp.manager.full_name if emp.manager_id else "",
            emp.biometric_id,
        ]
        for emp in qs
    ]
    return ReportDocument(
        title="Employee master / headcount",
        subtitle="",
        filename="headcount",
        sheets=[
            ReportSheet(
                "Employees",
                [
                    "Employee code",
                    "Full name",
                    "First name",
                    "Last name",
                    "Email",
                    "Phone",
                    "Status",
                    "Date of joining",
                    "Department",
                    "Division",
                    "Location",
                    "Position",
                    "Bank",
                    "Manager code",
                    "Manager name",
                    "Biometric ID",
                ],
                rows,
            )
        ],
    )


def build_gratuity(form) -> ReportDocument:
    as_of = form.cleaned_data["as_of"]
    dept = form.cleaned_data.get("department")
    status = form.cleaned_data.get("status") or Employee.Status.ACTIVE
    qs = Employee.objects.select_related(
        "department", "division", "location", "position"
    ).order_by("employee_code")
    if dept:
        qs = qs.filter(department=dept)
    if status:
        qs = qs.filter(status=status)

    from payroll.services import structures_on

    employees = list(qs)
    structures = structures_on([e.pk for e in employees], as_of)
    rows = []
    for emp in employees:
        est = estimate_gratuity(emp, as_of=as_of, structure=structures.get(emp.pk))
        rows.append(
            [
                *_emp_cols(emp),
                emp.date_of_joining,
                as_of,
                float(est.years_of_service),
                est.basic_monthly,
                est.daily_wage,
                est.currency,
                est.amount,
                "Yes" if est.eligible else "No",
                "Yes" if est.capped else "No",
                est.notes,
            ]
        )
    return ReportDocument(
        title="EOS gratuity estimates",
        subtitle=f"As of {as_of.isoformat()} · UAE Art. 51",
        filename=f"gratuity_estimates_{as_of}",
        sheets=[
            ReportSheet(
                "Gratuity",
                [
                    *EMP_HEADERS,
                    "Join date",
                    "As of",
                    "Years of service",
                    "Basic monthly",
                    "Daily wage",
                    "Currency",
                    "Gratuity amount",
                    "Eligible",
                    "Capped",
                    "Notes",
                ],
                rows,
                [len(EMP_HEADERS) + 4, len(EMP_HEADERS) + 5, len(EMP_HEADERS) + 7],
            )
        ],
    )
