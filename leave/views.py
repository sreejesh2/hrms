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


def _parse_leave_date(value):
    from datetime import datetime

    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _locked_employee_from_request(request):
    """Employee locked from ?employee= / POST when applying from a profile."""
    if not request_has_perm(request, "leave.manage"):
        return None
    raw = (
        request.POST.get("employee")
        if request.method == "POST"
        else request.GET.get("employee")
    ) or ""
    raw = str(raw).strip()
    if not raw.isdigit():
        return None
    return (
        Employee.objects.filter(
            pk=int(raw),
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ],
        )
        .select_related("department")
        .first()
    )


def _safe_next_url(request, fallback="leave:list"):
    nxt = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return reverse(fallback)


@any_permission_required("leave.request", "leave.manage")
@require_http_methods(["GET", "POST"])
def leave_create(request):
    allow_pick = request_has_perm(request, "leave.manage")
    locked = _locked_employee_from_request(request)
    # When locked from profile, do not allow switching employee
    allow_pick = allow_pick and locked is None

    initial = {}
    if request.method == "GET":
        if locked:
            initial["employee"] = locked.pk
        start = _parse_leave_date(request.GET.get("start") or request.GET.get("date"))
        end = _parse_leave_date(request.GET.get("end")) or start
        if start:
            initial["start_date"] = start
        if end:
            initial["end_date"] = end

    form = LeaveRequestForm(
        request.POST or None,
        user=request.user,
        allow_pick_employee=allow_pick,
        locked_employee=locked,
        initial=initial or None,
    )
    next_url = _safe_next_url(request)

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
            if next_url != reverse("leave:list"):
                return redirect(next_url)
            return redirect("leave:detail", pk=req.pk)

    balance_employee = locked or employee_for_user(request.user)
    my_balances = []
    if balance_employee:
        my_balances = LeaveBalance.objects.filter(
            employee=balance_employee, year=timezone.localdate().year
        ).select_related("leave_type")

    return render(
        request,
        "leave/form.html",
        {
            "page_title": "Apply for leave",
            "form": form,
            "allow_pick": allow_pick,
            "locked_employee": locked,
            "next_url": next_url if next_url != reverse("leave:list") else "",
            "my_balances": my_balances,
            "cancel_url": next_url
            if next_url != reverse("leave:list")
            else reverse("leave:list"),
            "back_url": next_url
            if next_url != reverse("leave:list")
            else reverse("leave:list"),
        },
    )


@permission_required("leave.manage")
@require_http_methods(["POST"])
def leave_quick_apply(request):
    """Create leave for an absent attendance day (leave type chosen from daily list)."""
    from datetime import datetime

    from attendance.models import DailyAttendance

    next_url = _safe_next_url(request, fallback="attendance_ops:daily_list")
    emp_raw = (request.POST.get("employee") or "").strip()
    type_raw = (request.POST.get("leave_type") or "").strip()
    day_raw = (request.POST.get("date") or "").strip()

    if not (emp_raw.isdigit() and type_raw.isdigit() and day_raw):
        messages.error(request, "Choose a leave type for this absent day.")
        return redirect(next_url)

    try:
        on_date = datetime.strptime(day_raw, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Invalid attendance date.")
        return redirect(next_url)

    employee = get_object_or_404(Employee, pk=int(emp_raw))
    leave_type = get_object_or_404(LeaveType, pk=int(type_raw), is_active=True)
    row = DailyAttendance.objects.filter(employee=employee, date=on_date).first()
    if not row or row.status != DailyAttendance.Status.ABSENT:
        messages.error(request, "Leave can only be applied from an Absent day.")
        return redirect(next_url)

    reason = f"Applied from attendance absent on {on_date.isoformat()}"
    try:
        req = submit_leave(
            employee=employee,
            leave_type=leave_type,
            start_date=on_date,
            end_date=on_date,
            reason=reason,
            requested_by=request.user,
            is_half_day=False,
            apply_to_attendance=True,
        )
        # From attendance, apply immediately so the day flips to On leave
        if req.status == LeaveRequest.Status.PENDING:
            approve_leave(
                req,
                reviewer=request.user,
                notes="Approved from daily attendance Absent",
            )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(next_url)

    messages.success(
        request,
        f"{employee.full_name}: {leave_type.name} applied for {on_date.isoformat()}.",
    )
    return redirect(next_url)


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

    next_url = _safe_next_url(request)
    detail_redirect = reverse("leave:detail", kwargs={"pk": pk})
    if next_url != reverse("leave:list"):
        from urllib.parse import urlencode

        detail_redirect = f"{detail_redirect}?{urlencode({'next': next_url})}"

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
            return redirect(detail_redirect)
        if action == "cancel" and not can_cancel:
            messages.error(request, "You cannot cancel this request.")
            return redirect(detail_redirect)

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
            return redirect(detail_redirect)

        if action == "cancel":
            try:
                cancel_leave(req, user=request.user)
                messages.success(request, "Leave cancelled.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(detail_redirect)

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
            "next_url": next_url if next_url != reverse("leave:list") else "",
            "back_url": next_url
            if next_url != reverse("leave:list")
            else reverse("leave:list"),
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
