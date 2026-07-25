"""Salary advance submit / approve / disburse / recover."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.mail import notify_user
from notifications.models import Notification
from payroll.currencies import default_currency_code, format_money
from workflows.models import ApprovalRequest

from .models import AdvanceRecovery, SalaryAdvance

ZERO = Decimal("0.00")


def employee_for_user(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, "employee_profile", None)


def resolve_assignee_user(employee):
    manager = getattr(employee, "manager", None)
    if manager and manager.user_id:
        return manager.user
    return None


def notify(user, *, title, body="", level=Notification.Level.INFO, link=""):
    notify_user(user, title=title, body=body, level=level, link=link)


@transaction.atomic
def submit_advance(
    *,
    employee,
    amount,
    installments,
    reason,
    requested_by,
    currency=None,
):
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    installments = int(installments or 1)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if installments < 1:
        raise ValueError("Installments must be at least 1.")

    installment = (amount / Decimal(installments)).quantize(Decimal("0.01"))
    advance = SalaryAdvance.objects.create(
        employee=employee,
        amount=amount,
        currency=currency or default_currency_code(),
        reason=(reason or "").strip(),
        installments=installments,
        installment_amount=installment,
        status=SalaryAdvance.Status.PENDING,
        requested_by=requested_by,
    )

    assignee = resolve_assignee_user(employee)
    approval = ApprovalRequest.objects.create(
        title=f"Salary advance · {employee.employee_code}",
        module="loans",
        object_id=advance.pk,
        requester=requested_by,
        assignee=assignee,
        status=ApprovalRequest.Status.PENDING,
        notes=(reason or "")[:500],
    )
    advance.approval = approval
    advance.save(update_fields=["approval", "updated_at"])

    detail = reverse("loans:detail", args=[advance.pk])
    notify(
        assignee,
        title="Salary advance pending",
        body=f"{employee.full_name} requested {format_money(amount, advance.currency)}.",
        level=Notification.Level.WARNING,
        link=detail,
    )
    return advance


@transaction.atomic
def approve_advance(advance, *, reviewed_by, notes=""):
    if advance.status != SalaryAdvance.Status.PENDING:
        raise ValueError("Only pending advances can be approved.")
    advance.status = SalaryAdvance.Status.APPROVED
    advance.reviewed_by = reviewed_by
    advance.reviewed_at = timezone.now()
    advance.reviewer_notes = (notes or "").strip()
    advance.save()
    if advance.approval_id:
        advance.approval.status = ApprovalRequest.Status.APPROVED
        advance.approval.decided_at = timezone.now()
        advance.approval.save(update_fields=["status", "decided_at"])

    detail = reverse("loans:detail", args=[advance.pk])
    notify(
        advance.requested_by,
        title="Salary advance approved",
        body=f"Your advance of {format_money(advance.amount, advance.currency)} was approved.",
        level=Notification.Level.SUCCESS,
        link=detail,
    )
    return advance


@transaction.atomic
def reject_advance(advance, *, reviewed_by, notes=""):
    if advance.status != SalaryAdvance.Status.PENDING:
        raise ValueError("Only pending advances can be rejected.")
    advance.status = SalaryAdvance.Status.REJECTED
    advance.reviewed_by = reviewed_by
    advance.reviewed_at = timezone.now()
    advance.reviewer_notes = (notes or "").strip()
    advance.save()
    if advance.approval_id:
        advance.approval.status = ApprovalRequest.Status.REJECTED
        advance.approval.decided_at = timezone.now()
        advance.approval.save(update_fields=["status", "decided_at"])

    detail = reverse("loans:detail", args=[advance.pk])
    notify(
        advance.requested_by,
        title="Salary advance rejected",
        body=(notes or "Your salary advance request was rejected.").strip(),
        level=Notification.Level.DANGER,
        link=detail,
    )
    return advance


@transaction.atomic
def cancel_advance(advance, *, user):
    if advance.status not in (
        SalaryAdvance.Status.PENDING,
        SalaryAdvance.Status.APPROVED,
    ):
        raise ValueError("Only pending or approved advances can be cancelled.")
    if (
        advance.requested_by_id != user.id
        and not getattr(user, "is_superuser", False)
    ):
        # callers enforce manage perm; allow requester cancel
        pass
    advance.status = SalaryAdvance.Status.CANCELLED
    advance.save(update_fields=["status", "updated_at"])
    if advance.approval_id and advance.approval.status == ApprovalRequest.Status.PENDING:
        advance.approval.status = ApprovalRequest.Status.CANCELLED
        advance.approval.decided_at = timezone.now()
        advance.approval.save(update_fields=["status", "decided_at"])
    return advance


@transaction.atomic
def disburse_advance(
    advance,
    *,
    disbursed_by,
    disburse_method="",
    disburse_reference="",
    notes="",
):
    if advance.status != SalaryAdvance.Status.APPROVED:
        raise ValueError("Only approved advances can be disbursed.")
    advance.status = SalaryAdvance.Status.DISBURSED
    advance.disbursed_at = timezone.now()
    advance.disbursed_by = disbursed_by
    advance.disburse_method = (
        disburse_method or SalaryAdvance.DisburseMethod.BANK
    )
    advance.disburse_reference = (disburse_reference or "").strip()
    if notes.strip():
        advance.reviewer_notes = (
            f"{advance.reviewer_notes}\n{notes.strip()}".strip()
            if advance.reviewer_notes
            else notes.strip()
        )
    advance.save()

    detail = reverse("loans:detail", args=[advance.pk])
    notify(
        advance.requested_by,
        title="Salary advance disbursed",
        body=(
            f"{format_money(advance.amount, advance.currency)} paid "
            f"({advance.get_disburse_method_display() or 'payment'}). "
            f"Recovery starts on the next payroll."
        ),
        level=Notification.Level.SUCCESS,
        link=detail,
    )
    return advance


def active_advances_for_recovery(employee):
    return SalaryAdvance.objects.filter(
        employee=employee,
        status__in=[
            SalaryAdvance.Status.DISBURSED,
            SalaryAdvance.Status.RECOVERING,
        ],
    ).order_by("created_at")


def deduction_plan_for_employee(employee) -> tuple[Decimal, list[tuple[int, Decimal]]]:
    """
    Return (total_deduction, [(advance_id, amount), ...]) for this payroll run.
    """
    plan = []
    total = ZERO
    for adv in active_advances_for_recovery(employee):
        remaining = adv.remaining
        if remaining <= 0:
            continue
        cap = adv.installment_amount or remaining
        if cap <= 0:
            cap = remaining
        take = min(remaining, cap).quantize(Decimal("0.01"))
        if take <= 0:
            continue
        plan.append((adv.pk, take))
        total += take
    return total.quantize(Decimal("0.01")), plan


@transaction.atomic
def apply_recoveries(period, plan_by_employee_notes: list[tuple]):
    """
    Apply recoveries from payslip notes after lock.
    plan items come from parsing ADV:id=amt,id=amt on each slip.
    """
    for advance_id, amount, period_obj in plan_by_employee_notes:
        try:
            adv = SalaryAdvance.objects.select_for_update().get(pk=advance_id)
        except SalaryAdvance.DoesNotExist:
            continue
        if adv.status not in (
            SalaryAdvance.Status.DISBURSED,
            SalaryAdvance.Status.RECOVERING,
        ):
            continue
        amount = Decimal(str(amount)).quantize(Decimal("0.01"))
        if amount <= 0:
            continue
        take = min(adv.remaining, amount)
        if take <= 0:
            continue
        AdvanceRecovery.objects.create(
            advance=adv, period=period_obj, amount=take
        )
        adv.recovered_amount = (adv.recovered_amount + take).quantize(Decimal("0.01"))
        if adv.remaining <= 0:
            adv.status = SalaryAdvance.Status.CLOSED
            adv.recovered_amount = adv.amount
        else:
            adv.status = SalaryAdvance.Status.RECOVERING
        adv.save(update_fields=["recovered_amount", "status", "updated_at"])

        detail = reverse("loans:detail", args=[adv.pk])
        notify(
            adv.requested_by,
            title="Salary advance recovery",
            body=(
                f"{format_money(take, adv.currency)} deducted. "
                f"Remaining {format_money(adv.remaining, adv.currency)}."
            ),
            level=Notification.Level.INFO,
            link=detail,
        )
