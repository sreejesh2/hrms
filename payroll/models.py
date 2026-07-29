from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .currencies import CURRENCY_CHOICES, FALLBACK_DEFAULT


class SalaryComponent(models.Model):
    """Company-level pay head (Basic, HRA, PF, …). Scalable catalog."""

    class Kind(models.TextChoices):
        EARNING = "earning", "Earning"
        DEDUCTION = "deduction", "Deduction"

    class CalcMethod(models.TextChoices):
        FIXED = "fixed", "Fixed amount"
        PERCENT_BASIC = "percent_basic", "% of Basic"
        PERCENT_GROSS = "percent_gross", "% of Gross"

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True)
    calc_method = models.CharField(
        max_length=20, choices=CalcMethod.choices, default=CalcMethod.FIXED
    )
    default_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Used when calc method is % of Basic/Gross (template default)",
    )
    is_basic = models.BooleanField(
        default=False,
        help_text="Mark the Basic component (only one should be Basic)",
    )
    is_taxable = models.BooleanField(default=True)
    affects_ot_base = models.BooleanField(
        default=False,
        help_text="Include in OT hourly rate base (usually Basic only)",
    )
    prorate_with_attendance = models.BooleanField(
        default=True,
        help_text="When on, amount is reduced by unpaid / LWP days. Turn off for fixed heads like Food Allow.",
    )
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "code")

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_basic:
            SalaryComponent.objects.exclude(pk=self.pk).filter(is_basic=True).update(
                is_basic=False
            )


class SalaryTemplate(models.Model):
    """Reusable package (e.g. Grade-A) for bulk assignment at scale."""

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    currency = models.CharField(
        max_length=8,
        choices=CURRENCY_CHOICES,
        default=FALLBACK_DEFAULT,
        help_text="Currency applied when assigning this template",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} — {self.name}"


class SalaryTemplateLine(models.Model):
    template = models.ForeignKey(
        SalaryTemplate, on_delete=models.CASCADE, related_name="lines"
    )
    component = models.ForeignKey(
        SalaryComponent, on_delete=models.PROTECT, related_name="template_lines"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Fixed amount (or base amount when using % methods)",
    )
    percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override component default % when applicable",
    )

    class Meta:
        ordering = ("component__sort_order", "component__code")
        constraints = [
            models.UniqueConstraint(
                fields=["template", "component"],
                name="uniq_salary_template_component",
            )
        ]

    def __str__(self):
        return f"{self.template_id}:{self.component_id}"


class SalaryStructure(models.Model):
    """Versioned employee pay package (effective-dated for history + scale)."""

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="salary_structures",
        db_index=True,
    )
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Blank = currently open / ongoing",
    )
    template = models.ForeignKey(
        SalaryTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="structures",
    )
    currency = models.CharField(
        max_length=8,
        choices=CURRENCY_CHOICES,
        default=FALLBACK_DEFAULT,
        db_index=True,
    )
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_structures_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-effective_from", "-id")
        indexes = [
            models.Index(fields=["employee", "-effective_from"]),
            models.Index(fields=["employee", "effective_from", "effective_to"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="salary_structure_end_on_or_after_start",
            ),
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(effective_to__isnull=True),
                name="uniq_open_salary_structure_per_employee",
            ),
        ]

    def __str__(self):
        return f"{self.employee_id} @ {self.effective_from}"

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Must be on/after effective from."})

    @property
    def is_open(self):
        return self.effective_to is None

    def basic_amount(self) -> Decimal:
        for line in self._cached_lines():
            if getattr(line.component, "is_basic", False):
                return line.amount
        return Decimal("0.00")

    def earnings_total(self) -> Decimal:
        return self._sum_kind(SalaryComponent.Kind.EARNING)

    def deductions_total(self) -> Decimal:
        return self._sum_kind(SalaryComponent.Kind.DEDUCTION)

    def net_preview(self) -> Decimal:
        return self.earnings_total() - self.deductions_total()

    def _cached_lines(self):
        """Use prefetch cache when present to avoid N+1 on list pages."""
        cache = getattr(self, "_prefetched_objects_cache", None) or {}
        if "lines" in cache:
            return list(self.lines.all())
        return list(self.lines.select_related("component"))

    def _sum_kind(self, kind) -> Decimal:
        total = Decimal("0.00")
        lines = self._cached_lines()
        basic = Decimal("0.00")
        for line in lines:
            if getattr(line.component, "is_basic", False):
                basic = line.amount
                break
        # First pass fixed + percent_basic; second pass percent_gross needs gross
        gross = Decimal("0.00")
        for line in lines:
            c = line.component
            if c.kind != SalaryComponent.Kind.EARNING:
                continue
            if c.calc_method == SalaryComponent.CalcMethod.FIXED:
                gross += line.amount
            elif c.calc_method == SalaryComponent.CalcMethod.PERCENT_BASIC:
                pct = line.percent if line.percent is not None else c.default_percent or 0
                gross += (basic * pct / Decimal("100")).quantize(Decimal("0.01"))
        # percent of gross earnings
        for line in lines:
            c = line.component
            if c.kind != SalaryComponent.Kind.EARNING:
                continue
            if c.calc_method == SalaryComponent.CalcMethod.PERCENT_GROSS:
                pct = line.percent if line.percent is not None else c.default_percent or 0
                gross += (gross * pct / Decimal("100")).quantize(Decimal("0.01"))
        if kind == SalaryComponent.Kind.EARNING:
            return gross.quantize(Decimal("0.01"))

        ded = Decimal("0.00")
        for line in lines:
            c = line.component
            if c.kind != SalaryComponent.Kind.DEDUCTION:
                continue
            if c.calc_method == SalaryComponent.CalcMethod.FIXED:
                ded += line.amount
            elif c.calc_method == SalaryComponent.CalcMethod.PERCENT_BASIC:
                pct = line.percent if line.percent is not None else c.default_percent or 0
                ded += (basic * pct / Decimal("100")).quantize(Decimal("0.01"))
            elif c.calc_method == SalaryComponent.CalcMethod.PERCENT_GROSS:
                pct = line.percent if line.percent is not None else c.default_percent or 0
                ded += (gross * pct / Decimal("100")).quantize(Decimal("0.01"))
        return ded.quantize(Decimal("0.01"))

    def resolved_lines(self):
        """Return list of dicts with computed amount for display."""
        basic = self.basic_amount()
        lines = sorted(
            self._cached_lines(),
            key=lambda line: (
                line.component.sort_order,
                line.component.code,
            ),
        )
        # Build gross for percent_gross
        temp_gross = Decimal("0.00")
        computed = []
        for line in lines:
            c = line.component
            amt = line.amount
            if c.calc_method == SalaryComponent.CalcMethod.PERCENT_BASIC:
                pct = line.percent if line.percent is not None else c.default_percent or 0
                amt = (basic * Decimal(pct) / Decimal("100")).quantize(Decimal("0.01"))
            computed.append({"line": line, "component": c, "amount": amt})
            if c.kind == SalaryComponent.Kind.EARNING and c.calc_method != SalaryComponent.CalcMethod.PERCENT_GROSS:
                temp_gross += amt
        # second pass percent gross
        result = []
        for row in computed:
            c = row["component"]
            amt = row["amount"]
            if c.calc_method == SalaryComponent.CalcMethod.PERCENT_GROSS:
                pct = row["line"].percent if row["line"].percent is not None else c.default_percent or 0
                amt = (temp_gross * Decimal(pct) / Decimal("100")).quantize(Decimal("0.01"))
                if c.kind == SalaryComponent.Kind.EARNING:
                    temp_gross += amt
            result.append({**row, "amount": amt})
        return result


class SalaryStructureLine(models.Model):
    structure = models.ForeignKey(
        SalaryStructure, on_delete=models.CASCADE, related_name="lines"
    )
    component = models.ForeignKey(
        SalaryComponent, on_delete=models.PROTECT, related_name="structure_lines"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional % override for percent-based components",
    )

    class Meta:
        ordering = ("component__sort_order", "component__code")
        constraints = [
            models.UniqueConstraint(
                fields=["structure", "component"],
                name="uniq_salary_structure_component",
            )
        ]

    def __str__(self):
        return f"{self.structure_id}:{self.component_id}={self.amount}"


class PayrollPeriod(models.Model):
    """Labeled pay period (calendar month or company cycle, e.g. 25th→24th)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CALCULATED = "calculated", "Calculated"
        LOCKED = "locked", "Locked"

    year = models.PositiveSmallIntegerField(db_index=True)
    month = models.PositiveSmallIntegerField(db_index=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    currency = models.CharField(
        max_length=8, choices=CURRENCY_CHOICES, default=FALLBACK_DEFAULT
    )
    notes = models.CharField(max_length=255, blank=True)
    calculated_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_periods_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-year", "-month")
        constraints = [
            models.UniqueConstraint(
                fields=["year", "month"], name="uniq_payroll_period_year_month"
            ),
            models.CheckConstraint(
                condition=Q(month__gte=1) & Q(month__lte=12),
                name="payroll_period_month_1_12",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="payroll_period_end_on_or_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.year}-{self.month:02d} ({self.status})"

    @property
    def label(self):
        from setup.cycles import period_label

        return period_label(self.year, self.month, self.start_date, self.end_date)

    @property
    def short_label(self):
        import calendar

        return f"{calendar.month_name[self.month]} {self.year}"

    @property
    def days_in_period(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def is_locked(self):
        return self.status == self.Status.LOCKED

    @property
    def can_run(self):
        return self.status in (self.Status.DRAFT, self.Status.CALCULATED)


class Payslip(models.Model):
    """One employee result inside a payroll period."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINAL = "final", "Final"

    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name="payslips"
    )
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="payslips",
        db_index=True,
    )
    structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payslips",
    )
    currency = models.CharField(max_length=8, choices=CURRENCY_CHOICES, default=FALLBACK_DEFAULT)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    calendar_days = models.PositiveSmallIntegerField(default=30)
    unpaid_days = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    paid_days = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    ot_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    ot_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    special_ot_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Extra / special OT flat amount for the period",
    )
    total_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Basic + Cost of Living + OT Amt (before Food/HRA/extras)",
    )
    earnings_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    deductions_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("employee__employee_code",)
        constraints = [
            models.UniqueConstraint(
                fields=["period", "employee"], name="uniq_payslip_period_employee"
            )
        ]
        indexes = [
            models.Index(fields=["period", "employee"]),
        ]

    def __str__(self):
        return f"{self.employee_id} @ {self.period_id} = {self.net_pay}"


class PayslipLine(models.Model):
    class Kind(models.TextChoices):
        EARNING = "earning", "Earning"
        DEDUCTION = "deduction", "Deduction"

    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="lines")
    component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sort_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ("sort_order", "code")

    def __str__(self):
        return f"{self.payslip_id}:{self.code}={self.amount}"


class PayslipTemplate(models.Model):
    """
    Editable payslip layout (singleton default).
    Company details come from OrganizationSettings; this controls wording & visibility.
    """

    name = models.CharField(max_length=80, default="Standard payslip")
    document_title = models.CharField(
        max_length=80,
        default="Payslip",
        help_text="Title printed at the top (e.g. Salary Slip / Payslip)",
    )
    header_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short line under the company header",
    )
    footer_text = models.TextField(
        blank=True,
        default=(
            "This is a computer-generated payslip and does not require a signature. "
            "For queries contact HR / Payroll."
        ),
    )
    bank_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional bank / payment note on the slip",
    )
    show_logo = models.BooleanField(default=True)
    show_address = models.BooleanField(default=True)
    show_phone = models.BooleanField(default=True)
    show_email = models.BooleanField(default=True)
    show_trn = models.BooleanField(default=True)
    show_paid_days = models.BooleanField(default=True)
    show_ot = models.BooleanField(default=True)
    # Optional HTML snippets — Django template syntax with {{ company.* }} {{ slip.* }}
    header_html = models.TextField(
        blank=True,
        help_text="Optional custom header HTML (advanced). Leave blank to use the default layout.",
    )
    footer_html = models.TextField(
        blank=True,
        help_text="Optional custom footer HTML (advanced).",
    )
    is_default = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_default", "name")
        verbose_name = "Payslip template"
        verbose_name_plural = "Payslip templates"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            PayslipTemplate.objects.exclude(pk=self.pk).filter(is_default=True).update(
                is_default=False
            )

    @classmethod
    def load_default(cls):
        obj = cls.objects.filter(is_default=True).first()
        if obj:
            return obj
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"name": "Standard payslip", "is_default": True},
        )
        if not obj.is_default:
            obj.is_default = True
            obj.save(update_fields=["is_default"])
        return obj


class StatutoryRule(models.Model):
    """
    Configurable statutory / policy line applied during monthly payroll.
    Dubai-oriented: GPSSA-style %, fixed medical, etc. Gratuity is separate (EOS).
    """

    class CalcMethod(models.TextChoices):
        FIXED = "fixed", "Fixed amount"
        PERCENT_BASIC = "percent_basic", "% of Basic"
        PERCENT_GROSS = "percent_gross", "% of Gross (structure + OT)"

    class Kind(models.TextChoices):
        DEDUCTION = "deduction", "Deduction (from net)"
        EARNING = "earning", "Earning (add to gross)"

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.DEDUCTION)
    calc_method = models.CharField(
        max_length=20, choices=CalcMethod.choices, default=CalcMethod.FIXED
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Used when calc method is Fixed",
    )
    percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Used when calc method is % of Basic / Gross",
    )
    max_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional cap after calculation",
    )
    min_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional floor after calculation",
    )
    country = models.CharField(max_length=64, default="United Arab Emirates")
    notes = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=300)
    apply_in_payroll = models.BooleanField(
        default=True,
        help_text="When on, active rules are added to every payslip on Run",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "code")
        verbose_name = "Statutory / deduction rule"
        verbose_name_plural = "Statutory / deduction rules"

    def __str__(self):
        return f"{self.code} — {self.name}"

    def compute(self, *, basic: Decimal, gross: Decimal) -> Decimal:
        if self.calc_method == self.CalcMethod.FIXED:
            value = Decimal(self.amount or 0)
        else:
            pct = Decimal(self.percent or 0)
            base = basic if self.calc_method == self.CalcMethod.PERCENT_BASIC else gross
            value = base * pct / Decimal("100")
        value = value.quantize(Decimal("0.01"))
        if self.max_amount is not None:
            value = min(value, Decimal(self.max_amount))
        if self.min_amount is not None:
            value = max(value, Decimal(self.min_amount))
        return value.quantize(Decimal("0.01"))


class IncentivePlan(models.Model):
    """Catalog of bonus / incentive types (spot, quarterly, sales, …)."""

    class Frequency(models.TextChoices):
        ONE_TIME = "one_time", "One-time"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.PROTECT,
        related_name="incentive_plans",
        help_text="Earning pay head used on the payslip",
    )
    frequency = models.CharField(
        max_length=16,
        choices=Frequency.choices,
        default=Frequency.ONE_TIME,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)
        verbose_name = "Incentive plan"
        verbose_name_plural = "Incentive plans"

    def __str__(self):
        return f"{self.code} — {self.name}"


class IncentiveAward(models.Model):
    """
    Variable-pay ledger: one approved amount for an employee in a pay period.
    Included on payroll run; marked paid when the period is locked.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    plan = models.ForeignKey(
        IncentivePlan, on_delete=models.PROTECT, related_name="awards"
    )
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="incentive_awards",
        db_index=True,
    )
    period = models.ForeignKey(
        PayrollPeriod,
        on_delete=models.PROTECT,
        related_name="incentive_awards",
        db_index=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(
        max_length=8, choices=CURRENCY_CHOICES, default=FALLBACK_DEFAULT
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incentive_awards_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incentive_awards_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    payslip_line = models.ForeignKey(
        "PayslipLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Incentive award"
        verbose_name_plural = "Incentive awards"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "plan", "period"],
                condition=Q(status__in=["draft", "approved"]),
                name="uniq_open_incentive_award",
            ),
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="incentive_award_amount_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["period", "status"]),
            models.Index(fields=["employee", "status"]),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.plan_id} @ {self.period_id} = {self.amount}"

    @property
    def slip_code(self) -> str:
        return f"INC_{self.pk}"
