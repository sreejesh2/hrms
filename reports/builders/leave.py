"""Leave MIS report builders."""

from __future__ import annotations

from leave.models import LeaveBalance, LeaveRequest
from reports.builders.payroll import EMP_HEADERS, _emp_cols
from reports.document import ReportDocument, ReportSheet


def build_leave_balances(form) -> ReportDocument:
    year = form.cleaned_data["year"]
    dept = form.cleaned_data.get("department")
    qs = (
        LeaveBalance.objects.filter(year=year)
        .select_related(
            "employee__department",
            "employee__division",
            "employee__location",
            "employee__position",
            "leave_type",
        )
        .order_by("employee__employee_code", "leave_type__code")
    )
    if dept:
        qs = qs.filter(employee__department=dept)

    rows = [
        [
            *_emp_cols(b.employee),
            b.leave_type.code,
            b.leave_type.name,
            "Yes" if b.leave_type.is_paid else "No",
            b.entitled,
            b.used,
            b.pending,
            b.available,
        ]
        for b in qs
    ]
    return ReportDocument(
        title="Leave balance statement",
        subtitle=f"Year {year}",
        filename=f"leave_balances_{year}",
        sheets=[
            ReportSheet(
                "Balances",
                [
                    *EMP_HEADERS,
                    "Type code",
                    "Leave type",
                    "Paid",
                    "Entitled",
                    "Used",
                    "Pending",
                    "Available",
                ],
                rows,
            )
        ],
    )


def build_leave_utilization(form) -> ReportDocument:
    d0 = form.cleaned_data["date_from"]
    d1 = form.cleaned_data["date_to"]
    dept = form.cleaned_data.get("department")
    qs = (
        LeaveRequest.objects.filter(
            status=LeaveRequest.Status.APPROVED,
            start_date__lte=d1,
            end_date__gte=d0,
        )
        .select_related(
            "employee__department",
            "employee__division",
            "employee__location",
            "employee__position",
            "leave_type",
            "reviewed_by",
        )
        .order_by("start_date", "employee__employee_code")
    )
    if dept:
        qs = qs.filter(employee__department=dept)

    rows = [
        [
            *_emp_cols(req.employee),
            req.leave_type.code,
            req.leave_type.name,
            "Yes" if req.leave_type.is_paid else "No",
            req.start_date,
            req.end_date,
            req.days,
            "Yes" if req.is_half_day else "No",
            req.get_status_display(),
            (req.reviewed_by.email if req.reviewed_by_id else ""),
            req.reviewed_at,
        ]
        for req in qs
    ]
    return ReportDocument(
        title="Leave utilization",
        subtitle=f"Approved leave overlapping {d0.isoformat()} → {d1.isoformat()}",
        filename=f"leave_utilization_{d0}_{d1}",
        sheets=[
            ReportSheet(
                "Utilization",
                [
                    *EMP_HEADERS,
                    "Type code",
                    "Leave type",
                    "Paid",
                    "Start",
                    "End",
                    "Days",
                    "Half day",
                    "Status",
                    "Reviewed by",
                    "Reviewed at",
                ],
                rows,
            )
        ],
    )
