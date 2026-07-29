"""Monthly payroll run — structures + LWP + OT → payslips."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from attendance.models import DailyAttendance
from people.models import Employee

from .currencies import default_currency_code
from .models import PayrollPeriod, Payslip, PayslipLine, SalaryComponent
from .services import structure_on

ZERO = Decimal("0.00")
HOURS_PER_DAY = Decimal("8")


def _reimbursement_total(employee) -> tuple[Decimal, list[int]]:
    """Sum approved (unpaid) expense claims to pay via payroll."""
    from expenses.models import ExpenseClaim

    claims = list(
        ExpenseClaim.objects.filter(
            employee=employee,
            status=ExpenseClaim.Status.APPROVED,
        ).only("pk", "total_amount")
    )
    if not claims:
        return ZERO, []
    total = sum((c.total_amount for c in claims), ZERO).quantize(Decimal("0.01"))
    return total, [c.pk for c in claims]


def _advance_deduction(employee) -> tuple[Decimal, list[tuple[int, Decimal]]]:
    """Salary advance recoveries for this payroll run."""
    from loans.services import deduction_plan_for_employee

    return deduction_plan_for_employee(employee)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Bounds for a labeled payroll/attendance period (respects company cycle)."""
    from setup.cycles import period_bounds

    return period_bounds(year, month)


@transaction.atomic
def create_period(*, year: int, month: int, created_by=None, notes="", currency=None):
    if month < 1 or month > 12:
        raise ValueError("Month must be 1–12.")
    if PayrollPeriod.objects.filter(year=year, month=month).exists():
        raise ValueError(f"Period {year}-{month:02d} already exists.")
    start, end = month_bounds(year, month)
    return PayrollPeriod.objects.create(
        year=year,
        month=month,
        start_date=start,
        end_date=end,
        currency=currency or default_currency_code(),
        notes=notes or "",
        created_by=created_by,
        status=PayrollPeriod.Status.DRAFT,
    )


def _unpaid_days(employee, start: date, end: date) -> Decimal:
    """
    Unpaid days for LWP proration:
    - Absent = 1
    - Half day = 0.5
    - Short payable hours (late penalty) as day-fractions on present days
    - Approved unpaid leave (LeaveType.is_paid=False) overlapping the period
      (count calendar days in range; half-day requests = 0.5)
    Avoid double-counting the same date (attendance absent + leave).
    """
    unpaid_dates: dict[date, Decimal] = {}

    rows = DailyAttendance.objects.filter(
        employee=employee, date__gte=start, date__lte=end
    ).values_list("date", "status")
    for d, status in rows:
        if status in (
            DailyAttendance.Status.ABSENT,
            DailyAttendance.Status.MISSING_PUNCH,
        ):
            unpaid_dates[d] = Decimal("1.00")
        elif status == DailyAttendance.Status.HALF_DAY:
            unpaid_dates[d] = max(unpaid_dates.get(d, ZERO), Decimal("0.50"))

    try:
        from leave.models import LeaveRequest

        leave_qs = LeaveRequest.objects.filter(
            employee=employee,
            status=LeaveRequest.Status.APPROVED,
            leave_type__is_paid=False,
            start_date__lte=end,
            end_date__gte=start,
        ).select_related("leave_type")
        for req in leave_qs:
            cur = max(req.start_date, start)
            last = min(req.end_date, end)
            while cur <= last:
                if req.is_half_day:
                    unpaid_dates[cur] = max(unpaid_dates.get(cur, ZERO), Decimal("0.50"))
                else:
                    unpaid_dates[cur] = Decimal("1.00")
                cur += timedelta(days=1)
    except Exception:
        # leave app optional during migrate edge cases
        pass

    total = sum(unpaid_dates.values(), ZERO)
    # Late / short-hour fractions on top of status-based unpaid days
    total += _short_hour_unpaid(employee, start, end)
    return total.quantize(Decimal("0.01"))


def _apply_statutory_rules(*, lines, earnings, deductions, basic, gross_for_rules):
    """Append active statutory rules; return updated earnings, deductions."""
    from .models import PayslipLine
    from .statutory import active_payroll_rules

    for rule in active_payroll_rules():
        amt = rule.compute(basic=basic, gross=gross_for_rules)
        if amt <= 0:
            continue
        kind = (
            PayslipLine.Kind.EARNING
            if rule.kind == rule.Kind.EARNING
            else PayslipLine.Kind.DEDUCTION
        )
        lines.append(
            {
                "component": None,
                "code": f"STAT_{rule.code}",
                "name": rule.name,
                "kind": kind,
                "amount": amt,
                "sort_order": rule.sort_order,
            }
        )
        if kind == PayslipLine.Kind.EARNING:
            earnings += amt
        else:
            deductions += amt
    return earnings, deductions


def _apply_incentive_awards(*, lines, earnings, period, employee, award_ids: list):
    """Append approved unpaid awards as earnings; collect ids for notes."""
    from .incentives import approved_awards_for_employee
    from .models import PayslipLine

    for award in approved_awards_for_employee(
        period_id=period.pk, employee_id=employee.pk
    ):
        amt = Decimal(award.amount or 0).quantize(Decimal("0.01"))
        if amt <= 0:
            continue
        component = award.plan.component
        lines.append(
            {
                "component": component,
                "code": award.slip_code,
                "name": f"{award.plan.name} ({component.code})",
                "kind": PayslipLine.Kind.EARNING,
                "amount": amt,
                "sort_order": getattr(component, "sort_order", 50) or 50,
            }
        )
        earnings += amt
        award_ids.append(award.pk)
    return earnings


def _ot_totals(employee, start: date, end: date) -> tuple[Decimal, list, Decimal]:
    """
    Return (ot_hours_sum, list of (hours, rate, divisor), special_ot_total).
    special_ot_total = sum(hours × special_ot_amount) from daily snapshots.
    """
    rows = DailyAttendance.objects.filter(
        employee=employee,
        date__gte=start,
        date__lte=end,
        overtime_hours__gt=0,
    ).values_list("overtime_hours", "ot_rate", "hourly_divisor", "special_ot_amount")
    pairs = []
    hours = ZERO
    special_total = ZERO
    for h, rate, divisor, special in rows:
        h = Decimal(h or 0)
        rate = Decimal(rate or 1)
        divisor = int(divisor or 240)
        special = Decimal(special or 0)
        hours += h
        pairs.append((h, rate, divisor))
        if special > 0 and h > 0:
            special_total += (h * special).quantize(Decimal("0.01"))
    return hours.quantize(Decimal("0.01")), pairs, special_total.quantize(Decimal("0.01"))


def _compute_ot_amount(basic: Decimal, pairs: list, calendar_days: int) -> Decimal:
    """
    OT pay using per-day hourly divisor when present.
    Formula: (basic / divisor) × hours × rate.
    Fallback when no divisor on a row: basic / calendar_days / 8.
    """
    if basic <= 0 or not pairs:
        return ZERO
    days = Decimal(calendar_days or 30)
    legacy_hourly = (basic / days / HOURS_PER_DAY).quantize(Decimal("0.0001"))
    total = ZERO
    for row in pairs:
        if len(row) == 3:
            hours, rate, divisor = row
        else:
            hours, rate = row
            divisor = 0
        if divisor and divisor > 0:
            hourly = (basic / Decimal(divisor)).quantize(Decimal("0.0001"))
        else:
            hourly = legacy_hourly
        total += (hours * rate * hourly).quantize(Decimal("0.01"))
    return total.quantize(Decimal("0.01"))


def _short_hour_unpaid(employee, start: date, end: date) -> Decimal:
    """
    Extra unpaid day-fractions from short payable hours on present days
    (late penalty and/or break overrun already baked into payable_hours).
    Half-day / absent are already counted via status.
    """
    rows = DailyAttendance.objects.filter(
        employee=employee,
        date__gte=start,
        date__lte=end,
        status=DailyAttendance.Status.PRESENT,
    ).values_list("expected_hours", "payable_hours")
    extra = ZERO
    for expected, payable in rows:
        expected = Decimal(expected or 0)
        payable = Decimal(payable or 0)
        if expected <= 0:
            continue
        short = expected - payable
        if short <= 0:
            continue
        fraction = (short / expected).quantize(Decimal("0.0001"))
        extra += min(fraction, Decimal("1.00"))
    return extra.quantize(Decimal("0.01"))


@transaction.atomic
def run_period(period: PayrollPeriod, *, user=None) -> dict:
    """
    Calculate / recalculate all payslips for active employees with a salary structure.
    Locked periods cannot be re-run.
    """
    if period.is_locked:
        raise ValueError("Period is locked. Unlock is not allowed — create notes only.")

    employees = (
        Employee.objects.filter(
            status__in=[Employee.Status.ACTIVE, Employee.Status.ON_LEAVE]
        )
        .order_by("employee_code")
    )

    created = updated = skipped = 0
    errors = []

    # Drop existing draft slips when recalculating
    period.payslips.all().delete()

    for emp in employees:
        structure = structure_on(emp, period.end_date)
        if not structure:
            skipped += 1
            continue
        try:
            _build_payslip(period, emp, structure)
            created += 1
        except Exception as exc:  # noqa: BLE001 — collect per-employee errors
            errors.append(f"{emp.employee_code}: {exc}")

    period.status = PayrollPeriod.Status.CALCULATED
    period.calculated_at = timezone.now()
    period.save(update_fields=["status", "calculated_at", "updated_at"])

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def _build_payslip(period: PayrollPeriod, employee, structure) -> Payslip:
    calendar_days = period.days_in_period
    unpaid = _unpaid_days(employee, period.start_date, period.end_date)
    unpaid = min(unpaid, Decimal(calendar_days))
    paid_days = (Decimal(calendar_days) - unpaid).quantize(Decimal("0.01"))

    resolved = structure.resolved_lines()
    basic = structure.basic_amount()

    ot_hours, ot_pairs, special_ot_total = _ot_totals(
        employee, period.start_date, period.end_date
    )
    ot_amount = _compute_ot_amount(basic, ot_pairs, calendar_days)

    # Prorate structure earnings/deductions by paid days
    factor = (
        (paid_days / Decimal(calendar_days)).quantize(Decimal("0.0001"))
        if calendar_days
        else ZERO
    )

    lines = []
    earnings = ZERO
    deductions = ZERO

    paid_by_code: dict[str, Decimal] = {}
    for row in resolved:
        c = row["component"]
        full = Decimal(row["amount"])
        if getattr(c, "prorate_with_attendance", True):
            amt = (full * factor).quantize(Decimal("0.01"))
        else:
            amt = full.quantize(Decimal("0.01"))
        if amt == 0 and full == 0:
            continue
        kind = (
            PayslipLine.Kind.EARNING
            if c.kind == SalaryComponent.Kind.EARNING
            else PayslipLine.Kind.DEDUCTION
        )
        lines.append(
            {
                "component": c,
                "code": c.code,
                "name": c.name,
                "kind": kind,
                "amount": amt,
                "sort_order": c.sort_order,
            }
        )
        paid_by_code[c.code] = amt
        if kind == PayslipLine.Kind.EARNING:
            earnings += amt
        else:
            deductions += amt

    if ot_amount > 0:
        lines.append(
            {
                "component": None,
                "code": "OT",
                "name": "Overtime",
                "kind": PayslipLine.Kind.EARNING,
                "amount": ot_amount,
                "sort_order": 90,
            }
        )
        earnings += ot_amount

    if special_ot_total > 0:
        lines.append(
            {
                "component": None,
                "code": "SPECIAL_OT",
                "name": "Extra OT Amt",
                "kind": PayslipLine.Kind.EARNING,
                "amount": special_ot_total,
                "sort_order": 91,
            }
        )
        earnings += special_ot_total

    # Staged sheet total: Basic + Cost of Living + OT Amt (excludes Food/HRA/Extra OT)
    total_salary = (
        paid_by_code.get("BASIC", ZERO)
        + paid_by_code.get("COL", ZERO)
        + ot_amount
    ).quantize(Decimal("0.01"))

    # Approved reimbursements (unpaid) paid via this payroll run
    reimb_total, reimb_ids = _reimbursement_total(employee)
    if reimb_total > 0:
        lines.append(
            {
                "component": None,
                "code": "REIMB",
                "name": "Expense reimbursements",
                "kind": PayslipLine.Kind.EARNING,
                "amount": reimb_total,
                "sort_order": 95,
            }
        )
        earnings += reimb_total

    # Salary advance recoveries
    adv_total, adv_plan = _advance_deduction(employee)
    if adv_total > 0:
        lines.append(
            {
                "component": None,
                "code": "ADV",
                "name": "Salary advance recovery",
                "kind": PayslipLine.Kind.DEDUCTION,
                "amount": adv_total,
                "sort_order": 96,
            }
        )
        deductions += adv_total

    # Statutory / policy rules (after structure + OT gross base)
    earnings, deductions = _apply_statutory_rules(
        lines=lines,
        earnings=earnings,
        deductions=deductions,
        basic=basic,
        gross_for_rules=earnings,
    )

    # Approved incentive / bonus awards for this period
    award_ids = []
    earnings = _apply_incentive_awards(
        lines=lines,
        earnings=earnings,
        period=period,
        employee=employee,
        award_ids=award_ids,
    )

    # Explicit LWP info line when unpaid days exist (amount already in proration)
    if unpaid > 0:
        full_proratable = ZERO
        for row in resolved:
            c = row["component"]
            if c.kind != SalaryComponent.Kind.EARNING:
                continue
            if not getattr(c, "prorate_with_attendance", True):
                continue
            full_proratable += Decimal(row["amount"])
        lwp_amt = (full_proratable - (full_proratable * factor)).quantize(Decimal("0.01"))
        if lwp_amt > 0:
            lines.append(
                {
                    "component": None,
                    "code": "LWP_INFO",
                    "name": f"Loss of pay ({unpaid} unpaid day(s))",
                    "kind": PayslipLine.Kind.DEDUCTION,
                    "amount": ZERO,  # informational; already prorated in earnings
                    "sort_order": 250,
                }
            )

    net = (earnings - deductions).quantize(Decimal("0.01"))
    note_parts = []
    if reimb_ids:
        note_parts.append("REIMB:" + ",".join(str(i) for i in reimb_ids))
    if adv_plan:
        note_parts.append(
            "ADV:" + ",".join(f"{aid}={amt}" for aid, amt in adv_plan)
        )
    if award_ids:
        note_parts.append("INC:" + ",".join(str(i) for i in award_ids))
    notes = "|".join(note_parts)[:255]

    slip = Payslip.objects.create(
        period=period,
        employee=employee,
        structure=structure,
        currency=structure.currency or period.currency,
        status=Payslip.Status.DRAFT,
        calendar_days=calendar_days,
        unpaid_days=unpaid,
        paid_days=paid_days,
        ot_hours=ot_hours,
        ot_amount=ot_amount,
        special_ot_amount=special_ot_total,
        total_salary=total_salary,
        earnings_total=earnings.quantize(Decimal("0.01")),
        deductions_total=deductions.quantize(Decimal("0.01")),
        net_pay=net,
        notes=notes,
    )
    PayslipLine.objects.bulk_create(
        [
            PayslipLine(
                payslip=slip,
                component=row["component"],
                code=row["code"],
                name=row["name"],
                kind=row["kind"],
                amount=row["amount"],
                sort_order=row["sort_order"],
            )
            for row in lines
        ]
    )
    return slip


@transaction.atomic
def lock_period(period: PayrollPeriod) -> PayrollPeriod:
    if period.status == PayrollPeriod.Status.DRAFT:
        raise ValueError("Run payroll before locking.")
    if period.is_locked:
        return period
    period.status = PayrollPeriod.Status.LOCKED
    period.locked_at = timezone.now()
    period.save(update_fields=["status", "locked_at", "updated_at"])
    period.payslips.update(status=Payslip.Status.FINAL)
    _mark_reimbursements_paid(period)
    _apply_advance_recoveries(period)
    from .incentives import mark_awards_paid

    mark_awards_paid(period)
    return period


def _mark_reimbursements_paid(period: PayrollPeriod):
    """Mark expense claims captured on REIMB payslip lines as paid via payroll."""
    from expenses.models import ExpenseClaim
    from expenses.services import mark_claim_paid

    for slip in period.payslips.only("pk", "notes", "employee_id"):
        notes = slip.notes or ""
        reimb_part = ""
        for part in notes.split("|"):
            if part.startswith("REIMB:"):
                reimb_part = part[6:].strip()
                break
        if not reimb_part:
            continue
        ids = []
        for token in reimb_part.split(","):
            token = token.strip()
            if token.isdigit():
                ids.append(int(token))
        if not ids:
            continue
        for claim in ExpenseClaim.objects.filter(
            pk__in=ids,
            employee_id=slip.employee_id,
            status=ExpenseClaim.Status.APPROVED,
        ):
            try:
                mark_claim_paid(
                    claim,
                    paid_by=None,
                    payment_method=ExpenseClaim.PaymentMethod.PAYROLL,
                    notes=f"Auto-paid with payroll period {period.year}-{period.month:02d}",
                )
            except ValueError:
                continue


def _apply_advance_recoveries(period: PayrollPeriod):
    from loans.services import apply_recoveries

    items = []
    for slip in period.payslips.only("pk", "notes"):
        notes = slip.notes or ""
        adv_part = ""
        for part in notes.split("|"):
            if part.startswith("ADV:"):
                adv_part = part[4:].strip()
                break
        if not adv_part:
            continue
        for token in adv_part.split(","):
            token = token.strip()
            if "=" not in token:
                continue
            aid, amt = token.split("=", 1)
            if aid.isdigit():
                items.append((int(aid), amt, period))
    if items:
        apply_recoveries(period, items)


def period_totals(period: PayrollPeriod) -> dict:
    agg = period.payslips.aggregate(
        gross=Sum("earnings_total"),
        deductions=Sum("deductions_total"),
        net=Sum("net_pay"),
        ot=Sum("ot_amount"),
    )
    return {
        "count": period.payslips.count(),
        "gross": agg["gross"] or ZERO,
        "deductions": agg["deductions"] or ZERO,
        "net": agg["net"] or ZERO,
        "ot": agg["ot"] or ZERO,
    }
