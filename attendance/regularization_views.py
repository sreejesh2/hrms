"""Attendance regularization UI."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import any_permission_required, request_has_perm
from core.pagination import paginate

from .forms import RegularizationDecisionForm, RegularizationRequestForm
from .models import AttendanceRegularization, DailyAttendance
from .regularization import (
    approve_regularization,
    cancel_regularization,
    employee_for_user,
    reject_regularization,
    submit_regularization,
)


def _can_approve(request, req=None):
    if not (
        request_has_perm(request, "attendance.manage")
        or request_has_perm(request, "attendance.approve_regularization")
    ):
        return False
    if req is None:
        return True
    if request_has_perm(request, "attendance.manage"):
        return True
    me = employee_for_user(request.user)
    if req.approval_id and req.approval.assignee_id == request.user.id:
        return True
    if me and req.employee.manager_id == me.pk:
        return True
    return False


def _can_view(request, req):
    if request_has_perm(request, "attendance.manage"):
        return True
    if req.requested_by_id == request.user.id:
        return True
    me = employee_for_user(request.user)
    if me and req.employee_id == me.pk:
        return True
    return _can_approve(request, req)


@any_permission_required(
    "attendance.request_regularization",
    "attendance.approve_regularization",
    "attendance.manage",
    "attendance.view",
)
def regularization_list(request):
    qs = AttendanceRegularization.objects.select_related(
        "employee",
        "employee__department",
        "requested_by",
        "reviewed_by",
        "attendance",
    )
    status = request.GET.get("status", "").strip()
    scope = request.GET.get("scope", "").strip() or "relevant"
    q = request.GET.get("q", "").strip()

    me = employee_for_user(request.user)
    can_manage = request_has_perm(request, "attendance.manage")
    can_approve = request_has_perm(request, "attendance.approve_regularization") or can_manage

    if can_manage and scope == "all":
        pass
    elif scope == "mine":
        qs = qs.filter(Q(requested_by=request.user) | Q(employee=me))
    elif scope == "pending" and can_approve:
        qs = qs.filter(status=AttendanceRegularization.Status.PENDING)
        if not can_manage and me:
            qs = qs.filter(
                Q(employee__manager=me) | Q(approval__assignee=request.user)
            )
        elif not can_manage and not me:
            qs = qs.filter(approval__assignee=request.user)
    elif can_manage:
        pass  # relevant for HR = all
    else:
        filters = Q(requested_by=request.user)
        if me:
            filters |= Q(employee=me)
        if can_approve and me:
            filters |= Q(employee__manager=me) | Q(approval__assignee=request.user)
        elif can_approve:
            filters |= Q(approval__assignee=request.user)
        qs = qs.filter(filters)

    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(reason__icontains=q)
        )

    pending_count = 0
    if can_approve:
        pqs = AttendanceRegularization.objects.filter(
            status=AttendanceRegularization.Status.PENDING
        )
        if not can_manage and me:
            pqs = pqs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        pending_count = pqs.count()

    page_obj = paginate(request, qs)
    return render(
        request,
        "attendance/regularization_list.html",
        {
            "page_title": "Attendance regularization",
            "page_obj": page_obj,
            "rows": page_obj,
            "status": status,
            "scope": scope,
            "q": q,
            "statuses": AttendanceRegularization.Status.choices,
            "pending_count": pending_count,
            "can_request": request_has_perm(request, "attendance.request_regularization")
            or can_manage,
            "can_manage": can_manage,
            "can_approve": can_approve,
        },
    )


@any_permission_required("attendance.request_regularization", "attendance.manage")
@require_http_methods(["GET", "POST"])
def regularization_create(request):
    allow_pick = request_has_perm(request, "attendance.manage")
    initial = {}
    if request.GET.get("date"):
        initial["date"] = request.GET.get("date")
    if request.GET.get("employee"):
        initial["employee"] = request.GET.get("employee")
    if request.GET.get("status"):
        initial["requested_status"] = request.GET.get("status")

    # Prefill current status hint
    prefill_attendance = None
    emp_id = request.GET.get("employee") or (
        None if allow_pick else getattr(employee_for_user(request.user), "pk", None)
    )
    day = request.GET.get("date")
    if emp_id and day:
        prefill_attendance = DailyAttendance.objects.filter(
            employee_id=emp_id, date=day
        ).first()
        if prefill_attendance and "requested_status" not in initial:
            initial["requested_status"] = prefill_attendance.status

    form = RegularizationRequestForm(
        request.POST or None,
        user=request.user,
        allow_pick_employee=allow_pick,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        try:
            req = submit_regularization(
                employee=form.cleaned_data["employee"],
                on_date=form.cleaned_data["date"],
                requested_status=form.cleaned_data["requested_status"],
                reason=form.cleaned_data["reason"],
                requested_by=request.user,
                requested_worked_hours=form.cleaned_data.get("requested_worked_hours"),
                lock_on_approve=form.cleaned_data.get("lock_on_approve", True),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Correction request submitted for approval.")
            return redirect("attendance_ops:regularization_detail", pk=req.pk)

    return render(
        request,
        "attendance/regularization_form.html",
        {
            "page_title": "Request attendance correction",
            "form": form,
            "prefill_attendance": prefill_attendance,
            "allow_pick": allow_pick,
        },
    )


@any_permission_required(
    "attendance.request_regularization",
    "attendance.approve_regularization",
    "attendance.manage",
    "attendance.view",
)
@require_http_methods(["GET", "POST"])
def regularization_detail(request, pk):
    req = get_object_or_404(
        AttendanceRegularization.objects.select_related(
            "employee",
            "employee__department",
            "employee__manager",
            "requested_by",
            "reviewed_by",
            "attendance",
            "approval",
        ),
        pk=pk,
    )
    if not _can_view(request, req):
        messages.error(request, "You do not have access to this request.")
        return redirect("attendance_ops:regularization_list")

    decision = RegularizationDecisionForm(request.POST or None)
    can_approve = _can_approve(request, req) and req.status == AttendanceRegularization.Status.PENDING
    can_cancel = (
        req.status == AttendanceRegularization.Status.PENDING
        and req.requested_by_id == request.user.id
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("approve", "reject") and not can_approve:
            messages.error(request, "You cannot decide this request.")
            return redirect("attendance_ops:regularization_detail", pk=pk)
        if action == "cancel" and not can_cancel:
            messages.error(request, "You cannot cancel this request.")
            return redirect("attendance_ops:regularization_detail", pk=pk)

        if action in ("approve", "reject") and decision.is_valid():
            notes = decision.cleaned_data.get("notes") or ""
            try:
                if action == "approve":
                    approve_regularization(req, reviewer=request.user, notes=notes)
                    messages.success(request, "Request approved — attendance updated.")
                else:
                    reject_regularization(req, reviewer=request.user, notes=notes)
                    messages.success(request, "Request rejected.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect("attendance_ops:regularization_detail", pk=pk)

        if action == "cancel":
            try:
                cancel_regularization(req, user=request.user)
                messages.success(request, "Request cancelled.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect("attendance_ops:regularization_detail", pk=pk)

    return render(
        request,
        "attendance/regularization_detail.html",
        {
            "page_title": f"Correction · {req.employee.employee_code}",
            "req": req,
            "decision": decision,
            "can_approve": can_approve,
            "can_cancel": can_cancel,
        },
    )
