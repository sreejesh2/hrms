from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.permissions import permission_required
from core.pagination import paginate

from .models import ActivityLog

User = get_user_model()


@permission_required("audit.view")
def log_list(request):
    qs = ActivityLog.objects.select_related("actor")

    q = (request.GET.get("q") or "").strip()
    module = (request.GET.get("module") or "").strip()
    action = (request.GET.get("action") or "").strip()
    actor_id = (request.GET.get("actor") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if q:
        qs = qs.filter(
            Q(summary__icontains=q)
            | Q(detail__icontains=q)
            | Q(actor_email__icontains=q)
            | Q(actor_name__icontains=q)
            | Q(object_repr__icontains=q)
            | Q(request_path__icontains=q)
            | Q(view_name__icontains=q)
            | Q(module__icontains=q)
            | Q(ip_address__icontains=q)
        )
    if module:
        qs = qs.filter(module=module)
    if action:
        qs = qs.filter(action=action)
    if actor_id.isdigit():
        qs = qs.filter(actor_id=int(actor_id))

    df = parse_date(date_from) if date_from else None
    dt = parse_date(date_to) if date_to else None
    if df:
        start = timezone.make_aware(datetime.combine(df, time.min))
        qs = qs.filter(created_at__gte=start)
    if dt:
        end = timezone.make_aware(datetime.combine(dt, time.max))
        qs = qs.filter(created_at__lte=end)

    modules = (
        ActivityLog.objects.exclude(module="")
        .values_list("module", flat=True)
        .distinct()
        .order_by("module")
    )
    actors = (
        User.objects.filter(activity_logs__isnull=False)
        .distinct()
        .order_by("email")[:200]
    )

    return render(
        request,
        "audit/log_list.html",
        {
            "page_title": "Activity log",
            "page_obj": paginate(request, qs, per_page=40),
            "q": q,
            "module": module,
            "action": action,
            "actor_id": actor_id,
            "date_from": date_from,
            "date_to": date_to,
            "modules": modules,
            "actors": actors,
            "action_choices": ActivityLog.Action.choices,
            "total_count": qs.count(),
        },
    )


@permission_required("audit.view")
def log_detail(request, pk):
    log = get_object_or_404(ActivityLog.objects.select_related("actor"), pk=pk)
    return render(
        request,
        "audit/log_detail.html",
        {"page_title": "Activity detail", "log": log},
    )
