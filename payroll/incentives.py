"""Incentive / bonus plans and award helpers."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import QuerySet
from django.utils import timezone

from .models import IncentiveAward, IncentivePlan, SalaryComponent


def seed_default_incentive_components() -> None:
    """Ensure BONUS / INCENTIVE earning heads exist for plans."""
    specs = [
        ("BONUS", "Bonus", 50),
        ("INCENTIVE", "Incentive", 55),
    ]
    for code, name, order in specs:
        SalaryComponent.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "kind": SalaryComponent.Kind.EARNING,
                "calc_method": SalaryComponent.CalcMethod.FIXED,
                "is_basic": False,
                "is_taxable": True,
                "affects_ot_base": False,
                "sort_order": order,
                "is_active": True,
            },
        )


def seed_default_incentive_plans() -> None:
    seed_default_incentive_components()
    bonus = SalaryComponent.objects.filter(code="BONUS").first()
    incentive = SalaryComponent.objects.filter(code="INCENTIVE").first()
    if not bonus or not incentive:
        return
    specs = [
        ("SPOT", "Spot bonus", bonus, IncentivePlan.Frequency.ONE_TIME),
        ("QTR-BONUS", "Quarterly bonus", bonus, IncentivePlan.Frequency.QUARTERLY),
        (
            "SALES-INCENTIVE",
            "Sales incentive",
            incentive,
            IncentivePlan.Frequency.MONTHLY,
        ),
    ]
    for code, name, component, frequency in specs:
        IncentivePlan.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "component": component,
                "frequency": frequency,
                "is_active": True,
            },
        )


def approved_awards_for_employee(
    *, period_id: int, employee_id: int
) -> QuerySet[IncentiveAward]:
    return (
        IncentiveAward.objects.filter(
            period_id=period_id,
            employee_id=employee_id,
            status=IncentiveAward.Status.APPROVED,
            amount__gt=0,
        )
        .select_related("plan", "plan__component")
        .order_by("plan__code", "pk")
    )


def count_pending_awards(period_id: int) -> int:
    return IncentiveAward.objects.filter(
        period_id=period_id,
        status=IncentiveAward.Status.APPROVED,
        amount__gt=0,
    ).count()


def approve_award(award: IncentiveAward, *, user=None) -> IncentiveAward:
    if award.status != IncentiveAward.Status.DRAFT:
        raise ValueError("Only draft awards can be approved.")
    if award.period.is_locked:
        raise ValueError("Cannot approve awards for a locked payroll period.")
    if award.amount <= 0:
        raise ValueError("Award amount must be greater than zero.")
    award.status = IncentiveAward.Status.APPROVED
    award.approved_by = user
    award.approved_at = timezone.now()
    award.save(
        update_fields=["status", "approved_by", "approved_at", "updated_at"]
    )
    return award


def cancel_award(award: IncentiveAward) -> IncentiveAward:
    if award.status == IncentiveAward.Status.PAID:
        raise ValueError("Paid awards cannot be cancelled.")
    if award.status == IncentiveAward.Status.CANCELLED:
        return award
    award.status = IncentiveAward.Status.CANCELLED
    award.payslip_line = None
    award.save(update_fields=["status", "payslip_line", "updated_at"])
    return award


def mark_awards_paid(period) -> int:
    """After lock: mark approved awards paid and link payslip lines."""
    from .models import PayslipLine

    awards = list(
        IncentiveAward.objects.filter(
            period=period,
            status=IncentiveAward.Status.APPROVED,
        ).select_related("employee")
    )
    if not awards:
        return 0

    lines_by_code = {
        line.code: line
        for line in PayslipLine.objects.filter(
            payslip__period=period,
            code__startswith="INC_",
        )
    }
    now = timezone.now()
    updated = 0
    for award in awards:
        line = lines_by_code.get(award.slip_code)
        award.status = IncentiveAward.Status.PAID
        award.payslip_line = line
        if award.approved_at is None:
            award.approved_at = now
        award.save(
            update_fields=["status", "payslip_line", "approved_at", "updated_at"]
        )
        updated += 1
    return updated


def parse_award_csv_rows(rows: list[dict], *, user=None) -> tuple[int, list[str]]:
    """
    Create draft awards from CSV-like dicts.
    Expected keys: employee_code, plan_code, amount, period_year, period_month
    Optional: notes, currency
    """
    from people.models import Employee

    from .currencies import default_currency_code
    from .models import PayrollPeriod

    created = 0
    errors: list[str] = []
    default_cur = default_currency_code()

    for i, row in enumerate(rows, start=2):
        try:
            emp_code = (row.get("employee_code") or "").strip()
            plan_code = (row.get("plan_code") or "").strip()
            amount = Decimal(str(row.get("amount") or "0").strip() or "0")
            year = int(str(row.get("period_year") or "").strip())
            month = int(str(row.get("period_month") or "").strip())
            notes = (row.get("notes") or "").strip()[:255]
            currency = (row.get("currency") or default_cur).strip() or default_cur

            if amount <= 0:
                raise ValueError("amount must be > 0")
            employee = Employee.objects.get(employee_code__iexact=emp_code)
            plan = IncentivePlan.objects.get(code__iexact=plan_code, is_active=True)
            period = PayrollPeriod.objects.get(year=year, month=month)
            if period.is_locked:
                raise ValueError(f"period {year}-{month:02d} is locked")

            existing = IncentiveAward.objects.filter(
                employee=employee,
                plan=plan,
                period=period,
                status__in=[
                    IncentiveAward.Status.DRAFT,
                    IncentiveAward.Status.APPROVED,
                ],
            ).first()
            if existing:
                raise ValueError(
                    f"open award already exists for {emp_code} / {plan_code} / {year}-{month:02d}"
                )

            IncentiveAward.objects.create(
                plan=plan,
                employee=employee,
                period=period,
                amount=amount.quantize(Decimal("0.01")),
                currency=currency,
                status=IncentiveAward.Status.DRAFT,
                notes=notes,
                created_by=user,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Row {i}: {exc}")
    return created, errors
