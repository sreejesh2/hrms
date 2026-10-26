"""Expense claim submit / approve / reject / cancel / mark paid."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.mail import notify_approvers, notify_user
from notifications.models import Notification
from payroll.currencies import default_currency_code, format_money
from workflows.models import ApprovalRequest

from .models import ExpenseCategory, ExpenseClaim, ExpenseLine


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


def _validate_lines(line_rows: list[dict], categories_by_pk: dict):
    if not line_rows:
        raise ValueError("Add at least one expense line.")
    cleaned = []
    for i, row in enumerate(line_rows, start=1):
        cat = row.get("category")
        if not cat:
            raise ValueError(f"Line {i}: select a category.")
        if not getattr(cat, "is_active", True):
            raise ValueError(f"Line {i}: category {cat.code} is inactive.")
        amount = row.get("amount")
        if amount is None or Decimal(amount) <= 0:
            raise ValueError(f"Line {i}: amount must be greater than zero.")
        expense_date = row.get("expense_date")
        if not expense_date:
            raise ValueError(f"Line {i}: expense date is required.")
        receipt = row.get("receipt")
        if cat.requires_receipt and not receipt:
            raise ValueError(f"Line {i}: receipt is required for {cat.code}.")
        cleaned.append(
            {
                "category": cat,
                "expense_date": expense_date,
                "amount": Decimal(amount),
                "merchant": (row.get("merchant") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "receipt": receipt,
                "sort_order": row.get("sort_order") or (i * 10),
            }
        )
    return cleaned


@transaction.atomic
def submit_claim(
    *,
    employee,
    title,
    purpose,
    currency,
    requested_by,
    line_rows: list[dict],
):
    categories = {
        c.pk: c for c in ExpenseCategory.objects.filter(is_active=True)
    }
    # Ensure category objects are hydrated
    normalized = []
    for row in line_rows:
        cat = row.get("category")
        if cat is not None and not isinstance(cat, ExpenseCategory):
            cat = categories.get(int(cat))
            row = {**row, "category": cat}
        normalized.append(row)

    lines = _validate_lines(normalized, categories)
    currency = currency or default_currency_code()
    total = sum((ln["amount"] for ln in lines), Decimal("0.00"))

    claim = ExpenseClaim.objects.create(
        employee=employee,
        title=title.strip(),
        purpose=(purpose or "").strip(),
        currency=currency,
        status=ExpenseClaim.Status.PENDING,
        total_amount=total,
        requested_by=requested_by,
    )
    for ln in lines:
        ExpenseLine.objects.create(
            claim=claim,
            category=ln["category"],
            expense_date=ln["expense_date"],
            amount=ln["amount"],
            merchant=ln["merchant"],
            description=ln["description"],
            receipt=ln["receipt"],
            sort_order=ln["sort_order"],
        )

    assignee = resolve_assignee_user(employee)
    approval = ApprovalRequest.objects.create(
        title=f"Reimbursement · {employee.employee_code} · {claim.title[:60]}",
        module="expense",
        object_id=claim.pk,
        requester=requested_by,
        assignee=assignee,
        status=ApprovalRequest.Status.PENDING,
        notes=(purpose or title)[:500],
    )
    claim.approval = approval
    claim.save(update_fields=["approval", "updated_at"])

    detail = reverse("expenses:detail", args=[claim.pk])
    notify_approvers(
        assignee,
        fallback_perm="expenses.manage",
        title="Reimbursement claim pending",
        body=(
            f"{employee.full_name} submitted {format_money(total, currency)} "
            f"({claim.title})."
        ),
        link=detail,
    )
    return claim


@transaction.atomic
def approve_claim(claim, *, reviewer, notes=""):
    if claim.status != ExpenseClaim.Status.PENDING:
        raise ValueError("Only pending claims can be approved.")

    claim.status = ExpenseClaim.Status.APPROVED
    claim.reviewed_by = reviewer
    claim.reviewed_at = timezone.now()
    claim.reviewer_notes = notes.strip()
    claim.save()

    if claim.approval_id:
        claim.approval.status = ApprovalRequest.Status.APPROVED
        claim.approval.decided_at = timezone.now()
        claim.approval.notes = notes.strip() or claim.approval.notes
        claim.approval.save(update_fields=["status", "decided_at", "notes"])

    detail = reverse("expenses:detail", args=[claim.pk])
    notify(
        claim.requested_by,
        title="Reimbursement claim approved",
        body=(
            f"{claim.title} — {format_money(claim.total_amount, claim.currency)} "
            "approved. Awaiting payment."
        ),
        level=Notification.Level.SUCCESS,
        link=detail,
    )
    return claim


@transaction.atomic
def reject_claim(claim, *, reviewer, notes=""):
    if claim.status != ExpenseClaim.Status.PENDING:
        raise ValueError("Only pending claims can be rejected.")

    claim.status = ExpenseClaim.Status.REJECTED
    claim.reviewed_by = reviewer
    claim.reviewed_at = timezone.now()
    claim.reviewer_notes = notes.strip()
    claim.save()

    if claim.approval_id:
        claim.approval.status = ApprovalRequest.Status.REJECTED
        claim.approval.decided_at = timezone.now()
        claim.approval.notes = notes.strip() or claim.approval.notes
        claim.approval.save(update_fields=["status", "decided_at", "notes"])

    detail = reverse("expenses:detail", args=[claim.pk])
    notify(
        claim.requested_by,
        title="Reimbursement claim rejected",
        body=notes.strip() or f"{claim.title} was rejected.",
        level=Notification.Level.WARNING,
        link=detail,
    )
    return claim


@transaction.atomic
def cancel_claim(claim, *, user):
    if claim.status != ExpenseClaim.Status.PENDING:
        raise ValueError("Only pending claims can be cancelled.")
    if claim.requested_by_id != user.id:
        raise ValueError("Only the requester can cancel this claim.")

    claim.status = ExpenseClaim.Status.CANCELLED
    claim.reviewed_by = user
    claim.reviewed_at = timezone.now()
    claim.save()

    if claim.approval_id:
        claim.approval.status = ApprovalRequest.Status.CANCELLED
        claim.approval.decided_at = timezone.now()
        claim.approval.save(update_fields=["status", "decided_at"])
    return claim


@transaction.atomic
def mark_claim_paid(
    claim,
    *,
    paid_by,
    payment_method="",
    payment_reference="",
    notes="",
):
    if claim.status != ExpenseClaim.Status.APPROVED:
        raise ValueError("Only approved claims can be marked paid.")

    claim.status = ExpenseClaim.Status.PAID
    claim.paid_at = timezone.now()
    claim.paid_by = paid_by
    claim.payment_method = payment_method or ExpenseClaim.PaymentMethod.BANK
    claim.payment_reference = (payment_reference or "").strip()
    if notes.strip():
        claim.reviewer_notes = (
            f"{claim.reviewer_notes}\n{notes.strip()}".strip()
            if claim.reviewer_notes
            else notes.strip()
        )
    claim.save()

    detail = reverse("expenses:detail", args=[claim.pk])
    notify(
        claim.requested_by,
        title="Reimbursement paid",
        body=(
            f"{claim.title} — {format_money(claim.total_amount, claim.currency)} "
            f"marked paid ({claim.get_payment_method_display() or 'payment'})."
        ),
        level=Notification.Level.SUCCESS,
        link=detail,
    )
    return claim


def seed_default_categories():
    defaults = [
        ("TRAVEL", "Travel", True, 10),
        ("MEALS", "Meals", True, 20),
        ("HOTEL", "Accommodation", True, 30),
        ("TAXI", "Transport / Taxi", True, 40),
        ("CLIENT", "Client entertainment", True, 50),
        ("OFFICE", "Office supplies", False, 60),
        ("TELECOM", "Telecom / Internet", True, 70),
        ("OTHER", "Other", False, 90),
    ]
    for code, name, receipt, order in defaults:
        ExpenseCategory.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "requires_receipt": receipt,
                "is_active": True,
                "sort_order": order,
            },
        )
