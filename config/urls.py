from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("people/", include("people.urls")),
    path("settings/time/", include("attendance.settings_urls")),
    path("attendance/", include("attendance.ops_urls")),
    path("leave/", include("leave.urls")),
    path("payroll/", include("payroll.urls")),
    path("reports/", include("reports.urls")),
    path("expenses/", include("expenses.urls")),
    path("loans/", include("loans.urls")),
    path("performance/", include("performance.urls")),
    path("api/attendance/", include("attendance.api_urls")),
    path("iclock/", include("attendance.zkteco_urls")),
    path("settings/", include("setup.urls")),
    path("notifications/", include("notifications.urls")),
    path("audit/", include("audit.urls")),
    path("docs/", include("docs_app.urls")),
    # Uploaded files: permission-checked in every mode (never served raw)
    re_path(r"^media/(?P<path>.+)$", core_views.protected_media, name="protected_media"),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
