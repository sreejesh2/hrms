"""Attendance operations — mounted at /attendance/"""

from django.urls import path

from . import ops_views, register_views, regularization_views

app_name = "attendance_ops"

urlpatterns = [
    path("punches/", ops_views.punch_list, name="punch_list"),
    path("punches/new/", ops_views.punch_create, name="punch_create"),
    path("punches/import/", ops_views.punch_import, name="punch_import"),
    path(
        "punches/import/sample/<slug:format_key>.csv",
        ops_views.punch_import_sample,
        name="punch_import_sample",
    ),
    path("punches/<int:pk>/delete/", ops_views.punch_delete, name="punch_delete"),
    path("daily/", ops_views.daily_list, name="daily_list"),
    path("daily/generate/", ops_views.daily_generate, name="daily_generate"),
    path("daily/<int:pk>/", ops_views.daily_detail, name="daily_detail"),
    path("daily/<int:pk>/regen/", ops_views.daily_regen, name="daily_regen"),
    # Regularization
    path(
        "regularization/",
        regularization_views.regularization_list,
        name="regularization_list",
    ),
    path(
        "regularization/new/",
        regularization_views.regularization_create,
        name="regularization_create",
    ),
    path(
        "regularization/<int:pk>/",
        regularization_views.regularization_detail,
        name="regularization_detail",
    ),
    # Monthly register
    path("register/", register_views.register_month, name="register_month"),
    path(
        "register/generate-month/",
        register_views.register_generate_month,
        name="register_generate_month",
    ),
    path(
        "register/lock-month/",
        register_views.register_lock_month,
        name="register_lock_month",
    ),
    path(
        "register/<int:employee_id>/<str:day_iso>/",
        register_views.register_day,
        name="register_day",
    ),
]
