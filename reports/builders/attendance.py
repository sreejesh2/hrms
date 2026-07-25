"""Attendance MIS report builders."""

from __future__ import annotations

import calendar
from collections import defaultdict
from decimal import Decimal

from attendance.models import DailyAttendance
from people.models import Employee
from reports.builders.payroll import EMP_HEADERS, _emp_cols
from reports.document import ReportDocument, ReportSheet

STATUS_SHORT = {
    DailyAttendance.Status.PRESENT: "P",
    DailyAttendance.Status.ABSENT: "A",
    DailyAttendance.Status.HALF_DAY: "HD",
    DailyAttendance.Status.WEEKLY_OFF: "WO",
    DailyAttendance.Status.HOLIDAY: "H",
    DailyAttendance.Status.ON_LEAVE: "L",
    DailyAttendance.Status.MISSING_PUNCH: "MP",
}


def _employee_qs(department=None):
    qs = Employee.objects.select_related(
        "department", "division", "location", "position"
    ).order_by("employee_code")
    if department:
        qs = qs.filter(department=department)
    return qs.filter(
        status__in=[
            Employee.Status.ACTIVE,
            Employee.Status.ON_LEAVE,
        ]
    )


def build_attendance_month(form) -> ReportDocument:
    year = form.cleaned_data["year"]
    month = form.cleaned_data["month"]
    dept = form.cleaned_data.get("department")
    start, end = form.month_bounds
    days_in_month = calendar.monthrange(year, month)[1]
    day_nums = list(range(1, days_in_month + 1))

    employees = list(_employee_qs(dept))
    emp_ids = [e.pk for e in employees]
    records = DailyAttendance.objects.filter(
        employee_id__in=emp_ids,
        date__gte=start,
        date__lte=end,
    )

    by_emp: dict[int, dict] = defaultdict(dict)
    for rec in records:
        by_emp[rec.employee_id][rec.date.day] = rec

    headers = [
        *EMP_HEADERS,
        *[str(d) for d in day_nums],
        "Present",
        "Absent",
        "Half day",
        "Leave",
        "Weekly off",
        "Holiday",
        "Missing punch",
        "OT hours",
        "Late mins",
    ]
    rows = []
    for emp in employees:
        day_map = by_emp.get(emp.pk, {})
        counts = defaultdict(int)
        ot_total = Decimal("0.00")
        late_total = 0
        day_cells = []
        for d in day_nums:
            rec = day_map.get(d)
            if not rec:
                day_cells.append("")
                continue
            day_cells.append(STATUS_SHORT.get(rec.status, rec.status))
            counts[rec.status] += 1
            ot_total += rec.overtime_hours or Decimal("0")
            late_total += rec.late_minutes or 0
        rows.append(
            [
                *_emp_cols(emp),
                *day_cells,
                counts[DailyAttendance.Status.PRESENT],
                counts[DailyAttendance.Status.ABSENT],
                counts[DailyAttendance.Status.HALF_DAY],
                counts[DailyAttendance.Status.ON_LEAVE],
                counts[DailyAttendance.Status.WEEKLY_OFF],
                counts[DailyAttendance.Status.HOLIDAY],
                counts[DailyAttendance.Status.MISSING_PUNCH],
                ot_total,
                late_total,
            ]
        )

    legend_rows = [
        ["P", "Present"],
        ["A", "Absent"],
        ["HD", "Half day"],
        ["L", "On leave"],
        ["WO", "Weekly off"],
        ["H", "Holiday"],
        ["MP", "Missing punch"],
    ]
    return ReportDocument(
        title="Attendance monthly register",
        subtitle=f"{calendar.month_name[month]} {year}",
        filename=f"attendance_month_{year}_{month:02d}",
        sheets=[
            ReportSheet("Register", headers, rows),
            ReportSheet("Legend", ["Code", "Meaning"], legend_rows),
        ],
    )


def build_attendance_detail(form) -> ReportDocument:
    d0 = form.cleaned_data["date_from"]
    d1 = form.cleaned_data["date_to"]
    dept = form.cleaned_data.get("department")
    qs = (
        DailyAttendance.objects.filter(date__gte=d0, date__lte=d1)
        .select_related(
            "employee__department",
            "employee__division",
            "employee__location",
            "employee__position",
            "shift",
        )
        .order_by("date", "employee__employee_code")
    )
    if dept:
        qs = qs.filter(employee__department=dept)

    rows = [
        [
            rec.date,
            *_emp_cols(rec.employee),
            rec.get_status_display(),
            rec.shift.name if rec.shift_id else "",
            rec.worked_hours,
            rec.expected_hours,
            rec.overtime_hours,
            rec.ot_rate,
            rec.late_minutes,
            rec.early_leave_minutes,
            rec.punch_count,
            rec.first_punch_at,
            rec.last_punch_at,
            "Yes" if rec.is_locked else "No",
        ]
        for rec in qs
    ]
    return ReportDocument(
        title="Daily attendance detail",
        subtitle=f"{d0.isoformat()} → {d1.isoformat()}",
        filename=f"attendance_detail_{d0}_{d1}",
        sheets=[
            ReportSheet(
                "Detail",
                [
                    "Date",
                    *EMP_HEADERS,
                    "Status",
                    "Shift",
                    "Worked hrs",
                    "Expected hrs",
                    "OT hrs",
                    "OT rate",
                    "Late mins",
                    "Early leave mins",
                    "Punches",
                    "First punch",
                    "Last punch",
                    "Locked",
                ],
                rows,
            )
        ],
    )


def build_overtime(form) -> ReportDocument:
    d0 = form.cleaned_data["date_from"]
    d1 = form.cleaned_data["date_to"]
    dept = form.cleaned_data.get("department")
    qs = (
        DailyAttendance.objects.filter(
            date__gte=d0,
            date__lte=d1,
            overtime_hours__gt=0,
        )
        .select_related(
            "employee__department",
            "employee__division",
            "employee__location",
            "employee__position",
            "ot_policy",
            "holiday",
        )
        .order_by("date", "employee__employee_code")
    )
    if dept:
        qs = qs.filter(employee__department=dept)

    rows = []
    for rec in qs:
        context = "Weekday"
        if rec.status == DailyAttendance.Status.HOLIDAY or rec.holiday_id:
            context = "Holiday"
        elif rec.status == DailyAttendance.Status.WEEKLY_OFF:
            context = "Weekly off"
        rows.append(
            [
                rec.date,
                *_emp_cols(rec.employee),
                rec.get_status_display(),
                context,
                rec.overtime_hours,
                rec.ot_rate,
                rec.ot_policy.name if rec.ot_policy_id else "",
                rec.worked_hours,
                rec.expected_hours,
            ]
        )
    return ReportDocument(
        title="Overtime MIS",
        subtitle=f"{d0.isoformat()} → {d1.isoformat()}",
        filename=f"overtime_mis_{d0}_{d1}",
        sheets=[
            ReportSheet(
                "Overtime",
                [
                    "Date",
                    *EMP_HEADERS,
                    "Status",
                    "OT context",
                    "OT hours",
                    "OT rate",
                    "OT policy",
                    "Worked hrs",
                    "Expected hrs",
                ],
                rows,
            )
        ],
    )
