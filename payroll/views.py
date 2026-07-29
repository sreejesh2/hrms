from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from accounts.permissions import permission_required
from core.pagination import paginate
from people.models import Employee

from .forms import (
    ApplyTemplateForm,
    IncentiveAwardForm,
    IncentiveAwardImportForm,
    IncentivePlanForm,
    PayrollPeriodForm,
    PayslipTemplateForm,
    SalaryComponentForm,
    SalaryStructureForm,
    SalaryStructureLineFormSet,
    SalaryTemplateForm,
    SalaryTemplateLineFormSet,
    StatutoryRuleForm,
)
from .models import (
    IncentiveAward,
    IncentivePlan,
    PayrollPeriod,
    Payslip,
    PayslipTemplate,
    SalaryComponent,
    SalaryStructure,
    SalaryTemplate,
    StatutoryRule,
)
from .pdf import render_payslip_pdf, render_sample_payslip_pdf
from .run import create_period, lock_period, period_totals, run_period
from .services import apply_template, create_structure, update_structure


def _return_url(request):
    candidate = (request.GET.get("next") or request.POST.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return ""


def _url_with_return(view_name, *, return_url="", kwargs=None):
    url = reverse(view_name, kwargs=kwargs)
    if return_url:
        return f"{url}?{urlencode({'next': return_url})}"
    return url


@permission_required("payroll.view")
def payroll_home(request):
    open_count = SalaryStructure.objects.filter(effective_to__isnull=True).count()
    latest_period = PayrollPeriod.objects.first()
    return render(
        request,
        "payroll/home.html",
        {
            "page_title": "Payroll",
            "component_count": SalaryComponent.objects.filter(is_active=True).count(),
            "template_count": SalaryTemplate.objects.filter(is_active=True).count(),
            "open_structures": open_count,
            "period_count": PayrollPeriod.objects.count(),
            "latest_period": latest_period,
            "statutory_active": StatutoryRule.objects.filter(
                is_active=True, apply_in_payroll=True
            ).count(),
            "plan_count": IncentivePlan.objects.filter(is_active=True).count(),
            "award_pending": IncentiveAward.objects.filter(
                status=IncentiveAward.Status.APPROVED
            ).count(),
            "can_manage": request.user.has_hrms_perm("payroll.manage")
            or request.user.is_superuser,
        },
    )


@permission_required("payroll.manage")
def component_list(request):
    q = request.GET.get("q", "").strip()
    qs = SalaryComponent.objects.all()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    page_obj = paginate(request, qs)
    return render(
        request,
        "payroll/component_list.html",
        {"page_title": "Salary components", "page_obj": page_obj, "rows": page_obj, "q": q},
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def component_edit(request, pk=None):
    obj = get_object_or_404(SalaryComponent, pk=pk) if pk else None
    form = SalaryComponentForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Component saved.")
        return redirect("payroll:component_list")
    return render(
        request,
        "payroll/component_form.html",
        {"page_title": "Edit component" if obj else "New component", "form": form},
    )


@permission_required("payroll.manage")
def template_list(request):
    qs = SalaryTemplate.objects.annotate(line_count=Count("lines")).order_by("code")
    page_obj = paginate(request, qs)
    return render(
        request,
        "payroll/template_list.html",
        {"page_title": "Salary templates", "page_obj": page_obj, "rows": page_obj},
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def template_edit(request, pk=None):
    obj = get_object_or_404(SalaryTemplate, pk=pk) if pk else SalaryTemplate()
    form = SalaryTemplateForm(request.POST or None, instance=obj if obj.pk else None)
    formset = SalaryTemplateLineFormSet(
        request.POST or None, instance=obj if obj.pk else None
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        template = form.save()
        formset.instance = template
        formset.save()
        messages.success(request, "Template saved.")
        return redirect("payroll:template_list")
    return render(
        request,
        "payroll/template_form.html",
        {
            "page_title": f"Edit {obj.code}" if obj.pk else "New salary template",
            "form": form,
            "formset": formset,
        },
    )


@permission_required("payroll.view")
def structure_list(request):
    q = request.GET.get("q", "").strip()
    scope = request.GET.get("scope", "open")
    qs = SalaryStructure.objects.select_related(
        "employee", "employee__department", "template"
    ).prefetch_related("lines__component")
    if scope == "open":
        qs = qs.filter(effective_to__isnull=True)
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
        )
    page_obj = paginate(request, qs)
    return render(
        request,
        "payroll/structure_list.html",
        {
            "page_title": "Employee salary structures",
            "page_obj": page_obj,
            "rows": page_obj,
            "q": q,
            "scope": scope,
            "can_manage": request.user.has_hrms_perm("payroll.manage")
            or request.user.is_superuser,
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def structure_create(request):
    return_url = _return_url(request)
    initial = {}
    if request.GET.get("employee"):
        initial["employee"] = request.GET.get("employee")
    form = SalaryStructureForm(request.POST or None, initial=initial)
    formset = SalaryStructureLineFormSet(request.POST or None)

    if request.method == "POST" and form.is_valid():
        employee = form.cleaned_data["employee"]
        effective_from = form.cleaned_data["effective_from"]
        # Validate formset against a throwaway structure instance
        draft = SalaryStructure(
            employee=employee,
            effective_from=effective_from,
            currency=form.cleaned_data.get("currency") or "",
            notes=form.cleaned_data.get("notes") or "",
        )
        formset = SalaryStructureLineFormSet(request.POST, instance=draft)
        if formset.is_valid():
            lines = []
            for f in formset:
                cd = f.cleaned_data
                if not cd or cd.get("DELETE"):
                    continue
                if not cd.get("component"):
                    continue
                lines.append(
                    {
                        "component": cd["component"],
                        "amount": cd.get("amount") or 0,
                        "percent": cd.get("percent"),
                    }
                )
            if not any(l["component"].is_basic for l in lines):
                messages.error(request, "Include the Basic component in the structure.")
            elif not lines:
                messages.error(request, "Add at least one salary line.")
            else:
                try:
                    structure = create_structure(
                        employee=employee,
                        effective_from=effective_from,
                        lines=lines,
                        currency=form.cleaned_data.get("currency")
                        or None,
                        notes=form.cleaned_data.get("notes") or "",
                        created_by=request.user,
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Salary structure created.")
                    if return_url:
                        return redirect(return_url)
                    return redirect(
                        _url_with_return(
                            "payroll:structure_detail",
                            return_url=return_url,
                            kwargs={"pk": structure.pk},
                        )
                    )
        else:
            messages.error(request, "Fix salary line errors.")

    return render(
        request,
        "payroll/structure_form.html",
        {
            "page_title": "New salary structure",
            "form": form,
            "formset": formset,
            "back_url": return_url or reverse("payroll:structure_list"),
            "return_url": return_url,
        },
    )


@permission_required("payroll.view")
def structure_detail(request, pk):
    return_url = _return_url(request)
    structure = get_object_or_404(
        SalaryStructure.objects.select_related(
            "employee", "template", "created_by"
        ).prefetch_related("lines__component"),
        pk=pk,
    )
    resolved = structure.resolved_lines()
    return render(
        request,
        "payroll/structure_detail.html",
        {
            "page_title": f"Salary · {structure.employee.employee_code}",
            "structure": structure,
            "resolved": resolved,
            "gross": structure.earnings_total(),
            "deductions": structure.deductions_total(),
            "net": structure.net_preview(),
            "basic": structure.basic_amount(),
            "can_manage": request.user.has_hrms_perm("payroll.manage")
            or request.user.is_superuser,
            "can_edit": structure.is_open
            and (
                request.user.has_hrms_perm("payroll.manage") or request.user.is_superuser
            ),
            "back_url": return_url or reverse("payroll:structure_list"),
            "return_url": return_url,
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def structure_edit(request, pk):
    return_url = _return_url(request)
    structure = get_object_or_404(
        SalaryStructure.objects.prefetch_related("lines__component"),
        pk=pk,
    )
    if not structure.is_open:
        messages.error(
            request,
            "Closed structures are history-only. Create a new revision instead.",
        )
        return redirect(
            _url_with_return(
                "payroll:structure_detail",
                return_url=return_url,
                kwargs={"pk": structure.pk},
            )
        )

    form = SalaryStructureForm(
        request.POST or None, instance=structure, lock_employee=True
    )
    formset = SalaryStructureLineFormSet(request.POST or None, instance=structure)

    if request.method == "POST" and form.is_valid():
        formset = SalaryStructureLineFormSet(request.POST, instance=structure)
        if formset.is_valid():
            lines = []
            for f in formset:
                cd = f.cleaned_data
                if not cd or cd.get("DELETE"):
                    continue
                if not cd.get("component"):
                    continue
                lines.append(
                    {
                        "component": cd["component"],
                        "amount": cd.get("amount") or 0,
                        "percent": cd.get("percent"),
                    }
                )
            try:
                update_structure(
                    structure=structure,
                    effective_from=form.cleaned_data["effective_from"],
                    currency=form.cleaned_data.get("currency"),
                    notes=form.cleaned_data.get("notes") or "",
                    lines=lines,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Salary structure updated.")
                if return_url:
                    return redirect(return_url)
                return redirect(
                    _url_with_return(
                        "payroll:structure_detail",
                        return_url=return_url,
                        kwargs={"pk": structure.pk},
                    )
                )
        else:
            messages.error(request, "Fix salary line errors.")

    return render(
        request,
        "payroll/structure_form.html",
        {
            "page_title": f"Edit salary · {structure.employee.employee_code}",
            "form": form,
            "formset": formset,
            "structure": structure,
            "is_edit": True,
            "back_url": return_url
            or _url_with_return(
                "payroll:structure_detail",
                return_url=return_url,
                kwargs={"pk": structure.pk},
            ),
            "return_url": return_url,
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def structure_apply_template(request):
    return_url = _return_url(request)
    initial = {}
    if request.method == "GET" and request.GET.get("employee"):
        initial["employee"] = request.GET.get("employee")
    form = ApplyTemplateForm(request.POST or None, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        try:
            structure = apply_template(
                employee=form.cleaned_data["employee"],
                template=form.cleaned_data["template"],
                effective_from=form.cleaned_data["effective_from"],
                currency=form.cleaned_data.get("currency"),
                notes=form.cleaned_data.get("notes") or "",
                created_by=request.user,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Applied {structure.template.code} to {structure.employee.employee_code}.",
            )
            if return_url:
                return redirect(return_url)
            return redirect("payroll:structure_detail", pk=structure.pk)
    return render(
        request,
        "payroll/apply_template.html",
        {
            "page_title": "Apply salary template",
            "form": form,
            "return_url": return_url,
            "back_url": return_url or reverse("payroll:structure_list"),
        },
    )


@permission_required("payroll.view")
def period_list(request):
    qs = PayrollPeriod.objects.annotate(payslip_count=Count("payslips")).order_by(
        "-year", "-month"
    )
    page_obj = paginate(request, qs, per_page=24)
    return render(
        request,
        "payroll/period_list.html",
        {
            "page_title": "Payroll periods",
            "page_obj": page_obj,
            "rows": page_obj,
            "can_manage": request.user.has_hrms_perm("payroll.manage")
            or request.user.is_superuser,
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def period_create(request):
    form = PayrollPeriodForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            period = create_period(
                year=form.cleaned_data["year"],
                month=form.cleaned_data["month"],
                currency=form.cleaned_data.get("currency"),
                notes=form.cleaned_data.get("notes") or "",
                created_by=request.user,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Opened {period.label}.")
            return redirect("payroll:period_detail", pk=period.pk)
    return render(
        request,
        "payroll/period_form.html",
        {"page_title": "New payroll period", "form": form},
    )


@permission_required("payroll.view")
def period_detail(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    slips = period.payslips.select_related("employee", "employee__department").all()
    q = request.GET.get("q", "").strip()
    if q:
        slips = slips.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
        )
    totals = period_totals(period)
    page_obj = paginate(request, slips, per_page=50)
    from .incentives import count_pending_awards

    return render(
        request,
        "payroll/period_detail.html",
        {
            "page_title": period.label,
            "period": period,
            "page_obj": page_obj,
            "slips": page_obj,
            "totals": totals,
            "q": q,
            "can_manage": request.user.has_hrms_perm("payroll.manage")
            or request.user.is_superuser,
            "pending_awards": count_pending_awards(period.pk),
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["POST"])
def period_run(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    try:
        result = run_period(period, user=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        msg = (
            f"Payroll calculated: {result['created']} payslip(s). "
            f"Skipped (no structure): {result['skipped']}."
        )
        if result["errors"]:
            messages.warning(request, msg + " Some errors: " + "; ".join(result["errors"][:5]))
        else:
            messages.success(request, msg)
    return redirect("payroll:period_detail", pk=period.pk)


@permission_required("payroll.manage")
@require_http_methods(["POST"])
def period_lock(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    try:
        lock_period(period)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{period.label} locked. Payslips are final.")
    return redirect("payroll:period_detail", pk=period.pk)


@permission_required("payroll.view")
def payslip_detail(request, pk):
    slip = get_object_or_404(
        Payslip.objects.select_related(
            "period", "employee", "employee__department", "structure"
        ).prefetch_related("lines"),
        pk=pk,
    )
    return_url = _return_url(request)
    period_url = reverse("payroll:period_detail", kwargs={"pk": slip.period_id})
    profile_url = (
        f"{reverse('people:employee_detail', args=[slip.employee_id])}?tab=salary"
    )
    back = return_url or profile_url
    return render(
        request,
        "payroll/payslip_detail.html",
        {
            "page_title": f"Payslip · {slip.employee.employee_code}",
            "slip": slip,
            "lines": slip.lines.all(),
            "can_manage": request.user.has_hrms_perm("payroll.manage")
            or request.user.is_superuser,
            "back_url": back,
            "breadcrumbs": [
                {"label": "Home", "url": reverse("core:dashboard")},
                {"label": "Payroll", "url": reverse("payroll:home")},
                {
                    "label": slip.employee.full_name,
                    "url": profile_url,
                },
                {"label": slip.period.short_label, "url": period_url},
                {"label": "Payslip", "url": None},
            ],
        },
    )


@permission_required("payroll.view")
def payslip_pdf(request, pk):
    slip = get_object_or_404(
        Payslip.objects.select_related(
            "period",
            "employee",
            "employee__department",
            "employee__position",
            "employee__bank",
            "structure",
        ).prefetch_related("lines"),
        pk=pk,
    )
    try:
        pdf_bytes = render_payslip_pdf(slip)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect("payroll:payslip_detail", pk=slip.pk)
    filename = f"payslip-{slip.employee.employee_code}-{slip.period.year}-{slip.period.month:02d}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def payslip_template_edit(request):
    layout = PayslipTemplate.load_default()
    form = PayslipTemplateForm(request.POST or None, instance=layout)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Payslip template saved. New PDFs will use this layout.")
        return redirect("payroll:payslip_template_edit")
    return render(
        request,
        "payroll/payslip_template_form.html",
        {"page_title": "Payslip template", "form": form, "layout": layout},
    )


@permission_required("payroll.manage")
def payslip_sample_pdf(request):
    """Download a demo payslip using current company + template settings."""
    layout = PayslipTemplate.load_default()
    try:
        pdf_bytes = render_sample_payslip_pdf(layout)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect("payroll:payslip_template_edit")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="sample-payslip.pdf"'
    return response


@permission_required("payroll.manage")
def statutory_list(request):
    q = request.GET.get("q", "").strip()
    qs = StatutoryRule.objects.all()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    page_obj = paginate(request, qs)
    return render(
        request,
        "payroll/statutory_list.html",
        {
            "page_title": "Statutory & deductions",
            "page_obj": page_obj,
            "rows": page_obj,
            "q": q,
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def statutory_edit(request, pk=None):
    obj = get_object_or_404(StatutoryRule, pk=pk) if pk else None
    form = StatutoryRuleForm(request.POST or None, instance=obj)
    return_url = _return_url(request)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Statutory rule saved. Re-run open payroll periods to apply.")
        if return_url:
            return redirect(return_url)
        return redirect("payroll:statutory_list")
    return render(
        request,
        "payroll/statutory_form.html",
        {
            "page_title": "Edit statutory rule" if obj else "New statutory rule",
            "form": form,
            "rule": obj,
            "return_url": return_url,
            "back_url": return_url or reverse("payroll:statutory_list"),
        },
    )


@permission_required("payroll.view")
def gratuity_list(request):
    """EOS gratuity estimates for active employees (UAE Art. 51)."""
    from .gratuity import estimate_gratuity

    q = request.GET.get("q", "").strip()
    employees = Employee.objects.filter(
        status__in=[Employee.Status.ACTIVE, Employee.Status.ON_LEAVE]
    ).order_by("employee_code")
    if q:
        employees = employees.filter(
            Q(employee_code__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    page_obj = paginate(request, employees, per_page=50)
    emp_ids = [e.pk for e in page_obj]
    open_structs = {}
    for s in (
        SalaryStructure.objects.filter(
            employee_id__in=emp_ids, effective_to__isnull=True
        )
        .prefetch_related("lines__component")
        .order_by("employee_id", "-effective_from", "-id")
    ):
        open_structs.setdefault(s.employee_id, s)
    rows = []
    for emp in page_obj:
        est = estimate_gratuity(emp, structure=open_structs.get(emp.pk))
        rows.append({"employee": emp, "estimate": est})
    return render(
        request,
        "payroll/gratuity_list.html",
        {
            "page_title": "Gratuity estimates (UAE)",
            "page_obj": page_obj,
            "rows": rows,
            "q": q,
            "can_manage": request.user.has_hrms_perm("payroll.manage")
            or request.user.is_superuser,
        },
    )


@permission_required("payroll.manage")
def incentive_plan_list(request):
    q = request.GET.get("q", "").strip()
    qs = IncentivePlan.objects.select_related("component").all()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    page_obj = paginate(request, qs)
    return render(
        request,
        "payroll/incentive_plan_list.html",
        {
            "page_title": "Incentive plans",
            "page_obj": page_obj,
            "rows": page_obj,
            "q": q,
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def incentive_plan_edit(request, pk=None):
    obj = get_object_or_404(IncentivePlan, pk=pk) if pk else None
    form = IncentivePlanForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Incentive plan saved.")
        return redirect("payroll:incentive_plan_list")
    return render(
        request,
        "payroll/incentive_plan_form.html",
        {
            "page_title": "Edit incentive plan" if obj else "New incentive plan",
            "form": form,
            "plan": obj,
        },
    )


@permission_required("payroll.manage")
def incentive_award_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    plan_id = request.GET.get("plan", "").strip()
    period_id = request.GET.get("period", "").strip()
    qs = IncentiveAward.objects.select_related(
        "plan", "employee", "period", "plan__component"
    ).all()
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(plan__code__icontains=q)
            | Q(notes__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if plan_id.isdigit():
        qs = qs.filter(plan_id=int(plan_id))
    if period_id.isdigit():
        qs = qs.filter(period_id=int(period_id))
    page_obj = paginate(request, qs, per_page=40)
    return render(
        request,
        "payroll/incentive_award_list.html",
        {
            "page_title": "Incentive awards",
            "page_obj": page_obj,
            "rows": page_obj,
            "q": q,
            "status": status,
            "plan_id": plan_id,
            "period_id": period_id,
            "status_choices": IncentiveAward.Status.choices,
            "plans": IncentivePlan.objects.filter(is_active=True).order_by("code"),
            "periods": PayrollPeriod.objects.order_by("-year", "-month")[:24],
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def incentive_award_edit(request, pk=None):
    obj = get_object_or_404(IncentiveAward, pk=pk) if pk else None
    if obj and obj.status == IncentiveAward.Status.PAID:
        messages.error(request, "Paid awards cannot be edited.")
        return redirect("payroll:incentive_award_list")
    form = IncentiveAwardForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        award = form.save(commit=False)
        if not obj:
            award.created_by = request.user
            award.status = IncentiveAward.Status.DRAFT
        elif award.status == IncentiveAward.Status.PAID:
            messages.error(request, "Paid awards cannot be edited.")
            return redirect("payroll:incentive_award_list")
        try:
            award.save()
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        else:
            messages.success(request, "Award saved as draft (approve before payroll).")
            return redirect("payroll:incentive_award_list")
    return render(
        request,
        "payroll/incentive_award_form.html",
        {
            "page_title": "Edit award" if obj else "New award",
            "form": form,
            "award": obj,
        },
    )


@permission_required("payroll.manage")
@require_http_methods(["POST"])
def incentive_award_approve(request, pk):
    from .incentives import approve_award

    award = get_object_or_404(IncentiveAward, pk=pk)
    try:
        approve_award(award, user=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Award approved for {award.employee}.")
    return redirect("payroll:incentive_award_list")


@permission_required("payroll.manage")
@require_http_methods(["POST"])
def incentive_award_cancel(request, pk):
    from .incentives import cancel_award

    award = get_object_or_404(IncentiveAward, pk=pk)
    try:
        cancel_award(award)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Award cancelled.")
    return redirect("payroll:incentive_award_list")


@permission_required("payroll.manage")
@require_http_methods(["POST"])
def incentive_award_approve_selected(request):
    from .incentives import approve_award

    ids = request.POST.getlist("award_ids")
    ok = fail = 0
    for pk in ids:
        if not str(pk).isdigit():
            continue
        award = IncentiveAward.objects.filter(pk=int(pk)).first()
        if not award:
            continue
        try:
            approve_award(award, user=request.user)
            ok += 1
        except ValueError:
            fail += 1
    if ok:
        messages.success(request, f"Approved {ok} award(s).")
    if fail:
        messages.warning(request, f"Skipped {fail} award(s) (not draft or invalid).")
    if not ok and not fail:
        messages.info(request, "No awards selected.")
    return redirect("payroll:incentive_award_list")


@permission_required("payroll.manage")
@require_http_methods(["GET", "POST"])
def incentive_award_import(request):
    import csv
    import io

    from .incentives import parse_award_csv_rows

    form = IncentiveAwardImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["csv_file"].read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        created, errors = parse_award_csv_rows(rows, user=request.user)
        if created:
            messages.success(request, f"Imported {created} draft award(s).")
        if errors:
            messages.warning(
                request, "Some rows failed: " + "; ".join(errors[:8])
            )
        if created and not errors:
            return redirect("payroll:incentive_award_list")
    return render(
        request,
        "payroll/incentive_award_import.html",
        {
            "page_title": "Import awards",
            "form": form,
        },
    )
