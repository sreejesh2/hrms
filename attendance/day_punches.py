"""Helpers to add / fix punches on a single attendance day."""

from __future__ import annotations

from datetime import datetime, time

from django.utils import timezone

from .engine import generate_daily_attendance, shift_version_on, assignment_for
from .models import PunchLog
from .punch_issues import analyze_punches


def day_punches(employee, on_date):
    return list(
        PunchLog.objects.filter(employee=employee, punched_at__date=on_date)
        .select_related("device")
        .order_by("punched_at")
    )


def add_day_punch(employee, on_date, *, punch_time, punch_type, user=None, notes=""):
    tz = timezone.get_current_timezone()
    punched_at = timezone.make_aware(datetime.combine(on_date, punch_time), tz)
    punch = PunchLog.objects.create(
        employee=employee,
        punched_at=punched_at,
        punch_type=punch_type,
        source=PunchLog.Source.MANUAL,
        notes=notes or "",
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    generate_daily_attendance(employee, on_date, force=True)
    return punch


def update_day_punch(punch, *, punch_time, punch_type, notes=None):
    """Change time/type of an existing punch; keep the same calendar date."""
    on_date = timezone.localtime(punch.punched_at).date()
    employee = punch.employee
    tz = timezone.get_current_timezone()
    punch.punched_at = timezone.make_aware(datetime.combine(on_date, punch_time), tz)
    punch.punch_type = punch_type
    if notes is not None:
        punch.notes = notes
    punch.source = PunchLog.Source.MANUAL
    punch.save(update_fields=["punched_at", "punch_type", "notes", "source"])
    generate_daily_attendance(employee, on_date, force=True)
    return punch


def delete_day_punch(punch):
    employee = punch.employee
    on_date = timezone.localtime(punch.punched_at).date()
    punch.delete()
    generate_daily_attendance(employee, on_date, force=True)
    return on_date


def quick_fix_missing_out(employee, on_date, *, user=None):
    """If day has In but no Out, add Out at shift end (or 18:00)."""
    punches = day_punches(employee, on_date)
    issues = {i.code for i in analyze_punches(punches)}
    if "missing_out" not in issues and "single_punch" not in issues and "open_segment" not in issues:
        return None, "No missing Out detected for this day."

    assignment = assignment_for(employee, on_date)
    shift = assignment.shift if assignment else None
    version = shift_version_on(shift, on_date)
    out_time = version.shift_to if version else time(18, 0)
    punch = add_day_punch(
        employee,
        on_date,
        punch_time=out_time,
        punch_type=PunchLog.PunchType.OUT,
        user=user,
        notes="HR quick-fix: missing Out",
    )
    return punch, f"Added Out at {out_time.strftime('%H:%M')}."


def quick_fix_missing_break_in(employee, on_date, *, user=None):
    """If Break out is open, add Break in at shift break_to or +60m after break out."""
    punches = day_punches(employee, on_date)
    issues = {i.code for i in analyze_punches(punches)}
    if "missing_break_in" not in issues:
        return None, "No open break detected for this day."

    assignment = assignment_for(employee, on_date)
    shift = assignment.shift if assignment else None
    version = shift_version_on(shift, on_date)
    if version and version.break_to:
        break_in = version.break_to
    else:
        # 1 hour after last break_out
        last_bo = next(
            (
                p
                for p in reversed(punches)
                if p.punch_type == PunchLog.PunchType.BREAK_OUT
            ),
            None,
        )
        if last_bo:
            local = timezone.localtime(last_bo.punched_at)
            total = local.hour * 60 + local.minute + 60
            break_in = time(min(total // 60, 23), total % 60)
        else:
            break_in = time(14, 0)

    punch = add_day_punch(
        employee,
        on_date,
        punch_time=break_in,
        punch_type=PunchLog.PunchType.BREAK_IN,
        user=user,
        notes="HR quick-fix: missing Break in",
    )
    return punch, f"Added Break in at {break_in.strftime('%H:%M')}."
