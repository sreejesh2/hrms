from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from payroll.currencies import CURRENCY_CHOICES, FALLBACK_DEFAULT


class ExpenseCategory(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    requires_receipt = models.BooleanField(
        default=False,
        help_text="When on, each line in this category must include a receipt file",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "code")
        verbose_name_plural = "Reimbursement categories"

    def __str__(self):
        return f"{self.code} — {self.name}"


class ExpenseClaim(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        PAID = "paid", "Paid"

    class PaymentMethod(models.TextChoices):
        BANK = "bank", "Bank transfer"
        CASH = "cash", "Cash"
        PAYROLL = "payroll", "Via payroll"
        OTHER = "other", "Other"

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="expense_claims",
        db_index=True,
    )
    title = models.CharField(max_length=160)
    purpose = models.TextField(blank=True)
    currency = models.CharField(
        max_length=8, choices=CURRENCY_CHOICES, default=FALLBACK_DEFAULT
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="expense_claims_made",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_claims_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_notes = models.TextField(blank=True)
    approval = models.ForeignKey(
        "workflows.ApprovalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_claims_paid",
    )
    payment_method = models.CharField(
        max_length=16, choices=PaymentMethod.choices, blank=True
    )
    payment_reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["employee", "status"]),
        ]

    def __str__(self):
        return f"{self.employee_id} · {self.title} ({self.status})"

    def recalculate_total(self, *, save=True):
        total = self.lines.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        self.total_amount = total
        if save:
            self.save(update_fields=["total_amount", "updated_at"])
        return total


class ExpenseLine(models.Model):
    claim = models.ForeignKey(
        ExpenseClaim, on_delete=models.CASCADE, related_name="lines"
    )
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    expense_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    merchant = models.CharField(max_length=160, blank=True)
    description = models.CharField(max_length=255, blank=True)
    receipt = models.FileField(
        upload_to="expense_receipts/%Y/%m/",
        blank=True,
        null=True,
    )
    sort_order = models.PositiveSmallIntegerField(default=10)

    class Meta:
        ordering = ("sort_order", "expense_date", "id")

    def __str__(self):
        return f"{self.claim_id}:{self.category_id}={self.amount}"

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
        if self.category_id and self.category.requires_receipt and not self.receipt:
            raise ValidationError(
                {"receipt": f"Receipt is required for {self.category.code}."}
            )
