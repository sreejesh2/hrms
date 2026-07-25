from django.conf import settings
from django.db import models
from django.db.models import Q

from core.query import RelatedManager, RelatedQuerySet


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CodeDescriptionModel(TimeStampedModel):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    description = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} — {self.description}"


class Division(CodeDescriptionModel):
    pass


class Department(CodeDescriptionModel):
    division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments",
        help_text="Optional parent division",
    )
    default_shift = models.ForeignKey(
        "attendance.WorkShift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_departments",
        help_text="Assigned automatically to new employees in this department",
    )
    default_calendar = models.ForeignKey(
        "attendance.WorkCalendar",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_departments",
        help_text="Optional work calendar paired with the default shift",
    )


class Location(CodeDescriptionModel):
    pass


class Position(CodeDescriptionModel):
    pass


class Bank(CodeDescriptionModel):
    pass


class EmployeeQuerySet(RelatedQuerySet):
    list_select_related = (
        "department",
        "division",
        "location",
        "position",
        "user",
        "manager",
    )
    detail_select_related = list_select_related + ("bank",)
    detail_prefetch_related = ("documents", "attribute_values__definition")

    def active(self):
        return self.filter(status=Employee.Status.ACTIVE)

    def on_vacation(self):
        """Placeholder until leave module lands — flag-based for now."""
        return self.filter(status=Employee.Status.ON_LEAVE)


class EmployeeManager(RelatedManager):
    def get_queryset(self):
        return EmployeeQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active().for_list()

    def on_vacation(self):
        return self.get_queryset().on_vacation().for_list()


class Employee(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Onboarding"
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On vacation"
        INACTIVE = "inactive", "Inactive"
        TERMINATED = "terminated", "Terminated"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile",
    )
    employee_code = models.CharField(max_length=32, unique=True, db_index=True)
    biometric_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="ID enrolled on punch machines (PIN / badge / device user id)",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone_country_code = models.CharField(max_length=8, blank=True, default="+91")
    phone = models.CharField(max_length=20, blank=True, help_text="Local number without country code")
    date_of_joining = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )
    division = models.ForeignKey(
        Division, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )
    position = models.ForeignKey(
        Position, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )
    bank = models.ForeignKey(
        Bank, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )
    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )

    objects = EmployeeManager()

    class Meta:
        ordering = ("employee_code",)
        indexes = [
            models.Index(fields=["status", "department"]),
            models.Index(fields=["last_name", "first_name"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["biometric_id"],
                condition=~Q(biometric_id=""),
                name="uniq_employee_biometric_id",
            )
        ]

    def __str__(self):
        return f"{self.employee_code} — {self.full_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def phone_display(self):
        local = (self.phone or "").strip()
        if not local:
            return ""
        code = (self.phone_country_code or "").strip()
        if code and not local.startswith("+"):
            return f"{code} {local}"
        return local


class EmployeeDocument(TimeStampedModel):
    class Category(models.TextChoices):
        ID_PROOF = "id_proof", "ID proof"
        CONTRACT = "contract", "Contract"
        CERTIFICATE = "certificate", "Certificate"
        EDUCATION = "education", "Education"
        MEDICAL = "medical", "Medical"
        OTHER = "other", "Other"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="documents", db_index=True
    )
    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=32, choices=Category.choices, default=Category.OTHER, db_index=True
    )
    file = models.FileField(upload_to="employee_docs/%Y/%m/")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title


class OnboardingChecklist(TimeStampedModel):
    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name="onboarding"
    )
    personal_info_done = models.BooleanField(default=False)
    documents_done = models.BooleanField(default=False)
    bank_done = models.BooleanField(default=False)
    shift_assigned = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Onboarding: {self.employee}"

    @property
    def progress_pct(self):
        steps = [
            self.personal_info_done,
            self.documents_done,
            self.bank_done,
            self.shift_assigned,
        ]
        return int(100 * sum(1 for s in steps if s) / len(steps))


class EmployeeAttributeDefinition(TimeStampedModel):
    """
    HR-defined extra employee fields (dynamic attributes).
    Example: Blood group, Emergency contact, Aadhaar, Uniform size.
    """

    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        TEXTAREA = "textarea", "Long text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        BOOLEAN = "boolean", "Yes / No"
        SELECT = "select", "Dropdown"

    key = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Stable id used in code (auto from label if blank).",
    )
    label = models.CharField(max_length=120)
    field_type = models.CharField(
        max_length=20, choices=FieldType.choices, default=FieldType.TEXT
    )
    help_text = models.CharField(max_length=255, blank=True)
    required = models.BooleanField(default=False)
    # For SELECT: store options as JSON list of strings
    choices = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("sort_order", "label")

    def __str__(self):
        return self.label

    def choice_list(self):
        if isinstance(self.choices, list):
            return [str(c) for c in self.choices]
        return []


class EmployeeAttributeValue(TimeStampedModel):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attribute_values",
        db_index=True,
    )
    definition = models.ForeignKey(
        EmployeeAttributeDefinition,
        on_delete=models.CASCADE,
        related_name="values",
        db_index=True,
    )
    value = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "definition"],
                name="uniq_employee_attribute",
            )
        ]
        indexes = [
            models.Index(fields=["definition", "employee"]),
        ]

    def __str__(self):
        return f"{self.employee_id}:{self.definition.key}={self.value[:40]}"

