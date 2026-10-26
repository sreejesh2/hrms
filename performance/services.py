"""Review cycle lifecycle, review generation, and submit/complete workflow."""

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.mail import notify_user
from notifications.models import Notification
from people.models import Employee

from .models import Competency, PerformanceReview, ReviewCompetencyScore, ReviewCycle

DEFAULT_COMPETENCIES = [
    ("COMMUNICATION", "Communication", "Shares information clearly and listens well", 10),
    ("OWNERSHIP", "Ownership", "Takes accountability and follows through", 20),
    ("DELIVERY", "Delivery", "Ships quality work reliably and on time", 30),
    ("TEAMWORK", "Teamwork", "Collaborates and supports the wider team", 40),
    ("LEADERSHIP", "Leadership", "Guides, mentors, and influences positively", 50),
]


def seed_default_competencies():
    for code, name, description, sort_order in DEFAULT_COMPETENCIES:
        Competency.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


def employee_for_user(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, "employee_profile", None)


def notify(user, *, title, body="", level=Notification.Level.INFO, link=""):
    notify_user(user, title=title, body=body, level=level, link=link)


def _review_link(review):
    return reverse("performance:detail", args=[review.pk])


@transaction.atomic
def open_cycle(cycle):
    if cycle.status == ReviewCycle.Status.CLOSED:
        raise ValueError("A closed cycle cannot be reopened.")
    if cycle.status == ReviewCycle.Status.OPEN:
        return cycle
    cycle.status = ReviewCycle.Status.OPEN
    cycle.save(update_fields=["status", "updated_at"])
    return cycle


@transaction.atomic
def close_cycle(cycle):
    if cycle.status != ReviewCycle.Status.OPEN:
        raise ValueError("Only an open cycle can be closed.")
    cycle.status = ReviewCycle.Status.CLOSED
    cycle.save(update_fields=["status", "updated_at"])
    return cycle


@transaction.atomic
def ensure_reviews_for_cycle(cycle):
    """Create a PerformanceReview (+ competency score rows) for every active employee."""
    competencies = list(Competency.objects.filter(is_active=True))
    employees = Employee.objects.filter(status=Employee.Status.ACTIVE)

    created = 0
    already_existed = 0
    for emp in employees:
        review, was_created = PerformanceReview.objects.get_or_create(
            cycle=cycle,
            employee=emp,
            defaults={"manager": emp.manager},
        )
        if was_created:
            created += 1
        else:
            already_existed += 1
            if review.status == PerformanceReview.Status.DRAFT and review.manager_id != emp.manager_id:
                review.manager = emp.manager
                review.save(update_fields=["manager", "updated_at"])

        for comp in competencies:
            ReviewCompetencyScore.objects.get_or_create(review=review, competency=comp)

    return {
        "created": created,
        "existing": already_existed,
        "employees": employees.count(),
    }


@transaction.atomic
def submit_self_review(
    review,
    *,
    overall_self_rating=None,
    self_summary="",
    employee_goals="",
    competency_scores=None,
):
    if review.cycle.status != ReviewCycle.Status.OPEN:
        raise ValueError("This review cycle is not open.")
    if review.status in (PerformanceReview.Status.COMPLETED, PerformanceReview.Status.CANCELLED):
        raise ValueError("This review is already closed.")

    review.overall_self_rating = overall_self_rating
    review.self_summary = (self_summary or "").strip()
    review.employee_goals = (employee_goals or "").strip()
    review.self_submitted_at = timezone.now()
    if review.status == PerformanceReview.Status.DRAFT:
        review.status = PerformanceReview.Status.SELF_SUBMITTED
    review.save()

    for score in competency_scores or []:
        score.save()

    if review.manager and review.manager.user_id:
        notify(
            review.manager.user,
            title="Self-review submitted",
            body=f"{review.employee.full_name} submitted their self-review for {review.cycle.name}.",
            link=_review_link(review),
        )
    return review


@transaction.atomic
def submit_manager_review(
    review,
    *,
    overall_manager_rating=None,
    manager_summary="",
    development_plan="",
    competency_scores=None,
):
    if review.cycle.status != ReviewCycle.Status.OPEN:
        raise ValueError("This review cycle is not open.")
    if review.status in (PerformanceReview.Status.COMPLETED, PerformanceReview.Status.CANCELLED):
        raise ValueError("This review is already closed.")

    review.overall_manager_rating = overall_manager_rating
    review.manager_summary = (manager_summary or "").strip()
    review.development_plan = (development_plan or "").strip()
    review.manager_submitted_at = timezone.now()
    review.status = PerformanceReview.Status.MANAGER_SUBMITTED
    review.save()

    for score in competency_scores or []:
        score.save()

    if review.employee.user_id:
        notify(
            review.employee.user,
            title="Manager review submitted",
            body=f"Your manager submitted their review for {review.cycle.name}.",
            link=_review_link(review),
        )
    return review


@transaction.atomic
def complete_review(review, *, actor=None):
    if review.status != PerformanceReview.Status.MANAGER_SUBMITTED:
        raise ValueError("The manager review must be submitted before completing.")

    review.status = PerformanceReview.Status.COMPLETED
    review.completed_at = timezone.now()
    review.save()

    recipients = []
    if review.employee.user_id:
        recipients.append(review.employee.user)
    if review.manager and review.manager.user_id and review.manager.user_id != review.employee.user_id:
        recipients.append(review.manager.user)
    for user in recipients:
        notify(
            user,
            title="Performance review completed",
            body=f"{review.cycle.name} review for {review.employee.full_name} is finalized.",
            level=Notification.Level.SUCCESS,
            link=_review_link(review),
        )
    return review
