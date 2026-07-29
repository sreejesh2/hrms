from django.urls import path

from . import views

app_name = "people"

urlpatterns = [
    path("", views.employee_list, name="employee_list"),
    path("active/", views.active_list, name="active_list"),
    path("vacation/", views.vacation_list, name="vacation_list"),
    path("onboarding/", views.onboarding_list, name="onboarding_list"),
    path("new/", views.employee_create, name="employee_create"),
    path("<int:pk>/edit/", views.employee_edit, name="employee_edit"),
    path("<int:pk>/login/", views.employee_login, name="employee_login"),
    path(
        "<int:pk>/attendance.<str:fmt>",
        views.employee_attendance_export,
        name="employee_attendance_export",
    ),
    path(
        "<int:pk>/attendance/inline/",
        views.employee_attendance_inline,
        name="employee_attendance_inline",
    ),
    path(
        "<int:pk>/payroll.<str:fmt>",
        views.employee_payroll_export,
        name="employee_payroll_export",
    ),
    path(
        "<int:pk>/device-enroll/",
        views.employee_device_enroll,
        name="employee_device_enroll",
    ),
    path("<int:pk>/", views.employee_detail, name="employee_detail"),
    path(
        "<int:pk>/documents/<int:doc_id>/delete/",
        views.document_delete,
        name="document_delete",
    ),
]
