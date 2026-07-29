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
    effective_to=None,
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
        return same

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
