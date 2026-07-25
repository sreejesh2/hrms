"""Monthly attendance register — view, edit, lock/unlock."""

from datetime import date, timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.permissions import permission_required, request_has_perm
from core.pagination import paginate
from people.models import Employee
from setup.cycles import (
    cycle_dates,
    cycle_help_text,
    get_cycle_start_day,
    period_bounds,
    period_for_date,
    period_label,
)

from .engine import generate_attendance_for_date, generate_daily_attendance
from .forms import DailyAttendanceEditForm, DayPunchEditForm, DayPunchForm, MonthRegisterForm
from .models import DailyAttendance, PunchLog
from . import day_punches as punch_ops
from .punch_issues import analyze_punches


STATUS_CELL = {
    DailyAttendance.Status.PRESENT: ("P", "cell-p"),
    DailyAttendance.Status.ABSENT: ("A", "cell-a"),
    DailyAttendance.Status.HALF_DAY: ("H", "cell-h"),
    DailyAttendance.Status.WEEKLY_OFF: ("W", "cell-w"),
    DailyAttendance.Status.HOLIDAY: ("O", "cell-o"),
    DailyAttendance.Status.ON_LEAVE: ("L", "cell-l"),
    DailyAttendance.Status.MISSING_PUNCH: ("M", "cell-m"),
}

WD = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def _register_redirect(year, month, department_id=None):
    url = reverse("attendance_ops:register_month")
    qs = f"?year={year}&month={month}"
    if department_id:
        qs += f"&department={department_id}"
    return redirect(url + qs)


def _shift_period(year, month, delta):
    m = month + delta
    y = year
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return y, m


def _month_bounds(year: int, month: int):
    """Compat wrapper — returns start, end, day_count."""
    start, end = period_bounds(year, month)
    return start, end, (end - start).days + 1


@permission_required("attendance.view")
def register_month(request):
    today = timezone.localdate()
    cur_y, cur_m, _, _ = period_for_date(today)
    form = MonthRegisterForm(
        request.GET or None,
        initial={"year": cur_y, "month": str(cur_m)},
    )
    if form.is_valid():
        year = form.cleaned_data["year"]
        month = form.cleaned_data["month"]
        department = form.cleaned_data.get("department")
    else:
        year, month, department = cur_y, cur_m, None

    start, end = period_bounds(year, month)
    dates = cycle_dates(start, end)
    cycle_day = get_cycle_start_day()
    prev_year, prev_month = _shift_period(year, month, -1)
    next_year, next_month = _shift_period(year, month, 1)

    day_headers = []
    for d in dates:
        wd = d.weekday()
        day_headers.append(
            {
                "n": d.day,
                "wd": WD[wd],
                "weekend": wd >= 5,
                "today": d == today,
                "other_month": d.month != month,
                "month_short": d.strftime("%b") if (d.month != month or cycle_day > 1) else "",
            }
        )

    employees = (
        Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        )
        .select_related("department")
        .order_by("employee_code")
    )
    if department:
        employees = employees.filter(department=department)

    page_obj = paginate(request, employees, per_page=40)
    employees = list(page_obj)
    emp_ids = [e.pk for e in employees]

    rows_qs = DailyAttendance.objects.filter(
        employee_id__in=emp_ids, date__gte=start, date__lte=end
    )
    by_key = {(r.employee_id, r.date): r for r in rows_qs}

    grid_rows = []
    locked_count = 0
    filled_count = 0
    status_counts = {
        "present": 0,
        "absent": 0,
        "half": 0,
        "missing": 0,
        "leave": 0,
        "off": 0,
    }
    for emp in employees:
        cells = []
        for d in dates:
            row = by_key.get((emp.pk, d))
            weekend = d.weekday() >= 5
            is_today = d == today
            if row:
                filled_count += 1
                if row.is_locked:
                    locked_count += 1
                if row.status == DailyAttendance.Status.PRESENT:
                    status_counts["present"] += 1
                elif row.status == DailyAttendance.Status.ABSENT:
                    status_counts["absent"] += 1
                elif row.status == DailyAttendance.Status.HALF_DAY:
                    status_counts["half"] += 1
                elif row.status == DailyAttendance.Status.MISSING_PUNCH:
                    status_counts["missing"] += 1
                elif row.status == DailyAttendance.Status.ON_LEAVE:
                    status_counts["leave"] += 1
                elif row.status in (
                    DailyAttendance.Status.WEEKLY_OFF,
                    DailyAttendance.Status.HOLIDAY,
                ):
                    status_counts["off"] += 1
                letter, css = STATUS_CELL.get(row.status, ("?", "cell-x"))
                cells.append(
                    {
                        "day": d.day,
                        "letter": letter,
                        "css": css,
                        "locked": row.is_locked,
                        "weekend": weekend,
                        "today": is_today,
                        "title": f"{d.isoformat()} · {row.get_status_display()} · {row.worked_hours}h"
                        + (" · Locked" if row.is_locked else ""),
                        "day_iso": d.isoformat(),
                    }
                )
            else:
                cells.append(
                    {
                        "day": d.day,
                        "letter": "·",
                        "css": "cell-empty",
                        "locked": False,
                        "weekend": weekend,
                        "today": is_today,
                        "title": f"{d.isoformat()} · No attendance — click to open",
                        "day_iso": d.isoformat(),
                    }
                )
        grid_rows.append({"employee": emp, "cells": cells})

    expected_cells = max(len(employees) * len(dates), 1)
    coverage_pct = round((filled_count / expected_cells) * 100)

    return render(
        request,
        "attendance/register_month.html",
        {
            "page_title": "Monthly register",
            "form": form,
            "year": year,
            "month": month,
            "month_label": period_label(year, month, start, end),
            "cycle_hint": cycle_help_text(cycle_day),
            "cycle_start_day": cycle_day,
            "period_start": start,
            "period_end": end,
            "day_headers": day_headers,
            "grid_rows": grid_rows,
            "page_obj": page_obj,
            "filled_count": filled_count,
            "locked_count": locked_count,
            "employee_count": page_obj.paginator.count,
            "status_counts": status_counts,
            "coverage_pct": coverage_pct,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "department_id": department.pk if department else "",
            "can_manage": request_has_perm(request, "attendance.manage"),
        },
    )


@permission_required("attendance.manage")
@require_http_methods(["POST"])
def register_generate_month(request):
    try:
        year = int(request.POST.get("year") or 0)
        month = int(request.POST.get("month") or 0)
        force = request.POST.get("force") == "1"
        dept = request.POST.get("department") or ""
    except (TypeError, ValueError):
        messages.error(request, "Invalid month.")
        return redirect("attendance_ops:register_month")

    start, end = period_bounds(year, month)
    total = 0
    day = start
    while day <= end:
        total += len(generate_attendance_for_date(day, force=force))
        day += timedelta(days=1)

    messages.success(
        request,
        f"Generated attendance for {start} → {end} "
        f"({total} updates; force={'on' if force else 'off'}).",
    )
    return _register_redirect(year, month, dept or None)


@permission_required("attendance.manage")
@require_http_methods(["POST"])
def register_lock_month(request):
    year = int(request.POST.get("year"))
    month = int(request.POST.get("month"))
    lock = request.POST.get("lock") == "1"
    dept = request.POST.get("department") or ""
    start, end = period_bounds(year, month)
    updated = DailyAttendance.objects.filter(date__gte=start, date__lte=end).update(
        is_locked=lock
    )
    messages.success(
        request,
        f"{'Locked' if lock else 'Unlocked'} {updated} day(s) in "
        f"{period_label(year, month, start, end)}.",
    )
    return _register_redirect(year, month, dept or None)


@permission_required("attendance.view")
@require_http_methods(["GET", "POST"])
def register_day(request, employee_id, day_iso):
    employee = get_object_or_404(
        Employee.objects.select_related("department"), pk=employee_id
    )
    try:
        on_date = date.fromisoformat(day_iso)
    except ValueError:
        messages.error(request, "Invalid date.")
        return redirect("attendance_ops:register_month")

    row, _ = DailyAttendance.objects.get_or_create(
        employee=employee,
        date=on_date,
        defaults={"status": DailyAttendance.Status.ABSENT},
    )
    punches = punch_ops.day_punches(employee, on_date)
    punch_issues = analyze_punches(punches)

    form = DailyAttendanceEditForm(instance=row)
    punch_form = DayPunchForm(
        initial={"punch_type": PunchLog.PunchType.OUT}, prefix="punch"
    )
    editing_punch = None
    edit_punch_form = None
    can_manage = request_has_perm(request, "attendance.manage")

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "You cannot edit attendance.")
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )

        action = request.POST.get("action") or "save"
        if action == "lock":
            row.is_locked = True
            row.save(update_fields=["is_locked", "updated_at"])
            messages.success(request, f"Locked {on_date} for {employee.employee_code}.")
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )
        if action == "unlock":
            row.is_locked = False
            row.save(update_fields=["is_locked", "updated_at"])
            messages.success(request, f"Unlocked {on_date} for {employee.employee_code}.")
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )
        if action == "regen":
            if row.is_locked:
                messages.error(request, "Unlock the day before regenerating from punches.")
            else:
                generate_daily_attendance(employee, on_date, force=False)
                messages.success(request, "Recalculated from punches.")
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )

        if row.is_locked and action in (
            "save",
            "add_punch",
            "edit_punch",
            "start_edit_punch",
            "delete_punch",
            "fix_missing_out",
            "fix_missing_break_in",
        ):
            messages.error(request, "This day is locked. Unlock before editing.")
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )

        if action == "save":
            form = DailyAttendanceEditForm(request.POST, instance=row)
            if form.is_valid():
                form.save()
                messages.success(request, "Attendance updated.")
                return redirect(
                    "attendance_ops:register_day",
                    employee_id=employee.pk,
                    day_iso=day_iso,
                )

        elif action == "add_punch":
            punch_form = DayPunchForm(request.POST, prefix="punch")
            if punch_form.is_valid():
                punch_ops.add_day_punch(
                    employee,
                    on_date,
                    punch_time=punch_form.cleaned_data["punch_time"],
                    punch_type=punch_form.cleaned_data["punch_type"],
                    user=request.user,
                    notes=punch_form.cleaned_data.get("notes") or "",
                )
                messages.success(request, "Punch added and attendance recalculated.")
            else:
                messages.error(request, "Could not add punch — check time and type.")
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )

        elif action == "start_edit_punch":
            editing_punch = get_object_or_404(
                PunchLog, pk=request.POST.get("punch_id"), employee=employee
            )
            local = timezone.localtime(editing_punch.punched_at)
            edit_punch_form = DayPunchEditForm(
                initial={
                    "punch_id": editing_punch.pk,
                    "punch_time": local.time().replace(microsecond=0),
                    "punch_type": editing_punch.punch_type,
                    "notes": editing_punch.notes,
                },
                prefix="edit",
            )

        elif action == "edit_punch":
            edit_punch_form = DayPunchEditForm(request.POST, prefix="edit")
            if edit_punch_form.is_valid():
                punch = get_object_or_404(
                    PunchLog,
                    pk=edit_punch_form.cleaned_data["punch_id"],
                    employee=employee,
                )
                punch_ops.update_day_punch(
                    punch,
                    punch_time=edit_punch_form.cleaned_data["punch_time"],
                    punch_type=edit_punch_form.cleaned_data["punch_type"],
                    notes=edit_punch_form.cleaned_data.get("notes") or "",
                )
                messages.success(request, "Punch updated and attendance recalculated.")
                return redirect(
                    "attendance_ops:register_day",
                    employee_id=employee.pk,
                    day_iso=day_iso,
                )
            editing_punch = get_object_or_404(
                PunchLog,
                pk=request.POST.get("edit-punch_id"),
                employee=employee,
            )
            messages.error(request, "Could not update punch — check time and type.")

        elif action == "delete_punch":
            punch = get_object_or_404(
                PunchLog, pk=request.POST.get("punch_id"), employee=employee
            )
            punch_ops.delete_day_punch(punch)
            messages.success(request, "Punch deleted and attendance recalculated.")
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )

        elif action == "fix_missing_out":
            _, msg = punch_ops.quick_fix_missing_out(
                employee, on_date, user=request.user
            )
            messages.success(request, msg)
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )

        elif action == "fix_missing_break_in":
            _, msg = punch_ops.quick_fix_missing_break_in(
                employee, on_date, user=request.user
            )
            messages.success(request, msg)
            return redirect(
                "attendance_ops:register_day",
                employee_id=employee.pk,
                day_iso=day_iso,
            )

    row.refresh_from_db()
    punches = punch_ops.day_punches(employee, on_date)
    punch_issues = analyze_punches(punches)
    issue_codes = {i.code for i in punch_issues}
    if not (request.method == "POST" and request.POST.get("action") == "save" and form.errors):
        form = DailyAttendanceEditForm(instance=row)

    return render(
        request,
        "attendance/register_day.html",
        {
            "page_title": f"{employee.employee_code} · {on_date}",
            "employee": employee,
            "row": row,
            "form": form,
            "punch_form": punch_form,
            "edit_punch_form": edit_punch_form,
            "editing_punch": editing_punch,
            "punches": punches,
            "punch_issues": punch_issues,
            "can_fix_out": bool(
                issue_codes & {"missing_out", "single_punch", "open_segment"}
            ),
            "can_fix_break": "missing_break_in" in issue_codes,
            "on_date": on_date,
            "can_manage": can_manage,
            "can_request_regularization": can_manage
            or request_has_perm(request, "attendance.request_regularization"),
        },
    )
