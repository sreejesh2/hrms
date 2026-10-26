from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.permissions import permission_required
from core.dashboard import build_dashboard
from core.middleware import THEME_COOKIE, VALID_THEMES


@permission_required("core.view_dashboard")
def dashboard(request):
    dash = build_dashboard(request)
    return render(
        request,
        "core/dashboard.html",
        {
            "page_title": "Dashboard",
            "dash": dash,
        },
    )


@login_required
@require_POST
def set_theme(request):
    theme = request.POST.get("theme", "light")
    if theme not in VALID_THEMES:
        theme = "light"
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse(
        "core:dashboard"
    )
    response = HttpResponseRedirect(next_url)
    response.set_cookie(
        THEME_COOKIE,
        theme,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
    )
    return response


def _can_open_media(request, name: str) -> bool:
    """Allow a file only if the user may see the record that owns it."""
    from accounts.permissions import request_has_perm
    from expenses.models import ExpenseLine
    from expenses.views import _can_view as can_view_claim
    from people.models import EmployeeDocument
    from setup.models import OrganizationSettings

    doc = EmployeeDocument.objects.filter(file=name).select_related("employee").first()
    if doc:
        return (
            request_has_perm(request, "people.view_employees")
            or doc.employee.user_id == request.user.id
        )
    line = ExpenseLine.objects.filter(receipt=name).select_related("claim").first()
    if line:
        return can_view_claim(request, line.claim)
    # Company logo: any signed-in user
    return OrganizationSettings.objects.filter(logo=name).exists()


@login_required
def protected_media(request, path):
    """
    Serve uploaded files (employee documents, receipts, logo) only to users
    allowed to see the owning record. Unknown files are 404, so there is no
    way to browse MEDIA_ROOT or escape it.
    """
    from django.conf import settings
    from django.http import FileResponse, Http404
    from django.utils._os import safe_join

    if not _can_open_media(request, path):
        raise Http404
    try:
        full_path = safe_join(settings.MEDIA_ROOT, path)
        response = FileResponse(open(full_path, "rb"))
    except (OSError, ValueError) as exc:
        raise Http404 from exc
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
