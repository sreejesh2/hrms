"""Overtime calculation from worked hours + shift/day context + OT policy."""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from .models import LatePenaltyPolicy, LatePenaltyTier, OvertimePolicy


def get_ot_policy_for_shift(shift):
    if shift and shift.ot_policy_id and shift.ot_policy.is_active:
        return shift.ot_policy
    return (
        OvertimePolicy.objects.filter(is_default=True, is_active=True).first()
        or OvertimePolicy.objects.filter(is_active=True).order_by("code").first()
    )


def get_ot_policy_for_position(position):
    """Return the OT policy mapped to this position, if any."""
    if not position or not getattr(position, "pk", None):
        return None
    from .engine import batch_cached

    return batch_cached(
        ("ot_policy_position", position.pk),
        lambda: OvertimePolicy.objects.filter(is_active=True, positions=position)
        .order_by("code")
        .first(),
    )


def get_ot_policy_for_employee(employee, shift=None):
    """
    Resolve OT policy:
    1) Position mapping (optional) — overrides shift
    2) Shift OT policy
    3) Company default
    """
    position = getattr(employee, "position", None) if employee else None
    by_position = get_ot_policy_for_position(position)
    if by_position:
        return by_position
    return get_ot_policy_for_shift(shift)


def get_late_penalty_policy_for_shift(shift):
    """Return the shift's late-penalty policy, or None when unset (no deduction)."""
    if shift and shift.late_penalty_policy_id and shift.late_penalty_policy.is_active:
        return shift.late_penalty_policy
    return None


def special_ot_amount_for_day(
    policy: OvertimePolicy | None,
    *,
    is_weekly_off: bool = False,
    is_holiday: bool = False,
) -> Decimal:
    """Flat special OT per hour applicable for this day context (snapshot)."""
    if not policy or not policy.special_ot_amount:
        return Decimal("0.00")
    amount = Decimal(policy.special_ot_amount)
    if amount <= 0:
        return Decimal("0.00")
    if is_holiday and policy.special_ot_on_holiday:
        return amount.quantize(Decimal("0.01"))
    if is_weekly_off and policy.special_ot_on_weekend:
        return amount.quantize(Decimal("0.01"))
    if not is_holiday and not is_weekly_off and policy.special_ot_on_weekday:
        return amount.quantize(Decimal("0.01"))
    return Decimal("0.00")


def _round_hours(hours: Decimal, policy: OvertimePolicy) -> Decimal:
    q = Decimal("0.01")
    if not policy or not policy.round_minutes:
        return max(Decimal("0.00"), hours).quantize(q)

    step = Decimal(policy.round_minutes) / Decimal("60")
    if step <= 0:
        return max(Decimal("0.00"), hours).quantize(q)

    units = hours / step
    mode = policy.round_mode
    if mode == OvertimePolicy.RoundMode.UP:
        units = units.to_integral_value(rounding=ROUND_CEILING)
    elif mode == OvertimePolicy.RoundMode.DOWN:
        units = units.to_integral_value(rounding=ROUND_FLOOR)
    elif mode == OvertimePolicy.RoundMode.NEAREST:
        units = units.to_integral_value(rounding=ROUND_HALF_UP)
    # NONE with round_minutes still snaps to step via nearest-ish; treat as nearest
    else:
        units = units.to_integral_value(rounding=ROUND_HALF_UP)

    return max(Decimal("0.00"), (units * step).quantize(q))


def calculate_overtime(
    *,
    worked: Decimal,
    expected: Decimal,
    policy: OvertimePolicy | None,
    is_weekly_off: bool = False,
    is_holiday: bool = False,
) -> tuple[Decimal, Decimal, str]:
    """
    Returns (ot_hours, ot_rate, note).
    """
    worked = worked or Decimal("0.00")
    expected = expected or Decimal("0.00")
    q = Decimal("0.01")

    if not policy:
        # Legacy: simple excess over expected
        ot = max(Decimal("0.00"), worked - expected).quantize(q)
        return ot, Decimal("1.50"), "No OT policy — used worked − expected"

    if policy.disable_ot:
        return Decimal("0.00"), Decimal("0.00"), f"{policy.code} · no OT for position"

    note_parts = [policy.code]

    if is_holiday and policy.holiday_all_as_ot:
        raw = worked
        rate = policy.holiday_rate
        note_parts.append("holiday all worked as OT")
    elif is_weekly_off and policy.weekly_off_all_as_ot:
        raw = worked
        rate = policy.weekend_rate
        note_parts.append("weekly off all worked as OT")
    else:
        grace = Decimal(policy.grace_minutes) / Decimal("60")
        if policy.ot_basis == OvertimePolicy.OtBasis.FIXED_HOURS:
            base = Decimal(policy.ot_base_hours or 0)
            raw = worked - base - grace
            note_parts.append(f"fixed {base}h")
        else:
            # Default: after shift expected hours (shift end)
            raw = worked - expected - grace
            note_parts.append("after shift")
        if raw < 0:
            raw = Decimal("0.00")
        rate = policy.weekday_rate
        if policy.grace_minutes:
            note_parts.append(f"grace {policy.grace_minutes}m")

    ot = _round_hours(raw, policy)

    if policy.max_hours_per_day is not None:
        cap = policy.max_hours_per_day
        if ot > cap:
            ot = cap.quantize(q)
            note_parts.append(f"capped at {cap}h")

    return ot.quantize(q), rate.quantize(q), " · ".join(note_parts)


def apply_late_penalty(
    *,
    worked: Decimal,
    late_minutes: int,
    policy: LatePenaltyPolicy | None,
) -> tuple[Decimal, int]:
    """
    Reduce payable hours by policy tiers.
    Returns (payable_hours, penalty_minutes).
    """
    q = Decimal("0.01")
    worked = max(Decimal("0.00"), worked or Decimal("0.00"))
    if not policy or late_minutes <= 0:
        return worked.quantize(q), 0

    penalty = int(policy.deduct_minutes_for(late_minutes))
    if penalty <= 0:
        return worked.quantize(q), 0

    deduct_hours = (Decimal(penalty) / Decimal("60")).quantize(q)
    payable = max(Decimal("0.00"), worked - deduct_hours).quantize(q)
    return payable, penalty


def seed_default_ot_policy():
    OvertimePolicy.objects.get_or_create(
        code="STD",
        defaults={
            "name": "Standard OT",
            "description": "Weekday 1.5x after shift; weekend/holiday all worked hours at 2x",
            "is_default": True,
            "is_active": True,
            "disable_ot": False,
            "ot_basis": OvertimePolicy.OtBasis.AFTER_SHIFT,
            "ot_base_hours": Decimal("8.00"),
            "grace_minutes": 15,
            "round_minutes": 15,
            "round_mode": OvertimePolicy.RoundMode.NEAREST,
            "max_hours_per_day": Decimal("4.00"),
            "weekday_rate": Decimal("1.50"),
            "weekend_rate": Decimal("2.00"),
            "holiday_rate": Decimal("2.00"),
            "weekly_off_all_as_ot": True,
            "holiday_all_as_ot": True,
            "hourly_divisor": 240,
            "special_ot_amount": Decimal("0.00"),
            "special_ot_on_weekday": False,
            "special_ot_on_weekend": False,
            "special_ot_on_holiday": False,
        },
    )
    OvertimePolicy.objects.get_or_create(
        code="NO-OT",
        defaults={
            "name": "No overtime",
            "description": "Map office / salaried positions here — OT hours stay 0",
            "is_default": False,
            "is_active": True,
            "disable_ot": True,
            "ot_basis": OvertimePolicy.OtBasis.AFTER_SHIFT,
            "ot_base_hours": Decimal("8.00"),
            "grace_minutes": 0,
            "round_minutes": 0,
            "round_mode": OvertimePolicy.RoundMode.NONE,
            "max_hours_per_day": Decimal("0.00"),
            "weekday_rate": Decimal("0.00"),
            "weekend_rate": Decimal("0.00"),
            "holiday_rate": Decimal("0.00"),
            "weekly_off_all_as_ot": False,
            "holiday_all_as_ot": False,
            "hourly_divisor": 240,
            "special_ot_amount": Decimal("0.00"),
            "special_ot_on_weekday": False,
            "special_ot_on_weekend": False,
            "special_ot_on_holiday": False,
        },
    )


def seed_company_ot_policies():
    """
    Company-style OT policies from OVERTIME.xlsx (idempotent).
    Does not change which policy is default — STD remains default for demo.
    """
    specs = (
        {
            "code": "WRK-DAY",
            "name": "Workers — Day shift OT",
            "description": "After shift end · Basic/240 × 1.0; weekend/holiday × 1.25 + AED 1",
            "ot_basis": OvertimePolicy.OtBasis.AFTER_SHIFT,
            "ot_base_hours": Decimal("8.00"),
            "weekday_rate": Decimal("1.00"),
            "weekend_rate": Decimal("1.25"),
            "holiday_rate": Decimal("1.25"),
            "special_ot_amount": Decimal("1.00"),
            "special_ot_on_weekday": False,
            "special_ot_on_weekend": True,
            "special_ot_on_holiday": True,
            "is_default": False,
        },
        {
            "code": "WRK-NIGHT",
            "name": "Workers — Night shift OT",
            "description": "After shift end · Basic/240 × 1.25; weekend/holiday × 1.25 + AED 1",
            "ot_basis": OvertimePolicy.OtBasis.AFTER_SHIFT,
            "ot_base_hours": Decimal("8.00"),
            "weekday_rate": Decimal("1.25"),
            "weekend_rate": Decimal("1.25"),
            "holiday_rate": Decimal("1.25"),
            "special_ot_amount": Decimal("1.00"),
            "special_ot_on_weekday": False,
            "special_ot_on_weekend": True,
            "special_ot_on_holiday": True,
            "is_default": False,
        },
        {
            "code": "OFFICE",
            "name": "Office / Driver OT",
            "description": "After shift end · Basic/240 × 1.0; weekend/holiday × 1.25",
            "ot_basis": OvertimePolicy.OtBasis.AFTER_SHIFT,
            "ot_base_hours": Decimal("8.00"),
            "weekday_rate": Decimal("1.00"),
            "weekend_rate": Decimal("1.25"),
            "holiday_rate": Decimal("1.25"),
            "special_ot_amount": Decimal("0.00"),
            "special_ot_on_weekday": False,
            "special_ot_on_weekend": False,
            "special_ot_on_holiday": False,
            "is_default": False,
        },
        {
            "code": "FIXED-8",
            "name": "OT after 8 hours worked",
            "description": "Weekday OT = worked − 8 hours (attendance-sheet style)",
            "ot_basis": OvertimePolicy.OtBasis.FIXED_HOURS,
            "ot_base_hours": Decimal("8.00"),
            "weekday_rate": Decimal("1.00"),
            "weekend_rate": Decimal("1.25"),
            "holiday_rate": Decimal("1.25"),
            "special_ot_amount": Decimal("0.00"),
            "special_ot_on_weekday": False,
            "special_ot_on_weekend": False,
            "special_ot_on_holiday": False,
            "is_default": False,
        },
    )
    for spec in specs:
        OvertimePolicy.objects.get_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "description": spec["description"],
                "is_default": spec["is_default"],
                "is_active": True,
                "ot_basis": spec["ot_basis"],
                "ot_base_hours": spec["ot_base_hours"],
                "grace_minutes": 0,
                "round_minutes": 0,
                "round_mode": OvertimePolicy.RoundMode.NONE,
                "max_hours_per_day": None,
                "weekday_rate": spec["weekday_rate"],
                "weekend_rate": spec["weekend_rate"],
                "holiday_rate": spec["holiday_rate"],
                "weekly_off_all_as_ot": True,
                "holiday_all_as_ot": True,
                "hourly_divisor": 240,
                "special_ot_amount": spec["special_ot_amount"],
                "special_ot_on_weekday": spec["special_ot_on_weekday"],
                "special_ot_on_weekend": spec["special_ot_on_weekend"],
                "special_ot_on_holiday": spec["special_ot_on_holiday"],
            },
        )


def seed_default_late_penalty_policy():
    """≤5 min late → −15 min; otherwise −4 hours (240 min)."""
    # Create-only: never overwrite tiers HR has edited (this runs on every migrate)
    policy, _ = LatePenaltyPolicy.objects.get_or_create(
        code="STD-LATE",
        defaults={
            "name": "Standard late punch",
            "description": "≤5 min → deduct 15 min; more than 5 min → deduct 4 hours",
            "is_default": True,
            "is_active": True,
        },
    )
    if LatePenaltyTier.objects.filter(policy=policy).exists():
        return policy
    LatePenaltyTier.objects.bulk_create(
        [
            LatePenaltyTier(
                policy=policy,
                max_late_minutes=5,
                deduct_minutes=15,
                sort_order=1,
            ),
            LatePenaltyTier(
                policy=policy,
                max_late_minutes=24 * 60,
                deduct_minutes=240,
                sort_order=2,
            ),
        ]
    )
    return policy


def seed_overtime_sheet_rules(*, include_std_policy: bool = True) -> dict:
    """
    Full OVERTIME.xlsx-style setup (idempotent):

    - OT policies: WRK-DAY, WRK-NIGHT, OFFICE, FIXED-8 (+ optional STD)
    - Late penalty: ≤5 min → 15 min; else → 4 hours
    - Calendar: UAE-STD (Sun weekly off)
    - Shifts linked to policies:
        DAY   07:00–15:30 + 30m break → WRK-DAY + late
        NIGHT 19:00–03:30 + 30m break → WRK-NIGHT + late
        OFFICE / GEN / DRIVER 09:00–17:30 + 30m break → OFFICE + late

    Run:
        python manage.py seed --only ot_rules
    """
    from datetime import date, time as dtime

    from django.utils import timezone

    from attendance.models import WorkCalendar, WorkShift, WorkShiftVersion

    if include_std_policy:
        seed_default_ot_policy()
    seed_company_ot_policies()
    late_policy = seed_default_late_penalty_policy()

    ot_by_code = {
        p.code: p
        for p in OvertimePolicy.objects.filter(
            code__in=["WRK-DAY", "WRK-NIGHT", "OFFICE", "FIXED-8", "STD"]
        )
    }

    # Create-only: re-running must not undo HR's calendar / shift edits
    calendar, _ = WorkCalendar.objects.get_or_create(
        code="UAE-STD",
        defaults={
            "name": "UAE Standard (Mon–Sat / Sun off)",
            "description": "Sunday weekly off (matches attendance sheet TYP=W on Sun)",
            "monday": True,
            "tuesday": True,
            "wednesday": True,
            "thursday": True,
            "friday": True,
            "saturday": True,
            "sunday": False,
            "is_active": True,
        },
    )

    year_start = date(timezone.localdate().year, 1, 1)
    shift_specs = (
        {
            "code": "DAY",
            "name": "Workers Day (07:00–15:30)",
            "ot": "WRK-DAY",
            "late": True,
            "from": dtime(7, 0),
            "to": dtime(15, 30),
            "day_span": False,
            "break_from": dtime(12, 0),
            "break_to": dtime(12, 30),
            "notes": "OVERTIME.xlsx workers day — OT after 15:30 @ Basic/240",
        },
        {
            "code": "NIGHT",
            "name": "Workers Night (19:00–03:30)",
            "ot": "WRK-NIGHT",
            "late": True,
            "from": dtime(19, 0),
            "to": dtime(3, 30),
            "day_span": True,
            "break_from": dtime(23, 0),
            "break_to": dtime(23, 30),
            "notes": "OVERTIME.xlsx workers night — OT after 03:30 @ 1.25×",
        },
        {
            "code": "OFFICE",
            "name": "Office Staff (09:00–17:30)",
            "ot": "OFFICE",
            "late": True,
            "from": dtime(9, 0),
            "to": dtime(17, 30),
            "day_span": False,
            "break_from": dtime(13, 0),
            "break_to": dtime(13, 30),
            "notes": "OVERTIME.xlsx office — OT after shift end @ Basic/240",
        },
        {
            "code": "DRIVER",
            "name": "Driver (09:00–17:30)",
            "ot": "OFFICE",
            "late": True,
            "from": dtime(9, 0),
            "to": dtime(17, 30),
            "day_span": False,
            "break_from": dtime(13, 0),
            "break_to": dtime(13, 30),
            "notes": "OVERTIME.xlsx driver — same OT as office",
        },
        {
            "code": "GEN",
            "name": "General / Office (09:00–17:30)",
            "ot": "OFFICE",
            "late": True,
            "from": dtime(9, 0),
            "to": dtime(17, 30),
            "day_span": False,
            "break_from": dtime(13, 0),
            "break_to": dtime(13, 30),
            "notes": "Default office-style shift for assignments",
        },
        {
            "code": "REG-8",
            "name": "Regular fixed-8 OT (09:00–17:30)",
            "ot": "FIXED-8",
            "late": True,
            "from": dtime(9, 0),
            "to": dtime(17, 30),
            "day_span": False,
            "break_from": dtime(13, 0),
            "break_to": dtime(13, 30),
            "notes": "Attendance-sheet style: OT = worked − 8 hours",
        },
    )

    shifts_created = 0
    for spec in shift_specs:
        ot_pol = ot_by_code.get(spec["ot"])
        shift, created = WorkShift.objects.get_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "is_active": True,
                "ot_policy": ot_pol,
                "late_penalty_policy": late_policy if spec["late"] else None,
            },
        )
        if created:
            shifts_created += 1
        if WorkShiftVersion.objects.filter(shift=shift).exists():
            continue  # keep the times HR has set
        version = WorkShiftVersion(
            shift=shift,
            effective_from=year_start,
            shift_from=spec["from"],
            shift_to=spec["to"],
            day_span=spec["day_span"],
            break_from=spec["break_from"],
            break_to=spec["break_to"],
            notes=spec["notes"],
        )
        version.recalculate_hours()
        version.save()

    return {
        "ot_policies": OvertimePolicy.objects.filter(
            code__in=["WRK-DAY", "WRK-NIGHT", "OFFICE", "FIXED-8", "STD"]
        ).count(),
        "late_penalty_policies": LatePenaltyPolicy.objects.filter(code="STD-LATE").count(),
        "late_penalty_tiers": late_policy.tiers.count(),
        "ot_calendar": calendar.code,
        "ot_shifts": WorkShift.objects.filter(
            code__in=[s["code"] for s in shift_specs]
        ).count(),
        "ot_shifts_created": shifts_created,
    }
