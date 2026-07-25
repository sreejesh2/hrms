"""Overtime calculation from worked hours + shift/day context + OT policy."""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from .models import OvertimePolicy


def get_ot_policy_for_shift(shift):
    if shift and shift.ot_policy_id and shift.ot_policy.is_active:
        return shift.ot_policy
    return (
        OvertimePolicy.objects.filter(is_default=True, is_active=True).first()
        or OvertimePolicy.objects.filter(is_active=True).order_by("code").first()
    )


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
        raw = worked - expected - grace
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


def seed_default_ot_policy():
    OvertimePolicy.objects.update_or_create(
        code="STD",
        defaults={
            "name": "Standard OT",
            "description": "Weekday 1.5x after shift; weekend/holiday all worked hours at 2x",
            "is_default": True,
            "is_active": True,
            "grace_minutes": 15,
            "round_minutes": 15,
            "round_mode": OvertimePolicy.RoundMode.NEAREST,
            "max_hours_per_day": Decimal("4.00"),
            "weekday_rate": Decimal("1.50"),
            "weekend_rate": Decimal("2.00"),
            "holiday_rate": Decimal("2.00"),
            "weekly_off_all_as_ot": True,
            "holiday_all_as_ot": True,
        },
    )
