from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class LeaveType(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    is_paid = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)
    check_balance = models.BooleanField(
        "Check leave balance",
        default=True,
        help_text=(
            "On: requests need enough balance. Off: no limit (e.g. Leave Without Pay) — "
            "days taken are still recorded on the balance."
        ),
    )
    exclude_off_days = models.BooleanField(
        "Skip weekly off days and holidays",
        default=False,
        help_text=(
            "On: weekly off days (from the employee's shift calendar) and public "
            "holidays inside the leave are not counted. Off: every calendar day counts."
        ),
    )
    default_entitlement = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        help_text="Default days per year when creating a balance",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} — {self.name}"


class LeaveBalance(models.Model):
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="leave_balances",
        db_index=True,
    )
    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.CASCADE, related_name="balances"
    )
    year = models.PositiveIntegerField(db_index=True)
    entitled = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("0.0"))
    used = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("0.0"))
    pending = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("0.0"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-year", "leave_type__code")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "leave_type", "year"],
                name="uniq_leave_balance_employee_type_year",
            )
        ]
        indexes = [
            models.Index(fields=["employee", "year"]),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.leave_type_id} {self.year}"

    @property
    def available(self) -> Decimal:
        return self.entitled - self.used - self.pending


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="leave_requests",
        db_index=True,
    )
    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.PROTECT, related_name="requests"
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    days = models.DecimalField(max_digits=6, decimal_places=1)
    # Dates charged to the balance: [["2026-07-02", "1"], ...]. Fixed at submit so
    # approve/cancel move the same days even if calendars or holidays change.
    # Empty for requests made before this existed: every calendar day counts.
    counted_days = models.JSONField(default=list, blank=True)
    is_half_day = models.BooleanField(
        default=False,
        help_text="Only for single-day requests; counts as 0.5 day",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reviewer_notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leave_requests_made",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_requests_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approval = models.ForeignKey(
        "workflows.ApprovalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    apply_to_attendance = models.BooleanField(
        default=True,
        help_text="On approve, mark daily attendance as On leave and lock those days",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["employee", "start_date", "end_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="leave_end_on_or_after_start",
            )
        ]

    def __str__(self):
        return f"{self.employee_id} {self.start_date}→{self.end_date} ({self.status})"

    def day_values(self) -> dict:
        """{date: Decimal} charged by this request (see counted_days)."""
        from datetime import date as _date, timedelta

        if self.counted_days:
            return {_date.fromisoformat(d): Decimal(v) for d, v in self.counted_days}
        value = Decimal("0.5") if self.is_half_day else Decimal("1")
        out, cur = {}, self.start_date
        while cur <= self.end_date:
            out[cur] = value
            cur += timedelta(days=1)
        return out

    def covers(self, day) -> bool:
        """True if `day` is a leave day of this request (off days may be skipped)."""
        if not (self.start_date <= day <= self.end_date):
            return False
        if not self.counted_days:
            return True
        return day.isoformat() in {d for d, _ in self.counted_days}

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after start date."})
        if self.is_half_day and self.start_date and self.end_date and self.start_date != self.end_date:
            raise ValidationError({"is_half_day": "Half day only allowed for a single date."})
