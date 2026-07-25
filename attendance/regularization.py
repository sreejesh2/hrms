"""Attendance regularization — request, approve, reject, apply to DailyAttendance."""

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.mail import notify_user
from notifications.models import Notification
from workflows.models import ApprovalRequest

from .models import AttendanceRegularization, DailyAttendance


def employee_for_user(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, "employee_profile", None)


def resolve_assignee_user(employee):
    """Prefer reporting manager's user account; else None (HR queue still sees it)."""
    manager = getattr(employee, "manager", None)
    if manager and manager.user_id:
        return manager.user
    return None


def notify(user, *, title, body="", level=Notification.Level.INFO, link=""):
    notify_user(user, title=title, body=body, level=level, link=link)


@transaction.atomic
def submit_regularization(
    *,
    employee,
    on_date,
    requested_status,
    reason,
    requested_by,
    requested_worked_hours=None,
    lock_on_approve=True,
):
    if AttendanceRegularization.objects.filter(
        employee=employee,
        date=on_date,
        status=AttendanceRegularization.Status.PENDING,
    ).exists():
        raise ValueError("A pending request already exists for this employee and date.")

    attendance = DailyAttendance.objects.filter(employee=employee, date=on_date).first()
    current = attendance.status if attendance else ""

    req = AttendanceRegularization.objects.create(
        employee=employee,
        date=on_date,
        attendance=attendance,
        current_status=current,
        requested_status=requested_status,
        requested_worked_hours=requested_worked_hours,
        reason=reason.strip(),
        lock_on_approve=lock_on_approve,
        requested_by=requested_by,
        status=AttendanceRegularization.Status.PENDING,
    )

    assignee = resolve_assignee_user(employee)
    approval = ApprovalRequest.objects.create(
        title=f"Attendance regularization · {employee.employee_code} · {on_date}",
        module="attendance_regularization",
        object_id=req.pk,
        requester=requested_by,
        assignee=assignee,
        status=ApprovalRequest.Status.PENDING,
        notes=reason.strip()[:500],
    )
    req.approval = approval
    req.save(update_fields=["approval", "updated_at"])

    detail = reverse("attendance_ops:regularization_detail", args=[req.pk])
    notify(
        assignee,
        title="Attendance correction requested",
        body=f"{employee.full_name} asked to change {on_date} to {req.get_requested_status_display()}.",
        level=Notification.Level.INFO,
        link=detail,
    )
    return req


@transaction.atomic
def approve_regularization(req, *, reviewer, notes=""):
    if req.status != AttendanceRegularization.Status.PENDING:
        raise ValueError("Only pending requests can be approved.")

    attendance = DailyAttendance.objects.filter(
        employee=req.employee, date=req.date
    ).first()
    if attendance is None:
        attendance = DailyAttendance(employee=req.employee, date=req.date)

    attendance.status = req.requested_status
    if req.requested_worked_hours is not None:
        attendance.worked_hours = req.requested_worked_hours
    if notes.strip():
        note = notes.strip()
        attendance.notes = (
            f"{attendance.notes} | Regularized: {note}".strip(" |")
            if attendance.notes
            else f"Regularized: {note}"
        )[:255]
    elif not attendance.notes:
        attendance.notes = f"Regularized: {req.reason[:200]}"[:255]

    if req.lock_on_approve:
        attendance.is_locked = True

    attendance.save()

    req.attendance = attendance
    req.status = AttendanceRegularization.Status.APPROVED
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.reviewer_notes = notes.strip()
    req.save()

    if req.approval_id:
        req.approval.status = ApprovalRequest.Status.APPROVED
        req.approval.decided_at = timezone.now()
        req.approval.notes = notes.strip() or req.approval.notes
        req.approval.save(update_fields=["status", "decided_at", "notes"])

    detail = reverse("attendance_ops:regularization_detail", args=[req.pk])
    notify(
        req.requested_by,
        title="Attendance correction approved",
        body=f"{req.date} for {req.employee.employee_code} is now {req.get_requested_status_display()}.",
        level=Notification.Level.SUCCESS,
        link=detail,
    )
    return req


@transaction.atomic
def reject_regularization(req, *, reviewer, notes=""):
    if req.status != AttendanceRegularization.Status.PENDING:
        raise ValueError("Only pending requests can be rejected.")

    req.status = AttendanceRegularization.Status.REJECTED
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.reviewer_notes = notes.strip()
    req.save()

    if req.approval_id:
        req.approval.status = ApprovalRequest.Status.REJECTED
        req.approval.decided_at = timezone.now()
        req.approval.notes = notes.strip() or req.approval.notes
        req.approval.save(update_fields=["status", "decided_at", "notes"])

    detail = reverse("attendance_ops:regularization_detail", args=[req.pk])
    notify(
        req.requested_by,
        title="Attendance correction rejected",
        body=notes.strip()
        or f"Your request for {req.date} ({req.employee.employee_code}) was rejected.",
        level=Notification.Level.WARNING,
        link=detail,
    )
    return req


@transaction.atomic
def cancel_regularization(req, *, user):
    if req.status != AttendanceRegularization.Status.PENDING:
        raise ValueError("Only pending requests can be cancelled.")
    if req.requested_by_id != user.id:
        raise ValueError("Only the requester can cancel this request.")

    req.status = AttendanceRegularization.Status.CANCELLED
    req.reviewed_by = user
    req.reviewed_at = timezone.now()
    req.save()

    if req.approval_id:
        req.approval.status = ApprovalRequest.Status.CANCELLED
        req.approval.decided_at = timezone.now()
        req.approval.save(update_fields=["status", "decided_at"])
    return req
