from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

RATING_CHOICES = [
    (1, "1 · Needs improvement"),
    (2, "2 · Developing"),
    (3, "3 · Meets expectations"),
    (4, "4 · Exceeds expectations"),
    (5, "5 · Outstanding"),
]


def rating_field():
    return models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=RATING_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )


class ReviewCycle(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    self_review_due = models.DateField(
        help_text="Deadline for employees to submit their self-review"
    )
    manager_review_due = models.DateField(
        help_text="Deadline for managers to submit their review"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performance_cycles_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start_date", "code")
        indexes = [
            models.Index(fields=["status", "-start_date"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    @property
    def review_count(self):
        return self.reviews.count()

    @property
    def completed_review_count(self):
        return self.reviews.filter(status=PerformanceReview.Status.COMPLETED).count()


class Competency(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name_plural = "competencies"

    def __str__(self):
        return self.name


class PerformanceReviewQuerySet(models.QuerySet):
    def for_employee(self, employee):
        return self.filter(employee=employee)

    def for_manager(self, employee):
        return self.filter(manager=employee)

    def relevant_to(self, employee):
        return self.filter(models.Q(employee=employee) | models.Q(manager=employee))


class PerformanceReview(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SELF_SUBMITTED = "self_submitted", "Self-review submitted"
        MANAGER_SUBMITTED = "manager_submitted", "Manager review submitted"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    cycle = models.ForeignKey(
        ReviewCycle, on_delete=models.CASCADE, related_name="reviews", db_index=True
    )
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="performance_reviews",
        db_index=True,
    )
    manager = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performance_reviews_managed",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    overall_self_rating = rating_field()
    overall_manager_rating = rating_field()
    self_summary = models.TextField(blank=True, default="")
    manager_summary = models.TextField(blank=True, default="")
    employee_goals = models.TextField(
        blank=True, default="", help_text="Goals set by / for the employee this cycle"
    )
    development_plan = models.TextField(
        blank=True, default="", help_text="Manager's development plan for the employee"
    )
    self_submitted_at = models.DateTimeField(null=True, blank=True)
    manager_submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PerformanceReviewQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "employee"], name="uniq_performance_review_cycle_employee"
            )
        ]
        indexes = [
            models.Index(fields=["cycle", "status"]),
            models.Index(fields=["employee", "-created_at"]),
            models.Index(fields=["manager", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.employee_id} · {self.cycle_id} ({self.status})"

    @property
    def is_self_editable(self):
        return self.cycle.is_open and self.status not in (
            self.Status.COMPLETED,
            self.Status.CANCELLED,
        )

    @property
    def is_manager_editable(self):
        return self.cycle.is_open and self.status not in (
            self.Status.COMPLETED,
            self.Status.CANCELLED,
        )

    @property
    def can_complete(self):
        return self.cycle.is_open and self.status == self.Status.MANAGER_SUBMITTED

    def self_average_rating(self):
        scores = [s.self_rating for s in self.competency_scores.all() if s.self_rating]
        return round(sum(scores) / len(scores), 1) if scores else None

    def manager_average_rating(self):
        scores = [s.manager_rating for s in self.competency_scores.all() if s.manager_rating]
        return round(sum(scores) / len(scores), 1) if scores else None


class ReviewCompetencyScore(models.Model):
    review = models.ForeignKey(
        PerformanceReview,
        on_delete=models.CASCADE,
        related_name="competency_scores",
        db_index=True,
    )
    competency = models.ForeignKey(
        Competency, on_delete=models.CASCADE, related_name="scores"
    )
    self_rating = rating_field()
    manager_rating = rating_field()
    self_comment = models.TextField(blank=True, default="")
    manager_comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("competency__sort_order", "competency__name")
        constraints = [
            models.UniqueConstraint(
                fields=["review", "competency"], name="uniq_review_competency_score"
            )
        ]
        indexes = [
            models.Index(fields=["review"]),
        ]

    def __str__(self):
        return f"{self.review_id} · {self.competency.code}"
