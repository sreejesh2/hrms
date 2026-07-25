from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import any_permission_required, permission_required, request_has_perm
from core.pagination import paginate
from payroll.currencies import format_money

from .forms import AdvanceDecisionForm, AdvanceDisburseForm, SalaryAdvanceForm
from .models import SalaryAdvance
from .services import (
    approve_advance,
    cancel_advance,
    disburse_advance,
    employee_for_user,
    reject_advance,
    submit_advance,
)


def _can_approve(request, advance=None):
    if not (
        request_has_perm(request, "loans.manage")
        or request_has_perm(request, "loans.approve")
    ):
        return False
    if advance is None:
        return True
    if request_has_perm(request, "loans.manage"):
        return True
    me = employee_for_user(request.user)
    if advance.approval_id and advance.approval.assignee_id == request.user.id:
        return True
    if me and advance.employee.manager_id == me.pk:
        return True
    return False


def _can_disburse(request):
    return request_has_perm(request, "loans.manage") or request_has_perm(
        request, "loans.disburse"
    )


def _can_view(request, advance):
    if request_has_perm(request, "loans.manage"):
        return True
    if advance.requested_by_id == request.user.id:
        return True
    me = employee_for_user(request.user)
    if me and advance.employee_id == me.pk:
        return True
    return _can_approve(request, advance)


@any_permission_required(
    "loans.view", "loans.request", "loans.manage", "loans.approve"
)
def advance_list(request):
    qs = SalaryAdvance.objects.select_related(
        "employee", "requested_by", "reviewed_by", "disbursed_by"
    )
    status = request.GET.get("status", "").strip()
    scope = request.GET.get("scope", "").strip() or "relevant"
    q = request.GET.get("q", "").strip()

    me = employee_for_user(request.user)
    can_manage = request_has_perm(request, "loans.manage")
    can_approve = request_has_perm(request, "loans.approve") or can_manage
    can_disburse = _can_disburse(request)
    can_request = request_has_perm(request, "loans.request") or can_manage

    if can_manage and scope == "all":
        pass
    elif scope == "mine":
        if me:
            qs = qs.filter(Q(requested_by=request.user) | Q(employee=me))
        else:
            qs = qs.filter(requested_by=request.user)
    elif scope == "pending" and can_approve:
        qs = qs.filter(status=SalaryAdvance.Status.PENDING)
    elif scope == "to_disburse" and can_disburse:
        qs = qs.filter(status=SalaryAdvance.Status.APPROVED)
    elif scope == "active":
        qs = qs.filter(
            status__in=[
                SalaryAdvance.Status.DISBURSED,
                SalaryAdvance.Status.RECOVERING,
            ]
        )
        if not can_manage:
            qs = qs.filter(
                Q(requested_by=request.user) | (Q(employee=me) if me else Q(pk__in=[]))
            )
    else:
        # relevant
        parts = Q(requested_by=request.user)
        if me:
            parts |= Q(employee=me)
        if can_approve:
            parts |= Q(status=SalaryAdvance.Status.PENDING)
        if can_disburse:
            parts |= Q(status=SalaryAdvance.Status.APPROVED)
        if can_manage:
            parts |= Q(
                status__in=[
                    SalaryAdvance.Status.DISBURSED,
                    SalaryAdvance.Status.RECOVERING,
                ]
            )
        qs = qs.filter(parts)

    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(reason__icontains=q)
            | Q(disburse_reference__icontains=q)
        )

    pending_count = 0
    to_disburse_count = 0
    if can_approve:
        pending_count = SalaryAdvance.objects.filter(
            status=SalaryAdvance.Status.PENDING
        ).count()
    if can_disburse:
        to_disburse_count = SalaryAdvance.objects.filter(
            status=SalaryAdvance.Status.APPROVED
        ).count()

    return render(
        request,
        "loans/list.html",
        {
            "page_title": "Salary advances",
            "page_obj": paginate(request, qs.distinct()),
            "status": status,
            "scope": scope,
            "q": q,
            "statuses": SalaryAdvance.Status.choices,
            "can_manage": can_manage,
            "can_approve": can_approve,
            "can_disburse": can_disburse,
            "can_request": can_request,
            "pending_count": pending_count,
            "to_disburse_count": to_disburse_count,
        },
    )


@any_permission_required("loans.request", "loans.manage")
@require_http_methods(["GET", "POST"])
def advance_create(request):
    can_pick = request_has_perm(request, "loans.manage")
    me = employee_for_user(request.user)
    form = SalaryAdvanceForm(
        request.POST or None, user=request.user, can_pick_employee=can_pick
    )
    if request.method == "POST" and form.is_valid():
        if can_pick:
            employee = form.cleaned_data["employee"]
        else:
            if not me:
                messages.error(request, "Your login is not linked to an employee.")
                return redirect("loans:list")
            employee = me
        try:
            adv = submit_advance(
                employee=employee,
                amount=form.cleaned_data["amount"],
                installments=form.cleaned_data["installments"],
                reason=form.cleaned_data.get("reason") or "",
                requested_by=request.user,
                currency=form.cleaned_data["currency"],
            )
            messages.success(
                request,
                f"Advance {format_money(adv.amount, adv.currency)} submitted.",
            )
            return redirect("loans:detail", pk=adv.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "loans/form.html",
        {"page_title": "Request salary advance", "form": form},
    )


@any_permission_required(
    "loans.view", "loans.request", "loans.manage", "loans.approve"
)
def advance_detail(request, pk):
    advance = get_object_or_404(
        SalaryAdvance.objects.select_related(
            "employee", "requested_by", "reviewed_by", "disbursed_by", "approval"
        ).prefetch_related("recoveries"),
        pk=pk,
    )
    if not _can_view(request, advance):
        messages.error(request, "You cannot view this advance.")
        return redirect("loans:list")

    decision_form = AdvanceDecisionForm()
    disburse_form = AdvanceDisburseForm()
    can_approve = _can_approve(request, advance) and advance.status == SalaryAdvance.Status.PENDING
    can_disburse = (
        _can_disburse(request) and advance.status == SalaryAdvance.Status.APPROVED
    )
    can_cancel = advance.status in (
        SalaryAdvance.Status.PENDING,
        SalaryAdvance.Status.APPROVED,
    ) and (
        advance.requested_by_id == request.user.id
        or request_has_perm(request, "loans.manage")
    )

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "approve" and can_approve:
                form = AdvanceDecisionForm(request.POST)
                if form.is_valid():
                    approve_advance(
                        advance,
                        reviewed_by=request.user,
                        notes=form.cleaned_data.get("notes") or "",
                    )
                    messages.success(request, "Advance approved.")
            elif action == "reject" and can_approve:
                form = AdvanceDecisionForm(request.POST)
                if form.is_valid():
                    reject_advance(
                        advance,
                        reviewed_by=request.user,
                        notes=form.cleaned_data.get("notes") or "",
                    )
                    messages.success(request, "Advance rejected.")
            elif action == "disburse" and can_disburse:
                form = AdvanceDisburseForm(request.POST)
                if form.is_valid():
                    disburse_advance(
                        advance,
                        disbursed_by=request.user,
                        disburse_method=form.cleaned_data["disburse_method"],
                        disburse_reference=form.cleaned_data.get("disburse_reference")
                        or "",
                        notes=form.cleaned_data.get("notes") or "",
                    )
                    messages.success(
                        request,
                        "Advance marked disbursed — recovery starts on next payroll.",
                    )
            elif action == "cancel" and can_cancel:
                cancel_advance(advance, user=request.user)
                messages.success(request, "Advance cancelled.")
            else:
                messages.error(request, "Action not allowed.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("loans:detail", pk=advance.pk)

    return render(
        request,
        "loans/detail.html",
        {
            "page_title": f"Advance · {advance.pk}",
            "advance": advance,
            "decision_form": decision_form,
            "disburse_form": disburse_form,
            "can_approve": can_approve,
            "can_disburse": can_disburse,
            "can_cancel": can_cancel,
            "recoveries": advance.recoveries.select_related("period")[:20],
        },
    )
