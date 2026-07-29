"""Attendance MIS report builders."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from attendance.models import DailyAttendance
from people.models import Employee
from reports.builders.payroll import EMP_HEADERS, _emp_cols
from reports.document import ReportDocument, ReportSheet
from setup.models import OrganizationSettings

STATUS_SHORT = {
    DailyAttendance.Status.PRESENT: "P",
    DailyAttendance.Status.ABSENT: "A",
    DailyAttendance.Status.HALF_DAY: "HD",
    DailyAttendance.Status.WEEKLY_OFF: "WO",
    DailyAttendance.Status.HOLIDAY: "H",
    DailyAttendance.Status.ON_LEAVE: "L",
    DailyAttendance.Status.MISSING_PUNCH: "MP",
}

WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ZERO = Decimal("0.00")


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


def _typ_code(rec: DailyAttendance | None, on_date) -> str:
    if rec:
        if rec.status == DailyAttendance.Status.WEEKLY_OFF:
            return "W"
        if rec.status == DailyAttendance.Status.ON_LEAVE and on_date.weekday() == 6:
            return "W"
        if rec.status == DailyAttendance.Status.HOLIDAY:
            return "H"
        return "N"
    # No row yet — Sunday as weekly off heuristic
    return "W" if on_date.weekday() == 6 else "N"


def _punch_time(dt) -> str:
    if not dt:
        return ""
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    return local.strftime("%H:%M")


def _ot_display(hours: Decimal, *, status: str) -> str:
    """e.g. 1.37N — N=normal/weekday, W=weekly off, H=holiday."""
    if not hours or hours <= 0:
        return "0.00"
    suffix = "N"
    if status == DailyAttendance.Status.WEEKLY_OFF:
        suffix = "W"
    elif status == DailyAttendance.Status.HOLIDAY:
        suffix = "H"
    return f"{hours.quantize(Decimal('0.01'))}{suffix}"


def _cot_hours(ot: Decimal, rate: Decimal | None) -> Decimal:
    """
    C.OT = pay-weighted OT hours (OT × rate), matching company sheets
    where Sunday/night 1.25× shows higher C.OT than OT.
    """
    ot = ot or ZERO
    rate = Decimal(rate or 1)
    if ot <= 0:
        return ZERO
    return (ot * rate).quantize(Decimal("0.01"))


def _leave_labels_for_period(employee, start, end) -> dict:
    """Map date → status text like Leave/Annual Leave from approved leave."""
    labels: dict = {}
    try:
        from leave.models import LeaveRequest

        qs = (
            LeaveRequest.objects.filter(
                employee=employee,
                status=LeaveRequest.Status.APPROVED,
                start_date__lte=end,
                end_date__gte=start,
            )
            .select_related("leave_type")
            .order_by("start_date", "id")
        )
        for req in qs:
            name = (
                (req.leave_type.name if req.leave_type_id else "")
                or (req.leave_type.code if req.leave_type_id else "")
                or "Leave"
            )
            # Match company sheet wording: Leave/Annual Leave
            text = f"Leave/{name}"
            if req.is_half_day:
                text = f"Leave/{name} (half)"
            cur = max(req.start_date, start)
            last = min(req.end_date, end)
            while cur <= last:
                labels[cur] = text[:60]
                cur += timedelta(days=1)
    except Exception:
        pass
    return labels


def _status_note(
    rec: DailyAttendance | None,
    *,
    leave_label: str = "",
) -> str:
    if not rec:
        return leave_label or ""
    if leave_label:
        return leave_label
    if rec.notes and "Wrong P" in rec.notes:
        return rec.notes[:60]
    if rec.status == DailyAttendance.Status.MISSING_PUNCH:
        return "Marked Absent, Due to Wrong P."
    if rec.status == DailyAttendance.Status.ABSENT:
        return "Absent/"
    if rec.status == DailyAttendance.Status.HALF_DAY:
        if rec.notes and "Leave" in rec.notes:
            return rec.notes[:60]
        return "Half day"
    if rec.status == DailyAttendance.Status.ON_LEAVE:
        if rec.notes:
            # Engine stores "Leave: EL" — present as Leave/EL
            raw = rec.notes
            if "Leave:" in raw:
                code = raw.split("Leave:")[-1].strip().split("|")[0].strip()
                if code:
                    return f"Leave/{code}"[:60]
            return raw[:60]
        return "On leave"
    if rec.notes:
        return rec.notes[:40]
    return ""


def _ded_hours(rec: DailyAttendance | None) -> Decimal:
    if not rec or not rec.penalty_minutes:
        return ZERO
    return (Decimal(rec.penalty_minutes) / Decimal("60")).quantize(Decimal("0.01"))


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
        ["MP", "Absent (wrong punch)"],
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


def build_employee_attendance_sheet(form) -> ReportDocument:
    """
    Company-style one-employee attendance sheet for a pay/attendance cycle.
    Columns: DATE, WEEK, TYP, SHIFT, IN/OUT, HOURS, OT, C.OT, Ded, Accr.Ded, STATUS.
    """
    employee = form.cleaned_data["employee"]
    year = form.cleaned_data["year"]
    month = form.cleaned_data["month"]
    start, end = form.period_bounds

    by_date = {
        rec.date: rec
        for rec in DailyAttendance.objects.filter(
            employee=employee,
            date__gte=start,
            date__lte=end,
        ).select_related("shift")
    }
    leave_labels = _leave_labels_for_period(employee, start, end)

    headers = [
        "DATE",
        "WEEK",
        "TYP",
        "SHIFT",
        "IN",
        "OUT",
        "HOURS",
        "OT",
        "C.OT",
        "Ded",
        "Accr. Ded",
        "STATUS",
    ]
    rows = []
    tot_ot = ZERO
    tot_cot = ZERO
    tot_ded = ZERO
    tot_accrued_ded = ZERO

    cur = start
    while cur <= end:
        rec = by_date.get(cur)
        hours = (rec.worked_hours if rec else ZERO) or ZERO
        ot = (rec.overtime_hours if rec else ZERO) or ZERO
        rate = Decimal(rec.ot_rate) if rec and rec.ot_rate is not None else Decimal("1.00")
        status = rec.status if rec else ""

        if rec and rec.status in (
            DailyAttendance.Status.ABSENT,
            DailyAttendance.Status.MISSING_PUNCH,
            DailyAttendance.Status.ON_LEAVE,
        ):
            hours = ZERO
            ot = ZERO

        cot = (
            rec.credited_overtime_hours
            if rec and rec.credited_overtime_hours is not None
            else _cot_hours(ot, rate)
        )
        ded = _ded_hours(rec)
        accrued_ded = (
            rec.accrued_deduction_hours
            if rec and rec.accrued_deduction_hours is not None
            else ZERO
        )

        shift_name = ""
        if rec and rec.shift_id:
            # Prefer short code so PDF columns stay aligned
            shift_name = (rec.shift.code or rec.shift.name or "").upper()[:12]
        elif rec and hours > 0:
            shift_name = "REGULAR"

        rows.append(
            [
                cur.strftime("%d/%m/%Y"),
                WEEKDAY_ABBR[cur.weekday()],
                _typ_code(rec, cur),
                shift_name,
                _punch_time(rec.first_punch_at) if rec else "",
                _punch_time(rec.last_punch_at) if rec else "",
                hours.quantize(Decimal("0.01")),
                _ot_display(ot, status=status),
                cot,
                ded,
                accrued_ded,
                _status_note(rec, leave_label=leave_labels.get(cur, "")),
            ]
        )
        tot_ot += ot
        tot_cot += cot
        tot_ded += ded
        tot_accrued_ded += accrued_ded
        cur += timedelta(days=1)

    rows.append(
        [
            "TOTAL",
            "",
            "",
            "",
            "",
            "",
            "",
            str(tot_ot.quantize(Decimal("0.01"))),
            tot_cot.quantize(Decimal("0.01")),
            tot_ded.quantize(Decimal("0.01")),
            tot_accrued_ded.quantize(Decimal("0.01")),
            "",
        ]
    )

    org = OrganizationSettings.load()
    emp_label = f"{employee.employee_code} {employee.full_name}".strip()
    period_label = f"{start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}"
    return ReportDocument(
        title="Attendance Report",
        subtitle=f"{emp_label} · {period_label}",
        filename=f"attendance_{employee.employee_code}_{year}_{month:02d}",
        sheets=[
            ReportSheet("Attendance", headers, rows),
        ],
        pdf_template="reports/employee_attendance_pdf.html",
        pdf_context={
            "employee_label": emp_label,
            "period_label": period_label,
            "company_name": org.display_name,
            "pdf_engine": "reportlab_attendance",
            "show_signature": True,
        },
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
