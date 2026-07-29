"""Attendance calculation: punches → daily status (multi In/Break/Out supported)."""

from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import (
    DailyAttendance,
    Holiday,
    PunchLog,
    ShiftAssignment,
    WorkCalendar,
    WorkShiftVersion,
)


WRONG_PUNCH_NOTE = "Marked Absent, Due to Wrong P."


def _local_date(dt):
    if timezone.is_aware(dt):
        return timezone.localtime(dt).date()
    return dt.date()


def _local_time(dt):
    if timezone.is_aware(dt):
        return timezone.localtime(dt).time()
    return dt.time()


def assignment_for(employee, on_date):
    return (
        ShiftAssignment.objects.filter(
            employee=employee,
            is_active=True,
            effective_from__lte=on_date,
        )
        .filter(
            models_q_effective_to(on_date)
        )
        .select_related(
            "shift",
            "shift__ot_policy",
            "shift__late_penalty_policy",
            "calendar",
        )
        .order_by("-effective_from", "-id")
        .first()
    )


def models_q_effective_to(on_date):
    from django.db.models import Q

    return Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)


def shift_version_on(shift, on_date):
    if not shift:
        return None
    return (
        WorkShiftVersion.objects.filter(shift=shift, effective_from__lte=on_date)
        .order_by("-effective_from", "-id")
        .first()
    )


def holiday_on(on_date, location=None):
    qs = Holiday.objects.filter(date=on_date, is_active=True)
    # Prefer location-specific, else company-wide (location null)
    if location:
        specific = qs.filter(location=location).first()
        if specific:
            return specific
    return qs.filter(location__isnull=True).first()


def calendar_is_working_day(calendar: WorkCalendar | None, on_date) -> bool:
    if not calendar:
        # Default Mon–Fri if no calendar assigned
        return on_date.weekday() < 5
    mapping = (
        calendar.monday,
        calendar.tuesday,
        calendar.wednesday,
        calendar.thursday,
        calendar.friday,
        calendar.saturday,
        calendar.sunday,
    )
    return bool(mapping[on_date.weekday()])


def pair_worked_hours(punches: list[PunchLog]) -> tuple[Decimal, Decimal, int]:
    """
    Pair chronological punches as In/Out segments.
    Supports: In → Break out → Break in → Out (and plain In/Out pairs).
    Returns (worked_hours, break_hours, punch_count).
    """
    if not punches:
        return Decimal("0.00"), Decimal("0.00"), 0

    ordered = sorted(punches, key=lambda p: p.punched_at)
    worked = Decimal("0.00")
    break_hrs = Decimal("0.00")
    open_in = None
    open_break = None

    for p in ordered:
        ptype = p.punch_type
        # Auto: alternate in/out by position when type unknown
        if ptype == PunchLog.PunchType.AUTO:
            if open_in is None:
                ptype = PunchLog.PunchType.IN
            elif open_break is not None:
                ptype = PunchLog.PunchType.BREAK_IN
            else:
                # If odd segment open, treat as out; else break_out if mid-day heuristic
                ptype = PunchLog.PunchType.OUT

        if ptype in (PunchLog.PunchType.IN, PunchLog.PunchType.BREAK_IN):
            if open_break is not None and ptype == PunchLog.PunchType.BREAK_IN:
                secs = (p.punched_at - open_break).total_seconds()
                if secs > 0:
                    break_hrs += Decimal(str(secs)) / Decimal("3600")
                open_break = None
                open_in = p.punched_at
            elif open_in is None:
                open_in = p.punched_at
        elif ptype == PunchLog.PunchType.BREAK_OUT:
            if open_in is not None:
                secs = (p.punched_at - open_in).total_seconds()
                if secs > 0:
                    worked += Decimal(str(secs)) / Decimal("3600")
                open_in = None
            open_break = p.punched_at
        elif ptype == PunchLog.PunchType.OUT:
            if open_in is not None:
                secs = (p.punched_at - open_in).total_seconds()
                if secs > 0:
                    worked += Decimal(str(secs)) / Decimal("3600")
                open_in = None
            open_break = None

    # Fallback: first–last minus inferred breaks when all AUTO left unpaired oddly
    if worked == 0 and len(ordered) >= 2:
        secs = (ordered[-1].punched_at - ordered[0].punched_at).total_seconds()
        if secs > 0:
            worked = Decimal(str(secs)) / Decimal("3600")
            # subtract middle pairs as break if 4+ punches
            if len(ordered) >= 4:
                mid = (ordered[2].punched_at - ordered[1].punched_at).total_seconds()
                if mid > 0:
                    break_hrs = Decimal(str(mid)) / Decimal("3600")
                    worked = max(Decimal("0.00"), worked - break_hrs)

    q = Decimal("0.01")
    return worked.quantize(q), break_hrs.quantize(q), len(ordered)


def worked_hours_after(punches: list[PunchLog], cutoff) -> Decimal:
    """Return paired work time occurring strictly after a datetime cutoff."""
    ordered = sorted(punches, key=lambda p: p.punched_at)
    worked = Decimal("0.00")
    open_in = None

    for punch in ordered:
        punch_type = punch.punch_type
        if punch_type == PunchLog.PunchType.AUTO:
            punch_type = (
                PunchLog.PunchType.IN
                if open_in is None
                else PunchLog.PunchType.OUT
            )

        if punch_type in (PunchLog.PunchType.IN, PunchLog.PunchType.BREAK_IN):
            if open_in is None:
                open_in = punch.punched_at
        elif punch_type in (PunchLog.PunchType.BREAK_OUT, PunchLog.PunchType.OUT):
            if open_in is not None:
                segment_start = max(open_in, cutoff)
                if punch.punched_at > segment_start:
                    seconds = (punch.punched_at - segment_start).total_seconds()
                    worked += Decimal(str(seconds)) / Decimal("3600")
                open_in = None

    return worked.quantize(Decimal("0.01"))


def apply_configured_break_fallback(
    *,
    worked: Decimal,
    break_hours: Decimal,
    punches: list[PunchLog],
    version: WorkShiftVersion | None,
    is_working_day: bool,
) -> tuple[Decimal, Decimal]:
    """
    Deduct the shift's configured break when a normal workday has only In/Out.

    Explicit/multi-segment punches take priority because they describe the
    employee's actual break duration.
    """
    if (
        not is_working_day
        or not version
        or not version.break_hours
        or len(punches) != 2
    ):
        return worked, break_hours

    configured_break = Decimal(version.break_hours)
    worked = max(Decimal("0.00"), worked - configured_break)
    q = Decimal("0.01")
    return worked.quantize(q), configured_break.quantize(q)


def calculate_break_overrun_minutes(
    break_hours: Decimal,
    version: WorkShiftVersion | None,
) -> int:
    """Return actual break minutes beyond the shift's configured allowance."""
    if not version:
        return 0
    allowed = Decimal(version.break_hours or 0)
    excess_hours = max(Decimal("0.00"), Decimal(break_hours or 0) - allowed)
    return int(
        (excess_hours * Decimal("60")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def calculate_break_overrun_penalty_minutes(
    break_overrun_minutes: int,
    shift,
) -> int:
    """
    Return minutes to deduct from payable hours for break overrun.

    Only applies when the shift enables break-overrun penalties. Grace minutes
    are ignored first.
    """
    if not shift or not getattr(shift, "break_overrun_penalty_enabled", False):
        return 0
    grace = int(getattr(shift, "break_overrun_grace_minutes", 0) or 0)
    return max(0, int(break_overrun_minutes or 0) - grace)


def _combine(on_date, t: time):
    tz = timezone.get_current_timezone()
    naive = datetime.combine(on_date, t)
    return timezone.make_aware(naive, tz) if timezone.is_naive(naive) else naive


@transaction.atomic
def generate_daily_attendance(employee, on_date, *, force=False):
    """Build/update DailyAttendance for one employee-day from punches + rules."""
    existing = DailyAttendance.objects.filter(employee=employee, date=on_date).first()

    # Approved leave is authoritative, including during Force generation.
    # Without this check, regenerating attendance can turn an approved leave
    # day back into Absent while leaving the "Leave: …" note behind.
    from leave.models import LeaveRequest

    approved_leave = (
        LeaveRequest.objects.filter(
            employee=employee,
            status=LeaveRequest.Status.APPROVED,
            apply_to_attendance=True,
            start_date__lte=on_date,
            end_date__gte=on_date,
        )
        .select_related("leave_type")
        .order_by("-reviewed_at", "-id")
        .first()
    )
    if approved_leave:
        leave_status = (
            DailyAttendance.Status.HALF_DAY
            if approved_leave.is_half_day
            else DailyAttendance.Status.ON_LEAVE
        )
        note = (
            "Half-day leave"
            if approved_leave.is_half_day
            else f"Leave: {approved_leave.leave_type.code}"
        )
        if existing:
            notes = existing.notes or ""
            if note not in notes:
                notes = (f"{notes} | {note}" if notes else note)[:255]
            existing.status = leave_status
            existing.is_locked = True
            existing.notes = notes
            existing.save(update_fields=["status", "is_locked", "notes", "updated_at"])
            return existing
        return DailyAttendance.objects.create(
            employee=employee,
            date=on_date,
            status=leave_status,
            is_locked=True,
            notes=note,
        )

    if existing and existing.is_locked and not force:
        return existing

    assignment = assignment_for(employee, on_date)
    shift = assignment.shift if assignment else None
    calendar = assignment.calendar if assignment else None
    version = shift_version_on(shift, on_date)
    hol = holiday_on(on_date, getattr(employee, "location", None))

    day_start = _combine(on_date, time.min)
    day_end = _combine(on_date, time.max)
    # Night-shift OT can continue after the scheduled shift end. Keep a
    # bounded post-shift window so an early punch for the next shift is not
    # attached to this attendance day.
    if version and version.day_span:
        day_end = _combine(
            on_date + timedelta(days=1),
            version.shift_to,
        ) + timedelta(hours=12)

    punches = list(
        PunchLog.objects.filter(
            employee=employee,
            punched_at__gte=day_start,
            punched_at__lte=day_end,
        ).order_by("punched_at")
    )

    worked, break_hrs, punch_count = pair_worked_hours(punches)
    worked, break_hrs = apply_configured_break_fallback(
        worked=worked,
        break_hours=break_hrs,
        punches=punches,
        version=version,
        is_working_day=not hol and calendar_is_working_day(calendar, on_date),
    )
    break_overrun_minutes = calculate_break_overrun_minutes(break_hrs, version)
    break_overrun_penalty_minutes = calculate_break_overrun_penalty_minutes(
        break_overrun_minutes,
        shift,
    )
    first_punch = punches[0].punched_at if punches else None
    last_punch = punches[-1].punched_at if punches else None

    from .ot import (
        apply_late_penalty,
        calculate_overtime,
        get_late_penalty_policy_for_shift,
        get_ot_policy_for_employee,
        special_ot_amount_for_day,
    )

    policy = get_ot_policy_for_employee(employee, shift)
    late_policy = get_late_penalty_policy_for_shift(shift)

    expected = version.work_hours if version else Decimal("0.00")
    if version and version.break_hours:
        # Compare attendance against net working hours (shift minus break)
        expected = max(Decimal("0.00"), expected - version.break_hours)

    status = DailyAttendance.Status.ABSENT
    late = 0
    early = 0
    ot = Decimal("0.00")
    ot_rate = Decimal("1.00")
    is_holiday = False
    is_weekly_off = False
    wrong_punch = False
    actual_ot = Decimal("0.00")

    if hol:
        status = DailyAttendance.Status.HOLIDAY
        expected = Decimal("0.00")
        is_holiday = True
    elif not calendar_is_working_day(calendar, on_date):
        status = DailyAttendance.Status.WEEKLY_OFF
        expected = Decimal("0.00")
        is_weekly_off = True
    elif punch_count == 0:
        status = DailyAttendance.Status.ABSENT
    elif punch_count == 1:
        # Incomplete pair (IN without OUT, etc.) — company rule: mark absent, 0 hours
        if version and version.single_punch_at_shift_start:
            status = DailyAttendance.Status.PRESENT
            worked = expected
        else:
            status = DailyAttendance.Status.MISSING_PUNCH
            wrong_punch = True
            worked = Decimal("0.00")
            break_hrs = Decimal("0.00")
            notes = WRONG_PUNCH_NOTE
    else:
        status = DailyAttendance.Status.PRESENT
        half_threshold = (expected * Decimal("0.5")) if expected else Decimal("0.00")
        if expected and worked < half_threshold:
            status = DailyAttendance.Status.HALF_DAY

        if version and first_punch:
            shift_start = _combine(on_date, version.shift_from)
            delta = (first_punch - shift_start).total_seconds() / 60
            if delta > 0:
                late = int(delta)
        if version and last_punch and not version.day_span:
            shift_end = _combine(on_date, version.shift_to)
            delta = (shift_end - last_punch).total_seconds() / 60
            if delta > 0:
                early = int(delta)

    if not wrong_punch:
        if is_weekly_off or is_holiday:
            actual_ot = worked
        elif version:
            shift_end_date = on_date + timedelta(days=1) if version.day_span else on_date
            actual_ot = worked_hours_after(
                punches,
                _combine(shift_end_date, version.shift_to),
            )

    # OT: weekday excess, or all hours on off/holiday when policy says so
    if (
        not wrong_punch
        and (
            punch_count >= 2
            or (punch_count == 1 and status == DailyAttendance.Status.PRESENT)
        )
    ):
        ot, ot_rate, _ot_note = calculate_overtime(
            worked=worked,
            expected=expected,
            policy=policy,
            is_weekly_off=is_weekly_off,
            is_holiday=is_holiday,
        )

    # Late / break-overrun penalties reduce payable hours; OT stays on worked hours
    apply_penalty = status in (
        DailyAttendance.Status.PRESENT,
        DailyAttendance.Status.HALF_DAY,
    )
    if apply_penalty and late > 0:
        payable, penalty_minutes = apply_late_penalty(
            worked=worked,
            late_minutes=late,
            policy=late_policy,
        )
    else:
        payable = worked if not wrong_punch else Decimal("0.00")
        penalty_minutes = 0

    if apply_penalty and break_overrun_penalty_minutes > 0 and not wrong_punch:
        deduct_hours = (
            Decimal(break_overrun_penalty_minutes) / Decimal("60")
        ).quantize(Decimal("0.01"))
        payable = max(Decimal("0.00"), payable - deduct_hours).quantize(Decimal("0.01"))
    elif wrong_punch:
        break_overrun_penalty_minutes = 0

    if wrong_punch:
        ot = Decimal("0.00")
        ot_rate = Decimal("1.00")
        payable = Decimal("0.00")
        break_overrun_penalty_minutes = 0

    hourly_divisor = int(getattr(policy, "hourly_divisor", None) or 240)
    special_ot = (
        Decimal("0.00")
        if wrong_punch
        else special_ot_amount_for_day(
            policy,
            is_weekly_off=is_weekly_off,
            is_holiday=is_holiday,
        )
    )

    defaults = {
        "status": status,
        "shift": shift,
        "calendar": calendar,
        "holiday": hol,
        "first_punch_at": first_punch,
        "last_punch_at": last_punch,
        "punch_count": punch_count,
        "worked_hours": worked,
        "payable_hours": payable,
        "break_hours": break_hrs,
        "break_overrun_minutes": break_overrun_minutes,
        "break_overrun_penalty_minutes": break_overrun_penalty_minutes,
        "expected_hours": expected,
        "actual_overtime_hours": actual_ot,
        "overtime_hours": ot,
        "credited_overtime_hours": None,
        "accrued_deduction_hours": Decimal("0.00"),
        "ot_policy": policy,
        "ot_rate": ot_rate,
        "hourly_divisor": hourly_divisor,
        "special_ot_amount": special_ot,
        "late_minutes": late,
        "penalty_minutes": penalty_minutes,
        "early_leave_minutes": early,
        "generated_at": timezone.now(),
    }
    if wrong_punch:
        defaults["notes"] = WRONG_PUNCH_NOTE
    elif existing and existing.notes == WRONG_PUNCH_NOTE:
        # Punches fixed — clear auto wrong-punch note only
        defaults["notes"] = ""

    obj, _ = DailyAttendance.objects.update_or_create(
        employee=employee,
        date=on_date,
        defaults=defaults,
    )
    return obj


def generate_attendance_for_date(on_date, *, employee_ids=None, force=False):
    from people.models import Employee

    qs = Employee.objects.filter(
        status__in=[
            Employee.Status.ACTIVE,
            Employee.Status.ON_LEAVE,
            Employee.Status.DRAFT,
        ]
    )
    if employee_ids:
        qs = qs.filter(pk__in=employee_ids)
    results = []
    for emp in qs.iterator():
        results.append(generate_daily_attendance(emp, on_date, force=force))
    return results
