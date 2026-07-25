"""Shift assignment helpers — safe for bulk / import / hire defaults."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ShiftAssignment


@transaction.atomic
def assign_employee_shift(
    *,
    employee,
    shift,
    calendar=None,
    effective_from=None,
    notes="",
    replace_overlapping=True,
):
    """
    Create an active shift assignment.
    If replace_overlapping, close/deactivate conflicting active rows first
    so 2000-employee bulk runs don't fail on unique-range clashes.
    """
    if effective_from is None:
        effective_from = timezone.localdate()

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
        notes=notes or "",
        is_active=True,
    )
    # Skip model.clean overlap check — we already closed overlaps
    assignment.save()
    return assignment


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
