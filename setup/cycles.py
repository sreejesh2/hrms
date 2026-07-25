"""
Company attendance / payroll cycles.

cycle_start_day = 1  → calendar month (1st → last day)
cycle_start_day = 25 → labeled "August" means 25 Jul → 24 Aug
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def get_cycle_start_day() -> int:
    try:
        from setup.models import OrganizationSettings

        day = int(OrganizationSettings.load().cycle_start_day or 1)
    except Exception:
        day = 1
    return max(1, min(day, 28))


def period_bounds(
    year: int, month: int, start_day: int | None = None
) -> tuple[date, date]:
    """
    Date range for the labeled pay/attendance period (year, month).

    Example with start_day=25, month=August 2026:
      start=2026-07-25, end=2026-08-24
    """
    if month < 1 or month > 12:
        raise ValueError("Month must be 1–12.")
    start_day = get_cycle_start_day() if start_day is None else max(1, min(int(start_day), 28))

    if start_day == 1:
        last = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last)

    end = date(year, month, start_day - 1)
    if month == 1:
        start = date(year - 1, 12, start_day)
    else:
        start = date(year, month - 1, start_day)
    return start, end


def period_for_date(
    on_date: date, start_day: int | None = None
) -> tuple[int, int, date, date]:
    """Return (label_year, label_month, start, end) containing on_date."""
    start_day = get_cycle_start_day() if start_day is None else max(1, min(int(start_day), 28))
    if start_day == 1:
        start, end = period_bounds(on_date.year, on_date.month, 1)
        return on_date.year, on_date.month, start, end

    if on_date.day >= start_day:
        if on_date.month == 12:
            y, m = on_date.year + 1, 1
        else:
            y, m = on_date.year, on_date.month + 1
    else:
        y, m = on_date.year, on_date.month
    start, end = period_bounds(y, m, start_day)
    return y, m, start, end


def period_label(year: int, month: int, start: date | None = None, end: date | None = None) -> str:
    name = f"{calendar.month_name[month]} {year}"
    if start and end and (start.month != month or end.month != month or start.day != 1):
        return f"{name} ({start.strftime('%d %b')} → {end.strftime('%d %b %Y')})"
    return name


def cycle_dates(start: date, end: date) -> list[date]:
    days = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def cycle_help_text(start_day: int | None = None) -> str:
    start_day = get_cycle_start_day() if start_day is None else start_day
    if start_day <= 1:
        return "Calendar months (1st → last day)."
    end_day = start_day - 1
    return (
        f"Each period runs from the {start_day}th of one month "
        f"through the {end_day}th of the next "
        f"(e.g. August = {start_day} Jul → {end_day} Aug)."
    )
