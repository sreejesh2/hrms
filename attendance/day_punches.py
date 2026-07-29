"""Helpers to add / fix punches on a single attendance day."""

from __future__ import annotations

from datetime import datetime, time, timedelta

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


def _combine_local(on_date, punch_time):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(on_date, punch_time), tz)


def engine_day_punches(employee, on_date):
    """Punches in the same window used by attendance generation."""
    assignment = assignment_for(employee, on_date)
    shift = assignment.shift if assignment else None
    version = shift_version_on(shift, on_date)
    day_start = _combine_local(on_date, time.min)
    day_end = _combine_local(on_date, time.max)
    if version and version.day_span:
        day_end = _combine_local(
            on_date + timedelta(days=1),
            version.shift_to,
        ) + timedelta(hours=12)
    return list(
        PunchLog.objects.filter(
            employee=employee,
            punched_at__gte=day_start,
            punched_at__lte=day_end,
        )
        .select_related("device")
        .order_by("punched_at")
    )


def set_day_boundary_times(
    employee,
    on_date,
    *,
    first_time=None,
    last_time=None,
    user=None,
):
    """
    Update the day's first/last punch times, then recalculate attendance.

    first_time / last_time: datetime.time or None (leave unchanged).
    If last_time is earlier than first_time, last punch is placed on the next day
    (night-shift style).
    """
    punches = engine_day_punches(employee, on_date)
    actor = user if getattr(user, "is_authenticated", False) else None

    first_at = _combine_local(on_date, first_time) if first_time else None
    last_date = on_date
    if first_time and last_time and last_time <= first_time:
        last_date = on_date + timedelta(days=1)
    last_at = _combine_local(last_date, last_time) if last_time else None

    if not punches:
        if first_at:
            PunchLog.objects.create(
                employee=employee,
                punched_at=first_at,
                punch_type=PunchLog.PunchType.IN,
                source=PunchLog.Source.MANUAL,
                notes="Profile quick edit: In",
                created_by=actor,
            )
        if last_at:
            PunchLog.objects.create(
                employee=employee,
                punched_at=last_at,
                punch_type=PunchLog.PunchType.OUT,
                source=PunchLog.Source.MANUAL,
                notes="Profile quick edit: Out",
                created_by=actor,
            )
    elif len(punches) == 1:
        only_punch = punches[0]
        if first_at is not None and last_at is not None:
            only_punch.punched_at = first_at
            only_punch.punch_type = PunchLog.PunchType.IN
            only_punch.source = PunchLog.Source.MANUAL
            only_punch.save(
                update_fields=["punched_at", "punch_type", "source"]
            )
            PunchLog.objects.create(
                employee=employee,
                punched_at=last_at,
                punch_type=PunchLog.PunchType.OUT,
                source=PunchLog.Source.MANUAL,
                notes="Profile quick edit: Out",
                created_by=actor,
            )
        elif first_at is not None:
            only_punch.punched_at = first_at
            only_punch.punch_type = PunchLog.PunchType.IN
            only_punch.source = PunchLog.Source.MANUAL
            only_punch.save(
                update_fields=["punched_at", "punch_type", "source"]
            )
        elif last_at is not None:
            only_punch.punched_at = last_at
            only_punch.punch_type = PunchLog.PunchType.OUT
            only_punch.source = PunchLog.Source.MANUAL
            only_punch.save(
                update_fields=["punched_at", "punch_type", "source"]
            )
    else:
        first_punch = punches[0]
        last_punch = punches[-1]
        if first_at is not None:
            first_punch.punched_at = first_at
            first_punch.punch_type = PunchLog.PunchType.IN
            first_punch.source = PunchLog.Source.MANUAL
            first_punch.save(
                update_fields=["punched_at", "punch_type", "source"]
            )
        if last_at is not None:
            last_punch.punched_at = last_at
            last_punch.punch_type = PunchLog.PunchType.OUT
            last_punch.source = PunchLog.Source.MANUAL
            last_punch.save(
                update_fields=["punched_at", "punch_type", "source"]
            )

    return generate_daily_attendance(employee, on_date, force=True)


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
