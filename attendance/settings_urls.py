"""Time settings URLs — mounted at /settings/time/"""

from django.urls import path

from . import ops_views, views

app_name = "attendance"

urlpatterns = [
    path("calendars/", views.calendar_list, name="calendar_list"),
    path("calendars/new/", views.calendar_create, name="calendar_create"),
    path("calendars/<int:pk>/edit/", views.calendar_edit, name="calendar_edit"),
    path("calendars/<int:pk>/delete/", views.calendar_delete, name="calendar_delete"),
    path("holidays/", ops_views.holiday_list, name="holiday_list"),
    path("holidays/new/", ops_views.holiday_create, name="holiday_create"),
    path("holidays/<int:pk>/edit/", ops_views.holiday_edit, name="holiday_edit"),
    path("holidays/<int:pk>/delete/", ops_views.holiday_delete, name="holiday_delete"),
    path("devices/", ops_views.device_list, name="device_list"),
    path("devices/new/", ops_views.device_create, name="device_create"),
    path("devices/<int:pk>/", ops_views.device_detail, name="device_detail"),
    path("devices/<int:pk>/edit/", ops_views.device_edit, name="device_edit"),
    path(
        "devices/<int:pk>/rotate-token/",
        ops_views.device_rotate_token,
        name="device_rotate_token",
    ),
    path(
        "devices/<int:pk>/sync-time/",
        ops_views.device_sync_time,
        name="device_sync_time",
    ),
    path(
        "devices/<int:pk>/check/",
        ops_views.device_check,
        name="device_check",
    ),
    path(
        "devices/<int:pk>/enroll/",
        ops_views.device_enroll,
        name="device_enroll",
    ),
    path("devices/<int:pk>/delete/", ops_views.device_delete, name="device_delete"),
    path("shifts/", views.shift_list, name="shift_list"),
    path("shifts/new/", views.shift_create, name="shift_create"),
    path("shifts/<int:pk>/", views.shift_detail, name="shift_detail"),
    path("shifts/<int:pk>/edit/", views.shift_edit, name="shift_edit"),
    path("shifts/<int:pk>/versions/new/", views.shift_version_add, name="shift_version_add"),
    path("shifts/<int:pk>/delete/", views.shift_delete, name="shift_delete"),
    path("assignments/", views.assignment_list, name="assignment_list"),
    path("assignments/new/", views.assignment_create, name="assignment_create"),
    path("assignments/bulk/", views.assignment_bulk, name="assignment_bulk"),
    path("assignments/import/", views.assignment_import, name="assignment_import"),
    path(
        "assignments/import/sample.csv",
        views.assignment_import_sample,
        name="assignment_import_sample",
    ),
    path(
        "assignments/apply-defaults/",
        views.assignment_apply_defaults,
        name="assignment_apply_defaults",
    ),
    path("assignments/<int:pk>/edit/", views.assignment_edit, name="assignment_edit"),
    path("assignments/<int:pk>/delete/", views.assignment_delete, name="assignment_delete"),
    path("ot-policies/", views.ot_policy_list, name="ot_policy_list"),
    path("ot-policies/new/", views.ot_policy_edit, name="ot_policy_create"),
    path("ot-policies/<int:pk>/", views.ot_policy_edit, name="ot_policy_edit"),
    path("ot-policies/<int:pk>/delete/", views.ot_policy_delete, name="ot_policy_delete"),
]
