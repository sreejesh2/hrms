from django.db import models

from payroll.currencies import CURRENCY_CHOICES, FALLBACK_DEFAULT


class OrganizationSettings(models.Model):
    """Singleton company profile — shown on payslips and documents."""

    company_name = models.CharField(max_length=160, default="Day Pay Company")
    legal_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Legal / trade name if different from display name",
    )
    country = models.CharField(
        max_length=64,
        default="United Arab Emirates",
        help_text="Primary operating country",
    )
    city = models.CharField(max_length=80, blank=True, default="Dubai")
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=120, blank=True)
    trn = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="TRN / Tax number",
        help_text="UAE Tax Registration Number (or local equivalent)",
    )
    logo = models.ImageField(
        upload_to="company/",
        blank=True,
        null=True,
        help_text="Used on payslip PDF header",
    )
    default_currency = models.CharField(
        max_length=8,
        choices=CURRENCY_CHOICES,
        default=FALLBACK_DEFAULT,
        help_text="Used for new salary structures and payroll",
    )
    cycle_start_day = models.PositiveSmallIntegerField(
        "Attendance cycle",
        default=1,
        help_text=(
            "Attendance & payroll cycle start day (1 = calendar month). "
            "Example: 25 means each period runs 25th → 24th next month."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization settings"
        verbose_name_plural = "Organization settings"

    def __str__(self):
        return self.company_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.legal_name or self.company_name

    @property
    def address_block(self):
        parts = [
            p
            for p in (
                self.address_line1,
                self.address_line2,
                ", ".join(x for x in (self.city, self.country) if x),
            )
            if p
        ]
        return "\n".join(parts)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "company_name": "Day Pay Company",
                "country": "United Arab Emirates",
                "city": "Dubai",
                "default_currency": FALLBACK_DEFAULT,
            },
        )
        return obj
