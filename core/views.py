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
