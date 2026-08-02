"""Shift assignment helpers — safe for bulk / import / hire defaults."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import ShiftAssignment


@transaction.atomic
def assign_employee_shift(
    *,
    employee,
    shift,
    calendar=None,
    effective_from=None,
    effective_to=None,
    notes="",
    replace_overlapping=True,
    refresh_attendance=True,
):
    """
    Create an active shift assignment.
    If replace_overlapping, close/deactivate conflicting active rows first
    so 2000-employee bulk runs don't fail on unique-range clashes.

    When effective_to is set, the prior covering assignment is resumed the
    day after so temporary night/day rotations don't leave a gap.
    """
    if effective_from is None:
        effective_from = timezone.localdate()
    if effective_to and effective_to < effective_from:
        raise ValueError("Effective to must be on or after effective from.")

    same = ShiftAssignment.objects.filter(
        employee=employee,
        shift=shift,
        calendar=calendar,
        effective_from=effective_from,
        effective_to=effective_to,
        is_active=True,
    ).first()
    if same:
        same._assignment_created = False
        if refresh_attendance:
            refresh_attendance_for_range(
                employee,
                effective_from,
                effective_to or timezone.localdate(),
            )
        return same

    # Capture the assignment that currently covers the start date so a
    # temporary dated assignment can resume it after effective_to.
    covering = (
        ShiftAssignment.objects.filter(
            employee=employee,
            is_active=True,
            effective_from__lte=effective_from,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=effective_from))
        .select_related("shift", "calendar")
        .order_by("-effective_from", "-id")
        .first()
    )
    covering_snapshot = None
    if covering:
        covering_snapshot = {
            "shift": covering.shift,
            "calendar": covering.calendar,
            "effective_to": covering.effective_to,
            "notes": covering.notes or "",
        }
        # Keep the employee's work-week when the form leaves calendar blank.
        if calendar is None and covering.calendar_id:
            calendar = covering.calendar

    if replace_overlapping:
        day_before = effective_from - timedelta(days=1)
        for other in ShiftAssignment.objects.filter(
            employee=employee, is_active=True
        ).select_for_update():
            if other.effective_from >= effective_from:
                other.is_active = False
                if other.effective_to is None or other.effective_to >= effective_from:
                    other.effective_to = day_before
                other.save(update_fields=["is_active", "effective_to", "updated_at"])
            elif other.effective_to is None or other.effective_to >= effective_from:
                other.effective_to = day_before
                other.save(update_fields=["effective_to", "updated_at"])

    assignment = ShiftAssignment(
        employee=employee,
        shift=shift,
        calendar=calendar,
        effective_from=effective_from,
        effective_to=effective_to,
        notes=notes or "",
        is_active=True,
    )
    # With replacement off, validation prevents silent overlapping shifts.
    # With replacement on, this also verifies the range after conflicts close.
    assignment.full_clean()
    assignment.save()
    assignment._assignment_created = True

    if (
        effective_to
        and covering_snapshot
        and (
            covering_snapshot["shift"].pk != shift.pk
            or (covering_snapshot["calendar"].pk if covering_snapshot["calendar"] else None)
            != (calendar.pk if calendar else None)
        )
    ):
        resume_from = effective_to + timedelta(days=1)
        original_end = covering_snapshot["effective_to"]
        if original_end is None or original_end >= resume_from:
            resume = ShiftAssignment(
                employee=employee,
                shift=covering_snapshot["shift"],
                calendar=covering_snapshot["calendar"],
                effective_from=resume_from,
                effective_to=original_end,
                notes=covering_snapshot["notes"] or "Resumed after temporary shift",
                is_active=True,
            )
            resume.full_clean()
            resume.save()

    if refresh_attendance:
        end = effective_to or timezone.localdate()
        if end < effective_from:
            end = effective_from
        # Include the first day of any resumed prior shift.
        refresh_end = end + timedelta(days=1) if effective_to else end
        refresh_attendance_for_range(employee, effective_from, refresh_end)

    return assignment


@transaction.atomic
def bulk_assign_employees(
    employees,
    *,
    shift,
    calendar=None,
    effective_from=None,
    effective_to=None,
    notes="Bulk assign",
    replace_overlapping=True,
):
    """Assign one rule to many employees and return a clear result summary."""
    result = {"created": 0, "skipped": 0, "failed": []}
    for employee in employees:
        try:
            assignment = assign_employee_shift(
                employee=employee,
                shift=shift,
                calendar=calendar,
                effective_from=effective_from,
                effective_to=effective_to,
                notes=notes,
                replace_overlapping=replace_overlapping,
            )
        except Exception as exc:  # validation result must identify the employee
            result["failed"].append(
                {
                    "employee_code": employee.employee_code,
                    "message": str(exc),
                }
            )
            continue
        if getattr(assignment, "_assignment_created", True):
            result["created"] += 1
        else:
            result["skipped"] += 1
    return result


def apply_department_defaults(employee, *, effective_from=None, only_if_missing=True):
    """
    If the employee's department has default_shift, create an assignment.
    Returns the assignment or None.
    """
    dept = employee.department
    if not dept or not dept.default_shift_id:
        return None
    if only_if_missing:
        has_active = ShiftAssignment.objects.filter(
            employee=employee, is_active=True
        ).exists()
        if has_active:
            return None
    return assign_employee_shift(
        employee=employee,
        shift=dept.default_shift,
        calendar=dept.default_calendar,
        effective_from=effective_from or employee.date_of_joining,
        notes=f"Department default ({dept.code})",
        replace_overlapping=True,
    )


def refresh_attendance_for_range(employee, start_date, end_date):
    """
    Rebuild daily attendance so profile/register show the assigned shift.
    Safe to call after assignment create/edit — leave days keep leave status
    but pick up the current shift.
    """
    from .engine import generate_daily_attendance

    if end_date < start_date:
        start_date, end_date = end_date, start_date
    day = start_date
    while day <= end_date:
        generate_daily_attendance(employee, day, force=True)
        day += timedelta(days=1)
