"""
UAE end-of-service gratuity (Federal Decree-Law No. 33 of 2021, Art. 51).

Uses Basic wage from the employee salary structure.
- First 5 years: 21 days' wage per year
- After 5 years: 30 days' wage per year
- Cap: 2 years' wage
- Pro-rata for partial years; requires ≥ 1 year continuous service for entitlement
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .currencies import format_money
from .services import structure_on

ZERO = Decimal("0.00")
DAYS_PER_MONTH = Decimal("30")
FIRST_BAND_YEARS = Decimal("5")
DAYS_FIRST_BAND = Decimal("21")
DAYS_AFTER_BAND = Decimal("30")
CAP_YEARS_WAGE = Decimal("2")


@dataclass
class GratuityEstimate:
    employee_id: int
    as_of: date
    join_date: date | None
    years_of_service: Decimal
    basic_monthly: Decimal
    daily_wage: Decimal
    currency: str
    amount: Decimal
    capped: bool
    eligible: bool
    notes: str

    @property
    def amount_fmt(self) -> str:
        return format_money(self.amount, self.currency)

    @property
    def basic_fmt(self) -> str:
        return format_money(self.basic_monthly, self.currency)


def _years_between(start: date, end: date) -> Decimal:
    if end < start:
        return ZERO
    days = (end - start).days
    return (Decimal(days) / Decimal("365.25")).quantize(Decimal("0.0001"))


def estimate_gratuity(
    employee, *, as_of: date | None = None, structure=None
) -> GratuityEstimate:
    """
    Accrued EOS gratuity estimate as of a date (default: today).
    Not a payslip line — for HR visibility / settlement preview.
    Pass `structure` to avoid a per-employee query on list pages.
    """
    as_of = as_of or timezone.localdate()
    join = getattr(employee, "date_of_joining", None)
    if structure is None:
        structure = structure_on(employee, as_of)
    basic = structure.basic_amount() if structure else ZERO
    currency = (structure.currency if structure else None) or "AED"
    daily = (basic / DAYS_PER_MONTH).quantize(Decimal("0.0001")) if basic else ZERO

    if not join:
        return GratuityEstimate(
            employee_id=employee.pk,
            as_of=as_of,
            join_date=None,
            years_of_service=ZERO,
            basic_monthly=basic,
            daily_wage=daily,
            currency=currency,
            amount=ZERO,
            capped=False,
            eligible=False,
            notes="Set date of joining on the employee profile to estimate gratuity.",
        )

    years = _years_between(join, as_of)
    if years < Decimal("1"):
        return GratuityEstimate(
            employee_id=employee.pk,
            as_of=as_of,
            join_date=join,
            years_of_service=years,
            basic_monthly=basic,
            daily_wage=daily,
            currency=currency,
            amount=ZERO,
            capped=False,
            eligible=False,
            notes="Gratuity typically accrues after completing one year of continuous service.",
        )

    if basic <= 0:
        return GratuityEstimate(
            employee_id=employee.pk,
            as_of=as_of,
            join_date=join,
            years_of_service=years,
            basic_monthly=basic,
            daily_wage=daily,
            currency=currency,
            amount=ZERO,
            capped=False,
            eligible=False,
            notes="No Basic salary on the structure effective for this date.",
        )

    first = min(years, FIRST_BAND_YEARS)
    rest = max(years - FIRST_BAND_YEARS, ZERO)
    raw = (first * DAYS_FIRST_BAND * daily) + (rest * DAYS_AFTER_BAND * daily)
    raw = raw.quantize(Decimal("0.01"))
    cap = (basic * CAP_YEARS_WAGE).quantize(Decimal("0.01"))
    capped = raw > cap
    amount = min(raw, cap)

    return GratuityEstimate(
        employee_id=employee.pk,
        as_of=as_of,
        join_date=join,
        years_of_service=years.quantize(Decimal("0.01")),
        basic_monthly=basic,
        daily_wage=daily.quantize(Decimal("0.01")),
        currency=currency,
        amount=amount,
        capped=capped,
        eligible=True,
        notes=(
            "UAE EOS: 21 days/year for first 5 years, then 30 days/year; "
            "capped at 2 years’ wage. Based on Basic. Confirm with legal counsel for edge cases."
        ),
    )
