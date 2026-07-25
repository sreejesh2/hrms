from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import any_permission_required, permission_required, request_has_perm
from core.pagination import paginate
from payroll.currencies import default_currency_code, format_money

from .forms import (
    ExpenseCategoryForm,
    ExpenseClaimForm,
    ExpenseDecisionForm,
    ExpenseLineFormSet,
    ExpensePayForm,
)
from .models import ExpenseCategory, ExpenseClaim
from .services import (
    approve_claim,
    cancel_claim,
    employee_for_user,
    mark_claim_paid,
    reject_claim,
    submit_claim,
)


def _can_approve(request, claim=None):
    if not (
        request_has_perm(request, "expenses.manage")
        or request_has_perm(request, "expenses.approve")
    ):
        return False
    if claim is None:
        return True
    if request_has_perm(request, "expenses.manage"):
        return True
    me = employee_for_user(request.user)
    if claim.approval_id and claim.approval.assignee_id == request.user.id:
        return True
    if me and claim.employee.manager_id == me.pk:
        return True
    return False


def _can_pay(request):
    return request_has_perm(request, "expenses.manage") or request_has_perm(
        request, "expenses.pay"
    )


def _can_view(request, claim):
    if request_has_perm(request, "expenses.manage"):
        return True
    if claim.requested_by_id == request.user.id:
        return True
    me = employee_for_user(request.user)
    if me and claim.employee_id == me.pk:
        return True
    return _can_approve(request, claim)


@any_permission_required(
    "expenses.view", "expenses.request", "expenses.manage", "expenses.approve"
)
def claim_list(request):
    qs = ExpenseClaim.objects.select_related(
        "employee", "requested_by", "reviewed_by", "paid_by"
    )
    status = request.GET.get("status", "").strip()
    scope = request.GET.get("scope", "").strip() or "relevant"
    q = request.GET.get("q", "").strip()

    me = employee_for_user(request.user)
    can_manage = request_has_perm(request, "expenses.manage")
    can_approve = request_has_perm(request, "expenses.approve") or can_manage
    can_pay = _can_pay(request)

    if can_manage and scope == "all":
        pass
    elif scope == "mine":
        qs = qs.filter(Q(requested_by=request.user) | Q(employee=me))
    elif scope == "pending" and can_approve:
        qs = qs.filter(status=ExpenseClaim.Status.PENDING)
        if not can_manage and me:
            qs = qs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        elif not can_manage:
            qs = qs.filter(approval__assignee=request.user)
    elif scope == "to_pay" and can_pay:
        qs = qs.filter(status=ExpenseClaim.Status.APPROVED)
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
            | Q(title__icontains=q)
            | Q(purpose__icontains=q)
            | Q(payment_reference__icontains=q)
        )

    pending_count = 0
    if can_approve:
        pqs = ExpenseClaim.objects.filter(status=ExpenseClaim.Status.PENDING)
        if not can_manage and me:
            pqs = pqs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        pending_count = pqs.count()

    to_pay_count = 0
    if can_pay:
        to_pay_count = ExpenseClaim.objects.filter(
            status=ExpenseClaim.Status.APPROVED
        ).count()

    page_obj = paginate(request, qs)
    return render(
        request,
        "expenses/list.html",
        {
            "page_title": "Reimbursement claims",
            "page_obj": page_obj,
            "rows": page_obj,
            "status": status,
            "scope": scope,
            "q": q,
            "statuses": ExpenseClaim.Status.choices,
            "pending_count": pending_count,
            "to_pay_count": to_pay_count,
            "can_request": request_has_perm(request, "expenses.request") or can_manage,
            "can_manage": can_manage,
            "can_approve": can_approve,
            "can_pay": can_pay,
            "format_money": format_money,
        },
    )


@any_permission_required("expenses.request", "expenses.manage")
@require_http_methods(["GET", "POST"])
def claim_create(request):
    allow_pick = request_has_perm(request, "expenses.manage")
    form = ExpenseClaimForm(
        request.POST or None,
        user=request.user,
        allow_pick_employee=allow_pick,
    )
    # Use a temporary unbound claim instance for the formset parent
    formset = ExpenseLineFormSet(
        request.POST or None,
        request.FILES or None,
        instance=ExpenseClaim(),
        prefix="lines",
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        line_rows = []
        for f in formset:
            cd = f.cleaned_data
            if not cd or not cd.get("_has_content") or cd.get("DELETE"):
                continue
            line_rows.append(
                {
                    "category": cd["category"],
                    "expense_date": cd["expense_date"],
                    "amount": cd["amount"],
                    "merchant": cd.get("merchant") or "",
                    "description": cd.get("description") or "",
                    "receipt": cd.get("receipt"),
                }
            )
        try:
            claim = submit_claim(
                employee=form.cleaned_data["employee"],
                title=form.cleaned_data["title"],
                purpose=form.cleaned_data.get("purpose") or "",
                currency=form.cleaned_data["currency"],
                requested_by=request.user,
                line_rows=line_rows,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Reimbursement claim submitted ({format_money(claim.total_amount, claim.currency)}).",
            )
            return redirect("expenses:detail", pk=claim.pk)

    return render(
        request,
        "expenses/form.html",
        {
            "page_title": "Submit reimbursement claim",
            "form": form,
            "formset": formset,
            "allow_pick": allow_pick,
            "default_currency": form["currency"].value() or default_currency_code(),
            "me": employee_for_user(request.user),
        },
    )


@any_permission_required(
    "expenses.view", "expenses.request", "expenses.manage", "expenses.approve"
)
@require_http_methods(["GET", "POST"])
def claim_detail(request, pk):
    claim = get_object_or_404(
        ExpenseClaim.objects.select_related(
            "employee",
            "employee__department",
            "requested_by",
            "reviewed_by",
            "paid_by",
            "approval",
        ).prefetch_related("lines__category"),
        pk=pk,
    )
    if not _can_view(request, claim):
        messages.error(request, "You do not have access to this reimbursement claim.")
        return redirect("expenses:list")

    decision = ExpenseDecisionForm(request.POST or None, prefix="decision")
    pay_form = ExpensePayForm(request.POST or None, prefix="pay")
    can_approve = _can_approve(request, claim) and claim.status == ExpenseClaim.Status.PENDING
    can_cancel = (
        claim.status == ExpenseClaim.Status.PENDING
        and claim.requested_by_id == request.user.id
    )
    can_mark_paid = _can_pay(request) and claim.status == ExpenseClaim.Status.APPROVED

    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("approve", "reject") and not can_approve:
            messages.error(request, "You cannot decide this claim.")
            return redirect("expenses:detail", pk=pk)
        if action == "cancel" and not can_cancel:
            messages.error(request, "You cannot cancel this claim.")
            return redirect("expenses:detail", pk=pk)
        if action == "pay" and not can_mark_paid:
            messages.error(request, "You cannot mark this claim paid.")
            return redirect("expenses:detail", pk=pk)

        try:
            if action == "approve" and decision.is_valid():
                approve_claim(
                    claim, reviewer=request.user, notes=decision.cleaned_data.get("notes", "")
                )
                messages.success(request, "Claim approved.")
            elif action == "reject" and decision.is_valid():
                reject_claim(
                    claim, reviewer=request.user, notes=decision.cleaned_data.get("notes", "")
                )
                messages.success(request, "Claim rejected.")
            elif action == "cancel":
                cancel_claim(claim, user=request.user)
                messages.success(request, "Claim cancelled.")
            elif action == "pay" and pay_form.is_valid():
                mark_claim_paid(
                    claim,
                    paid_by=request.user,
                    payment_method=pay_form.cleaned_data["payment_method"],
                    payment_reference=pay_form.cleaned_data.get("payment_reference") or "",
                    notes=pay_form.cleaned_data.get("notes") or "",
                )
                messages.success(request, "Claim marked as paid.")
            else:
                messages.error(request, "Check the form and try again.")
                return redirect("expenses:detail", pk=pk)
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("expenses:detail", pk=pk)

    return render(
        request,
        "expenses/detail.html",
        {
            "page_title": claim.title,
            "claim": claim,
            "lines": claim.lines.all(),
            "decision": decision,
            "pay_form": pay_form,
            "can_approve": can_approve,
            "can_cancel": can_cancel,
            "can_mark_paid": can_mark_paid,
            "total_fmt": format_money(claim.total_amount, claim.currency),
        },
    )


@permission_required("expenses.manage")
def category_list(request):
    page_obj = paginate(request, ExpenseCategory.objects.all())
    return render(
        request,
        "expenses/category_list.html",
        {
            "page_title": "Reimbursement categories",
            "page_obj": page_obj,
            "rows": page_obj,
        },
    )


@permission_required("expenses.manage")
@require_http_methods(["GET", "POST"])
def category_edit(request, pk=None):
    obj = get_object_or_404(ExpenseCategory, pk=pk) if pk else None
    form = ExpenseCategoryForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category saved.")
        return redirect("expenses:category_list")
    return render(
        request,
        "expenses/category_form.html",
        {
            "page_title": "Edit category" if obj else "New category",
            "form": form,
            "obj": obj,
        },
    )
