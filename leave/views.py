from django.urls import reverse
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.permissions import any_permission_required, permission_required, request_has_perm
from core.pagination import paginate
from people.models import Employee

from .forms import LeaveBalanceForm, LeaveDecisionForm, LeaveRequestForm, LeaveTypeForm
from .models import LeaveBalance, LeaveRequest, LeaveType
from .services import (
    approve_leave,
    cancel_leave,
    employee_for_user,
    reject_leave,
    submit_leave,
)


def _can_approve(request, req=None):
    if not (
        request_has_perm(request, "leave.manage")
        or request_has_perm(request, "leave.approve")
    ):
        return False
    if req is None:
        return True
    if request_has_perm(request, "leave.manage"):
        return True
    me = employee_for_user(request.user)
    if req.approval_id and req.approval.assignee_id == request.user.id:
        return True
    if me and req.employee.manager_id == me.pk:
        return True
    return False


def _can_view(request, req):
    if request_has_perm(request, "leave.manage"):
        return True
    if req.requested_by_id == request.user.id:
        return True
    me = employee_for_user(request.user)
    if me and req.employee_id == me.pk:
        return True
    return _can_approve(request, req)


@any_permission_required("leave.view", "leave.request", "leave.manage", "leave.approve")
def leave_list(request):
    qs = LeaveRequest.objects.select_related(
        "employee", "leave_type", "requested_by", "reviewed_by"
    )
    status = request.GET.get("status", "").strip()
    scope = request.GET.get("scope", "").strip() or "relevant"
    q = request.GET.get("q", "").strip()

    me = employee_for_user(request.user)
    can_manage = request_has_perm(request, "leave.manage")
    can_approve = request_has_perm(request, "leave.approve") or can_manage

    if can_manage and scope == "all":
        pass
    elif scope == "mine":
        qs = qs.filter(Q(requested_by=request.user) | Q(employee=me))
    elif scope == "pending" and can_approve:
        qs = qs.filter(status=LeaveRequest.Status.PENDING)
        if not can_manage and me:
            qs = qs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        elif not can_manage:
            qs = qs.filter(approval__assignee=request.user)
    elif can_manage:
        pass
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
            | Q(leave_type__code__icontains=q)
        )

    pending_count = 0
    if can_approve:
        pqs = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING)
        if not can_manage and me:
            pqs = pqs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        pending_count = pqs.count()

    page_obj = paginate(request, qs)
    return render(
        request,
        "leave/list.html",
        {
            "page_title": "Leave requests",
            "page_obj": page_obj,
            "rows": page_obj,
            "status": status,
            "scope": scope,
            "q": q,
            "statuses": LeaveRequest.Status.choices,
            "pending_count": pending_count,
            "can_request": request_has_perm(request, "leave.request") or can_manage,
            "can_manage": can_manage,
            "can_approve": can_approve,
        },
    )


@any_permission_required("leave.request", "leave.manage")
@require_http_methods(["GET", "POST"])
def leave_create(request):
    allow_pick = request_has_perm(request, "leave.manage")
    form = LeaveRequestForm(
        request.POST or None,
        user=request.user,
        allow_pick_employee=allow_pick,
    )
    if request.method == "POST" and form.is_valid():
        try:
            req = submit_leave(
                employee=form.cleaned_data["employee"],
                leave_type=form.cleaned_data["leave_type"],
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                reason=form.cleaned_data["reason"],
                requested_by=request.user,
                is_half_day=form.cleaned_data.get("is_half_day", False),
                apply_to_attendance=form.cleaned_data.get("apply_to_attendance", True),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Leave request submitted.")
            return redirect("leave:detail", pk=req.pk)

    my_balances = []
    me = employee_for_user(request.user)
    if me:
        my_balances = LeaveBalance.objects.filter(
            employee=me, year=timezone.localdate().year
        ).select_related("leave_type")

    return render(
        request,
        "leave/form.html",
        {
            "page_title": "Apply for leave",
            "form": form,
            "allow_pick": allow_pick,
            "my_balances": my_balances,
        },
    )


@any_permission_required("leave.view", "leave.request", "leave.manage", "leave.approve")
@require_http_methods(["GET", "POST"])
def leave_detail(request, pk):
    req = get_object_or_404(
        LeaveRequest.objects.select_related(
            "employee",
            "employee__department",
            "leave_type",
            "requested_by",
            "reviewed_by",
            "approval",
        ),
        pk=pk,
    )
    if not _can_view(request, req):
        messages.error(request, "You do not have access to this leave request.")
        return redirect("leave:list")

    decision = LeaveDecisionForm(request.POST or None)
    can_approve = _can_approve(request, req) and req.status == LeaveRequest.Status.PENDING
    can_cancel = (
        req.status == LeaveRequest.Status.PENDING
        and req.requested_by_id == request.user.id
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("approve", "reject") and not can_approve:
            messages.error(request, "You cannot decide this request.")
            return redirect("leave:detail", pk=pk)
        if action == "cancel" and not can_cancel:
            messages.error(request, "You cannot cancel this request.")
            return redirect("leave:detail", pk=pk)

        if action in ("approve", "reject") and decision.is_valid():
            notes = decision.cleaned_data.get("notes") or ""
            try:
                if action == "approve":
                    approve_leave(req, reviewer=request.user, notes=notes)
                    messages.success(request, "Leave approved.")
                else:
                    reject_leave(req, reviewer=request.user, notes=notes)
                    messages.success(request, "Leave rejected.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect("leave:detail", pk=pk)

        if action == "cancel":
            try:
                cancel_leave(req, user=request.user)
                messages.success(request, "Leave cancelled.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect("leave:detail", pk=pk)

    balance = LeaveBalance.objects.filter(
        employee=req.employee,
        leave_type=req.leave_type,
        year=req.start_date.year,
    ).first()

    return render(
        request,
        "leave/detail.html",
        {
            "page_title": f"Leave · {req.employee.employee_code}",
            "req": req,
            "decision": decision,
            "can_approve": can_approve,
            "can_cancel": can_cancel,
            "balance": balance,
        },
    )


@permission_required("leave.manage")
def leave_type_list(request):
    page_obj = paginate(request, LeaveType.objects.all())
    return render(
        request,
        "leave/type_list.html",
        {
            "page_title": "Leave types",
            "page_obj": page_obj,
            "rows": page_obj,
        },
    )


@permission_required("leave.manage")
@require_http_methods(["GET", "POST"])
def leave_type_edit(request, pk=None):
    obj = get_object_or_404(LeaveType, pk=pk) if pk else None
    form = LeaveTypeForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Leave type saved.")
        return redirect("leave:type_list")
    return render(
        request,
        "leave/type_form.html",
        {
            "page_title": "Edit leave type" if obj else "New leave type",
            "form": form,
            "obj": obj,
        },
    )


@any_permission_required("leave.view", "leave.manage", "leave.request")
def leave_balance_list(request):
    year = request.GET.get("year") or str(timezone.localdate().year)
    try:
        year_i = int(year)
    except ValueError:
        year_i = timezone.localdate().year

    qs = LeaveBalance.objects.filter(year=year_i).select_related(
        "employee", "leave_type", "employee__department"
    )
    can_manage = request_has_perm(request, "leave.manage")
    me = employee_for_user(request.user)
    if not can_manage:
        if me:
            qs = qs.filter(employee=me)
        else:
            qs = qs.none()

    q = request.GET.get("q", "").strip()
    if q and can_manage:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(leave_type__code__icontains=q)
        )

    page_obj = paginate(request, qs.order_by("employee__employee_code", "leave_type__code"))
    return render(
        request,
        "leave/balance_list.html",
        {
            "page_title": "Leave balances",
            "page_obj": page_obj,
            "rows": page_obj,
            "year": year_i,
            "q": q,
            "can_manage": can_manage,
        },
    )


@permission_required("leave.manage")
@require_http_methods(["GET", "POST"])
def leave_balance_edit(request, pk=None):
    obj = get_object_or_404(LeaveBalance, pk=pk) if pk else None
    initial = {}
    if not obj:
        initial["year"] = timezone.localdate().year
    form = LeaveBalanceForm(request.POST or None, instance=obj, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Leave balance saved.")
        return redirect("leave:balance_list")
    return render(
        request,
        "leave/balance_form.html",
        {
            "page_title": "Edit balance" if obj else "Add leave balance",
            "form": form,
            "obj": obj,
        },
    )


@permission_required("leave.manage")
@require_http_methods(["POST"])
def leave_balance_ensure_year(request):
    """Create missing balances for active employees using leave type defaults."""
    try:
        year = int(request.POST.get("year") or timezone.localdate().year)
    except ValueError:
        year = timezone.localdate().year
    types = list(LeaveType.objects.filter(is_active=True))
    employees = Employee.objects.filter(
        status__in=[Employee.Status.ACTIVE, Employee.Status.ON_LEAVE]
    )
    created = 0
    for emp in employees:
        for lt in types:
            _, was_created = LeaveBalance.objects.get_or_create(
                employee=emp,
                leave_type=lt,
                year=year,
                defaults={"entitled": lt.default_entitlement},
            )
            if was_created:
                created += 1
    messages.success(request, f"Ensured balances for {year}: {created} new row(s).")
    return redirect(f"{reverse('leave:balance_list')}?year={year}")
