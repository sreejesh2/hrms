from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import any_permission_required, permission_required, request_has_perm
from core.pagination import paginate

from .forms import (
    CompetencyForm,
    ManagerCompetencyScoreFormSet,
    ManagerReviewForm,
    ReviewCycleForm,
    SelfCompetencyScoreFormSet,
    SelfReviewForm,
)
from .models import Competency, PerformanceReview, ReviewCycle
from .services import (
    close_cycle,
    complete_review,
    employee_for_user,
    ensure_reviews_for_cycle,
    open_cycle,
    submit_manager_review,
    submit_self_review,
)


def _can_manage(request):
    return request_has_perm(request, "performance.manage")


def _can_view_review(request, review, me):
    if _can_manage(request):
        return True
    return bool(me and (review.employee_id == me.pk or review.manager_id == me.pk))


# —— Cycles (manage) ——


@permission_required("performance.manage")
def cycle_list(request):
    page_obj = paginate(request, ReviewCycle.objects.all())
    return render(
        request,
        "performance/cycle_list.html",
        {"page_title": "Review cycles", "page_obj": page_obj, "rows": page_obj},
    )


@permission_required("performance.manage")
@require_http_methods(["GET", "POST"])
def cycle_edit(request, pk=None):
    obj = get_object_or_404(ReviewCycle, pk=pk) if pk else None
    form = ReviewCycleForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        cycle = form.save(commit=False)
        if not obj:
            cycle.created_by = request.user
        cycle.save()
        messages.success(request, "Review cycle saved.")
        return redirect("performance:cycle_detail", pk=cycle.pk)
    return render(
        request,
        "performance/cycle_form.html",
        {
            "page_title": "Edit review cycle" if obj else "New review cycle",
            "form": form,
            "obj": obj,
        },
    )


@permission_required("performance.manage")
def cycle_detail(request, pk):
    cycle = get_object_or_404(ReviewCycle, pk=pk)
    status = request.GET.get("status", "").strip()

    rows = cycle.reviews.select_related("employee", "manager", "employee__department")
    if status:
        rows = rows.filter(status=status)

    counts_raw = cycle.reviews.aggregate(
        total=Count("id"),
        draft=Count("id", filter=Q(status=PerformanceReview.Status.DRAFT)),
        self_submitted=Count(
            "id", filter=Q(status=PerformanceReview.Status.SELF_SUBMITTED)
        ),
        manager_submitted=Count(
            "id", filter=Q(status=PerformanceReview.Status.MANAGER_SUBMITTED)
        ),
        completed=Count("id", filter=Q(status=PerformanceReview.Status.COMPLETED)),
    )
    counts = {k: counts_raw[k] or 0 for k in counts_raw}
    page_obj = paginate(request, rows.order_by("employee__employee_code"), per_page=50)

    return render(
        request,
        "performance/cycle_detail.html",
        {
            "page_title": cycle.name,
            "cycle": cycle,
            "page_obj": page_obj,
            "rows": page_obj,
            "counts": counts,
            "status": status,
            "statuses": PerformanceReview.Status.choices,
        },
    )


@permission_required("performance.manage")
@require_http_methods(["POST"])
def cycle_open(request, pk):
    cycle = get_object_or_404(ReviewCycle, pk=pk)
    try:
        open_cycle(cycle)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{cycle.name} is now open.")
    return redirect("performance:cycle_detail", pk=pk)


@permission_required("performance.manage")
@require_http_methods(["POST"])
def cycle_close(request, pk):
    cycle = get_object_or_404(ReviewCycle, pk=pk)
    try:
        close_cycle(cycle)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{cycle.name} is closed.")
    return redirect("performance:cycle_detail", pk=pk)


@permission_required("performance.manage")
@require_http_methods(["POST"])
def cycle_generate_reviews(request, pk):
    cycle = get_object_or_404(ReviewCycle, pk=pk)
    result = ensure_reviews_for_cycle(cycle)
    messages.success(
        request,
        f"Generated {result['created']} new review(s) for {result['employees']} active "
        f"employee(s) ({result['existing']} already existed).",
    )
    return redirect("performance:cycle_detail", pk=pk)


# —— Competencies (manage) ——


@permission_required("performance.manage")
def competency_list(request):
    page_obj = paginate(request, Competency.objects.all())
    return render(
        request,
        "performance/competency_list.html",
        {"page_title": "Competencies", "page_obj": page_obj, "rows": page_obj},
    )


@permission_required("performance.manage")
@require_http_methods(["GET", "POST"])
def competency_edit(request, pk=None):
    obj = get_object_or_404(Competency, pk=pk) if pk else None
    form = CompetencyForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Competency saved.")
        return redirect("performance:competency_list")
    return render(
        request,
        "performance/competency_form.html",
        {
            "page_title": "Edit competency" if obj else "New competency",
            "form": form,
            "obj": obj,
        },
    )


# —— Reviews ——


@any_permission_required("performance.view", "performance.manage")
def review_list(request):
    qs = PerformanceReview.objects.select_related(
        "cycle", "employee", "manager", "employee__department"
    )
    can_manage = _can_manage(request)
    me = employee_for_user(request.user)

    cycle_id = request.GET.get("cycle", "").strip()
    status = request.GET.get("status", "").strip()
    scope = request.GET.get("scope", "").strip() or "relevant"
    q = request.GET.get("q", "").strip()

    if can_manage:
        if scope == "mine":
            qs = qs.filter(employee=me) if me else qs.none()
        # default "relevant"/"all" for HR: no extra filter, they see every review
    elif not me:
        qs = qs.none()
    elif scope == "mine":
        qs = qs.filter(employee=me)
    else:
        qs = qs.filter(Q(employee=me) | Q(manager=me))

    if cycle_id:
        qs = qs.filter(cycle_id=cycle_id)
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
        )

    page_obj = paginate(request, qs.order_by("-cycle__start_date", "employee__employee_code"))

    return render(
        request,
        "performance/review_list.html",
        {
            "page_title": "Performance reviews",
            "page_obj": page_obj,
            "rows": page_obj,
            "cycles": ReviewCycle.objects.all(),
            "statuses": PerformanceReview.Status.choices,
            "cycle_id": cycle_id,
            "status": status,
            "scope": scope,
            "q": q,
            "can_manage": can_manage,
            "is_manager": bool(me and me.direct_reports.exists()),
        },
    )


@any_permission_required("performance.view", "performance.manage")
@require_http_methods(["GET", "POST"])
def review_detail(request, pk):
    review = get_object_or_404(
        PerformanceReview.objects.select_related(
            "cycle", "employee", "manager", "employee__department"
        ).prefetch_related("competency_scores__competency"),
        pk=pk,
    )
    me = employee_for_user(request.user)
    can_manage = _can_manage(request)

    if not _can_view_review(request, review, me):
        messages.error(request, "You do not have access to this review.")
        return redirect("performance:list")

    is_self = bool(me and review.employee_id == me.pk)
    is_manager = bool(me and review.manager_id == me.pk)
    can_edit_self = (is_self or can_manage) and review.is_self_editable
    can_edit_manager = (is_manager or can_manage) and review.is_manager_editable
    can_complete = can_manage and review.can_complete

    scores_qs = review.competency_scores.select_related("competency").order_by(
        "competency__sort_order", "competency__name"
    )
    posting_self = request.method == "POST" and request.POST.get("action") == "submit_self"
    posting_manager = request.method == "POST" and request.POST.get("action") == "submit_manager"

    self_form = SelfReviewForm(
        request.POST if posting_self else None,
        initial={
            "overall_self_rating": review.overall_self_rating,
            "self_summary": review.self_summary,
            "employee_goals": review.employee_goals,
        },
    )
    manager_form = ManagerReviewForm(
        request.POST if posting_manager else None,
        initial={
            "overall_manager_rating": review.overall_manager_rating,
            "manager_summary": review.manager_summary,
            "development_plan": review.development_plan,
        },
    )
    self_formset = SelfCompetencyScoreFormSet(
        request.POST if posting_self else None, queryset=scores_qs, prefix="self"
    )
    manager_formset = ManagerCompetencyScoreFormSet(
        request.POST if posting_manager else None, queryset=scores_qs, prefix="manager"
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "submit_self":
            if not can_edit_self:
                messages.error(request, "You cannot edit the self-review section.")
            elif self_form.is_valid() and self_formset.is_valid():
                try:
                    submit_self_review(
                        review,
                        overall_self_rating=self_form.cleaned_data.get("overall_self_rating"),
                        self_summary=self_form.cleaned_data.get("self_summary", ""),
                        employee_goals=self_form.cleaned_data.get("employee_goals", ""),
                        competency_scores=self_formset.save(commit=False),
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Self-review submitted.")
                return redirect("performance:detail", pk=pk)
            else:
                messages.error(request, "Fix the errors in your self-review.")
        elif action == "submit_manager":
            if not can_edit_manager:
                messages.error(request, "You cannot edit the manager section.")
            elif manager_form.is_valid() and manager_formset.is_valid():
                try:
                    submit_manager_review(
                        review,
                        overall_manager_rating=manager_form.cleaned_data.get("overall_manager_rating"),
                        manager_summary=manager_form.cleaned_data.get("manager_summary", ""),
                        development_plan=manager_form.cleaned_data.get("development_plan", ""),
                        competency_scores=manager_formset.save(commit=False),
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Manager review submitted.")
                return redirect("performance:detail", pk=pk)
            else:
                messages.error(request, "Fix the errors in the manager review.")
        elif action == "complete":
            if not can_complete:
                messages.error(request, "This review cannot be completed yet.")
            else:
                try:
                    complete_review(review, actor=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Review completed.")
            return redirect("performance:detail", pk=pk)

    return render(
        request,
        "performance/review_detail.html",
        {
            "page_title": f"Review · {review.employee.full_name}",
            "review": review,
            "self_form": self_form,
            "manager_form": manager_form,
            "self_formset": self_formset,
            "manager_formset": manager_formset,
            "can_edit_self": can_edit_self,
            "can_edit_manager": can_edit_manager,
            "can_complete": can_complete,
            "can_manage": can_manage,
            "is_self": is_self,
            "is_manager": is_manager,
        },
    )
