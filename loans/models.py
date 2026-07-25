from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from payroll.currencies import CURRENCY_CHOICES, FALLBACK_DEFAULT


class SalaryAdvance(models.Model):
    """Salary advance (short-term recovery via payroll deductions)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        DISBURSED = "disbursed", "Disbursed"
        RECOVERING = "recovering", "Recovering"
        CLOSED = "closed", "Closed"

    class DisburseMethod(models.TextChoices):
        BANK = "bank", "Bank transfer"
        CASH = "cash", "Cash"
        OTHER = "other", "Other"

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="salary_advances",
        db_index=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(
        max_length=8, choices=CURRENCY_CHOICES, default=FALLBACK_DEFAULT
    )
    reason = models.TextField(blank=True)
    installments = models.PositiveSmallIntegerField(
        default=1,
        help_text="Number of payroll months to recover over (1 = full amount next run)",
    )
    installment_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Max deduction per payroll period (auto-set from amount ÷ installments)",
    )
    recovered_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="salary_advances_requested",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_advances_reviewed",
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
    disbursed_at = models.DateTimeField(null=True, blank=True)
    disbursed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_advances_disbursed",
    )
    disburse_method = models.CharField(
        max_length=16, choices=DisburseMethod.choices, blank=True
    )
    disburse_reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["employee", "status"]),
        ]
        verbose_name = "salary advance"
        verbose_name_plural = "salary advances"

    def __str__(self):
        return f"{self.employee_id} · {self.amount} ({self.status})"

    @property
    def remaining(self) -> Decimal:
        rem = (self.amount or Decimal("0")) - (self.recovered_amount or Decimal("0"))
        return rem if rem > 0 else Decimal("0.00")

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
        if self.installments < 1:
            raise ValidationError({"installments": "At least 1 installment."})

    def save(self, *args, **kwargs):
        if self.amount and self.installments and (
            not self.installment_amount or self.installment_amount <= 0
        ):
            self.installment_amount = (
                self.amount / Decimal(self.installments)
            ).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


class AdvanceRecovery(models.Model):
    """One payroll deduction applied against a salary advance."""

    advance = models.ForeignKey(
        SalaryAdvance, on_delete=models.CASCADE, related_name="recoveries", db_index=True
    )
    period = models.ForeignKey(
        "payroll.PayrollPeriod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advance_recoveries",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Advance {self.advance_id} · {self.amount}"
