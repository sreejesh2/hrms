from django.urls import path

from . import master_views, views

app_name = "setup"

urlpatterns = [
    path("", views.settings_home, name="home"),
    path(
        "organization/company/",
        views.organization_settings,
        name="organization_settings",
    ),
    path("employee-fields/", views.employee_fields, name="employee_fields"),
    path("employee-fields/new/", views.employee_field_create, name="employee_field_create"),
    path(
        "employee-fields/<int:pk>/edit/",
        views.employee_field_edit,
        name="employee_field_edit",
    ),
    path(
        "employee-fields/<int:pk>/delete/",
        views.employee_field_delete,
        name="employee_field_delete",
    ),
    # Access control
    path("access/roles/", views.role_list, name="role_list"),
    path("access/roles/new/", views.role_create, name="role_create"),
    path("access/roles/<int:pk>/edit/", views.role_edit, name="role_edit"),
    path("access/roles/<int:pk>/delete/", views.role_delete, name="role_delete"),
    path("access/permissions/", views.permission_list, name="permission_list"),
    path("access/permissions/new/", views.permission_create, name="permission_create"),
    path(
        "access/permissions/<int:pk>/edit/",
        views.permission_edit,
        name="permission_edit",
    ),
    path("access/users/", views.user_role_list, name="user_role_list"),
    path("access/users/<int:pk>/", views.user_role_edit, name="user_role_edit"),
    path("backups/", views.backup_list, name="backup_list"),
    path("backups/download/<str:name>", views.backup_download, name="backup_download"),
    # Organization masters
    path(
        "organization/<slug:master_key>/",
        master_views.master_list,
        name="master_list",
    ),
    path(
        "organization/<slug:master_key>/new/",
        master_views.master_create,
        name="master_create",
    ),
    path(
        "organization/<slug:master_key>/<int:pk>/edit/",
        master_views.master_edit,
        name="master_edit",
    ),
    path(
        "organization/<slug:master_key>/<int:pk>/delete/",
        master_views.master_delete,
        name="master_delete",
    ),
]
