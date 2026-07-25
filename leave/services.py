"""Leave apply / approve / balance helpers."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from attendance.models import DailyAttendance
from notifications.mail import notify_user
from notifications.models import Notification
from workflows.models import ApprovalRequest

from .models import LeaveBalance, LeaveRequest, LeaveType


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


def calc_leave_days(start_date, end_date, *, is_half_day=False) -> Decimal:
    if end_date < start_date:
        raise ValueError("End date must be on or after start date.")
    if is_half_day:
        if start_date != end_date:
            raise ValueError("Half day is only for a single date.")
        return Decimal("0.5")
    return Decimal(str((end_date - start_date).days + 1))


def get_or_create_balance(employee, leave_type, year):
    bal, created = LeaveBalance.objects.get_or_create(
        employee=employee,
        leave_type=leave_type,
        year=year,
        defaults={"entitled": leave_type.default_entitlement},
    )
    return bal


def overlapping_requests(employee, start_date, end_date, *, exclude_pk=None):
    qs = LeaveRequest.objects.filter(
        employee=employee,
        status__in=[
            LeaveRequest.Status.PENDING,
            LeaveRequest.Status.APPROVED,
        ],
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs


def iter_dates(start_date, end_date):
    cur = start_date
    while cur <= end_date:
        yield cur
        cur += timedelta(days=1)


@transaction.atomic
def submit_leave(
    *,
    employee,
    leave_type,
    start_date,
    end_date,
    reason,
    requested_by,
    is_half_day=False,
    apply_to_attendance=True,
):
    if not leave_type.is_active:
        raise ValueError("This leave type is inactive.")

    days = calc_leave_days(start_date, end_date, is_half_day=is_half_day)
    if overlapping_requests(employee, start_date, end_date).exists():
        raise ValueError("Overlapping pending/approved leave already exists for these dates.")

    year = start_date.year
    balance = get_or_create_balance(employee, leave_type, year)
    if balance.available < days:
        raise ValueError(
            f"Insufficient balance for {leave_type.code} {year}: "
            f"available {balance.available}, requested {days}."
        )

    req = LeaveRequest.objects.create(
        employee=employee,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        days=days,
        is_half_day=is_half_day,
        reason=reason.strip(),
        requested_by=requested_by,
        apply_to_attendance=apply_to_attendance,
        status=LeaveRequest.Status.PENDING,
    )

    balance.pending = balance.pending + days
    balance.save(update_fields=["pending", "updated_at"])

    assignee = resolve_assignee_user(employee)
    if leave_type.requires_approval:
        approval = ApprovalRequest.objects.create(
            title=f"Leave · {employee.employee_code} · {start_date} → {end_date}",
            module="leave",
            object_id=req.pk,
            requester=requested_by,
            assignee=assignee,
            status=ApprovalRequest.Status.PENDING,
            notes=reason.strip()[:500],
        )
        req.approval = approval
        req.save(update_fields=["approval", "updated_at"])
        detail = reverse("leave:detail", args=[req.pk])
        notify(
            assignee,
            title="Leave request pending",
            body=f"{employee.full_name} requested {days} day(s) ({leave_type.name}).",
            link=detail,
        )
    else:
        # Auto-approve types (e.g. some unpaid policies)
        return approve_leave(req, reviewer=requested_by, notes="Auto-approved")

    return req


def _apply_attendance_on_leave(req):
    if not req.apply_to_attendance:
        return
    for day in iter_dates(req.start_date, req.end_date):
        row, _ = DailyAttendance.objects.get_or_create(
            employee=req.employee,
            date=day,
            defaults={"status": DailyAttendance.Status.ON_LEAVE},
        )
        if row.is_locked and row.status == DailyAttendance.Status.ON_LEAVE:
            continue
        # Approved leave wins; unlock briefly then set + lock
        row.status = DailyAttendance.Status.ON_LEAVE
        if req.is_half_day:
            row.status = DailyAttendance.Status.HALF_DAY
            row.notes = (row.notes + " | Half-day leave").strip(" |")[:255]
        else:
            note = f"Leave: {req.leave_type.code}"
            row.notes = (f"{row.notes} | {note}" if row.notes else note)[:255]
        row.is_locked = True
        row.save()


@transaction.atomic
def approve_leave(req, *, reviewer, notes=""):
    if req.status != LeaveRequest.Status.PENDING:
        raise ValueError("Only pending leave can be approved.")

    balance = get_or_create_balance(req.employee, req.leave_type, req.start_date.year)
    # pending should already hold these days
    if balance.pending < req.days:
        # repair: still allow approve if available overall
        if balance.available + balance.pending < req.days:
            raise ValueError("Insufficient leave balance to approve.")

    balance.pending = max(Decimal("0.0"), balance.pending - req.days)
    balance.used = balance.used + req.days
    balance.save(update_fields=["pending", "used", "updated_at"])

    req.status = LeaveRequest.Status.APPROVED
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.reviewer_notes = notes.strip()
    req.save()

    if req.approval_id:
        req.approval.status = ApprovalRequest.Status.APPROVED
        req.approval.decided_at = timezone.now()
        req.approval.notes = notes.strip() or req.approval.notes
        req.approval.save(update_fields=["status", "decided_at", "notes"])

    _apply_attendance_on_leave(req)

    detail = reverse("leave:detail", args=[req.pk])
    notify(
        req.requested_by,
        title="Leave approved",
        body=f"{req.start_date} → {req.end_date} ({req.days} day(s)) approved.",
        level=Notification.Level.SUCCESS,
        link=detail,
    )
    return req


@transaction.atomic
def reject_leave(req, *, reviewer, notes=""):
    if req.status != LeaveRequest.Status.PENDING:
        raise ValueError("Only pending leave can be rejected.")

    balance = get_or_create_balance(req.employee, req.leave_type, req.start_date.year)
    balance.pending = max(Decimal("0.0"), balance.pending - req.days)
    balance.save(update_fields=["pending", "updated_at"])

    req.status = LeaveRequest.Status.REJECTED
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.reviewer_notes = notes.strip()
    req.save()

    if req.approval_id:
        req.approval.status = ApprovalRequest.Status.REJECTED
        req.approval.decided_at = timezone.now()
        req.approval.notes = notes.strip() or req.approval.notes
        req.approval.save(update_fields=["status", "decided_at", "notes"])

    detail = reverse("leave:detail", args=[req.pk])
    notify(
        req.requested_by,
        title="Leave rejected",
        body=notes.strip() or f"Your leave {req.start_date} → {req.end_date} was rejected.",
        level=Notification.Level.WARNING,
        link=detail,
    )
    return req


@transaction.atomic
def cancel_leave(req, *, user):
    if req.status != LeaveRequest.Status.PENDING:
        raise ValueError("Only pending leave can be cancelled.")
    if req.requested_by_id != user.id:
        raise ValueError("Only the requester can cancel this leave.")

    balance = get_or_create_balance(req.employee, req.leave_type, req.start_date.year)
    balance.pending = max(Decimal("0.0"), balance.pending - req.days)
    balance.save(update_fields=["pending", "updated_at"])

    req.status = LeaveRequest.Status.CANCELLED
    req.reviewed_by = user
    req.reviewed_at = timezone.now()
    req.save()

    if req.approval_id:
        req.approval.status = ApprovalRequest.Status.CANCELLED
        req.approval.decided_at = timezone.now()
        req.approval.save(update_fields=["status", "decided_at"])
    return req


def seed_default_leave_types():
    defaults = [
        ("CL", "Casual Leave", Decimal("12.0"), True),
        ("SL", "Sick Leave", Decimal("10.0"), True),
        ("EL", "Earned Leave", Decimal("15.0"), True),
        ("LWP", "Leave Without Pay", Decimal("0.0"), False),
    ]
    for code, name, entitled, paid in defaults:
        LeaveType.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "is_paid": paid,
                "requires_approval": True,
                "default_entitlement": entitled,
                "is_active": True,
            },
        )
