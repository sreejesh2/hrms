from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.forms_rbac import AppPermissionForm, RoleForm, UserRolesForm
from accounts.models import AppPermission, Role, User
from accounts.permissions import permission_required
from core.pagination import paginate
from people.forms import EmployeeAttributeDefinitionForm
from people.models import EmployeeAttributeDefinition

from .forms import OrganizationSettingsForm
from .models import OrganizationSettings


@login_required
def settings_home(request):
    return render(
        request,
        "setup/home.html",
        {"page_title": "Settings"},
    )


@permission_required("setup.manage_company")
@require_http_methods(["GET", "POST"])
def organization_settings(request):
    org = OrganizationSettings.load()
    form = OrganizationSettingsForm(
        request.POST or None, request.FILES or None, instance=org
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Company settings saved.")
        return redirect("setup:organization_settings")
    return render(
        request,
        "setup/organization_settings.html",
        {
            "page_title": "Company settings",
            "form": form,
            "org": org,
        },
    )


@permission_required("setup.manage_employee_fields")
def employee_fields(request):
    page_obj = paginate(request, EmployeeAttributeDefinition.objects.all())
    return render(
        request,
        "setup/employee_fields.html",
        {
            "page_title": "Employee custom fields",
            "page_obj": page_obj,
            "fields": page_obj,
        },
    )


@permission_required("setup.manage_employee_fields")
@require_http_methods(["GET", "POST"])
def employee_field_create(request):
    form = EmployeeAttributeDefinitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Custom field created. It will appear on employee profiles."
        )
        return redirect("setup:employee_fields")
    return render(
        request,
        "setup/employee_field_form.html",
        {"page_title": "Add employee custom field", "form": form},
    )


@permission_required("setup.manage_employee_fields")
@require_http_methods(["GET", "POST"])
def employee_field_edit(request, pk):
    field = get_object_or_404(EmployeeAttributeDefinition, pk=pk)
    form = EmployeeAttributeDefinitionForm(request.POST or None, instance=field)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Custom field updated.")
        return redirect("setup:employee_fields")
    return render(
        request,
        "setup/employee_field_form.html",
        {"page_title": "Edit employee custom field", "form": form, "field": field},
    )


@permission_required("setup.manage_employee_fields")
@require_http_methods(["POST"])
def employee_field_delete(request, pk):
    field = get_object_or_404(EmployeeAttributeDefinition, pk=pk)
    field.delete()
    messages.success(request, "Custom field deleted.")
    return redirect("setup:employee_fields")


# —— Access control (dynamic RBAC) ——


@permission_required("access.manage_roles")
def role_list(request):
    page_obj = paginate(request, Role.objects.prefetch_related("permissions").all())
    return render(
        request,
        "setup/role_list.html",
        {"page_title": "Roles", "page_obj": page_obj, "roles": page_obj},
    )


@permission_required("access.manage_roles")
@require_http_methods(["GET", "POST"])
def role_create(request):
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Role created.")
        return redirect("setup:role_list")
    return render(
        request,
        "setup/role_form.html",
        {"page_title": "Create role", "form": form},
    )


@permission_required("access.manage_roles")
@require_http_methods(["GET", "POST"])
def role_edit(request, pk):
    role = get_object_or_404(Role.objects.prefetch_related("permissions"), pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Role updated.")
        return redirect("setup:role_list")
    return render(
        request,
        "setup/role_form.html",
        {"page_title": f"Edit role: {role.name}", "form": form, "role": role},
    )


@permission_required("access.manage_roles")
@require_http_methods(["POST"])
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk)
    role.delete()
    messages.success(request, "Role deleted.")
    return redirect("setup:role_list")


@permission_required("access.manage_permissions")
def permission_list(request):
    page_obj = paginate(request, AppPermission.objects.all())
    return render(
        request,
        "setup/permission_list.html",
        {
            "page_title": "Permissions",
            "page_obj": page_obj,
            "permissions": page_obj,
        },
    )


@permission_required("access.manage_permissions")
@require_http_methods(["GET", "POST"])
def permission_create(request):
    form = AppPermissionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Permission added to catalog.")
        return redirect("setup:permission_list")
    return render(
        request,
        "setup/permission_form.html",
        {"page_title": "Add permission", "form": form},
    )


@permission_required("access.manage_permissions")
@require_http_methods(["GET", "POST"])
def permission_edit(request, pk):
    perm = get_object_or_404(AppPermission, pk=pk)
    form = AppPermissionForm(request.POST or None, instance=perm)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Permission updated.")
        return redirect("setup:permission_list")
    return render(
        request,
        "setup/permission_form.html",
        {"page_title": "Edit permission", "form": form},
    )


@permission_required("access.assign_user_roles")
def user_role_list(request):
    page_obj = paginate(
        request, User.objects.prefetch_related("roles").order_by("email")
    )
    return render(
        request,
        "setup/user_role_list.html",
        {"page_title": "User roles", "page_obj": page_obj, "users": page_obj},
    )


@permission_required("access.assign_user_roles")
@require_http_methods(["GET", "POST"])
def user_role_edit(request, pk):
    user = get_object_or_404(User.objects.prefetch_related("roles"), pk=pk)
    form = UserRolesForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Roles updated for {user.email}.")
        return redirect("setup:user_role_list")
    return render(
        request,
        "setup/user_role_form.html",
        {"page_title": f"Roles: {user.email}", "form": form, "edit_user": user},
    )


@permission_required("setup.manage_backups")
@require_http_methods(["GET", "POST"])
def backup_list(request):
    from audit.models import ActivityLog
    from audit.services import log_event

    from .backups import BackupError, backup_dir, create_backup, list_backups

    if request.method == "POST":
        try:
            files = create_backup()
        except (BackupError, OSError) as exc:
            messages.error(request, f"Backup failed: {exc}")
        else:
            log_event(
                summary=f"Created backup {files[0].name}",
                action=ActivityLog.Action.CREATE,
                module="setup",
                request=request,
            )
            messages.success(request, "Backup created.")
        return redirect("setup:backup_list")

    sets = {}
    for f in list_backups():
        entry = sets.setdefault(f.stamp, {"stamp": f.stamp, "created": f.created})
        entry[f.kind] = f
    return render(
        request,
        "setup/backup_list.html",
        {
            "page_title": "Backups",
            "backup_sets": list(sets.values()),
            "backup_dir": backup_dir(),
        },
    )


@permission_required("setup.manage_backups", raise_exception=True)
def backup_download(request, name):
    from django.http import FileResponse, Http404

    from audit.models import ActivityLog
    from audit.services import log_event

    from .backups import backup_path

    path = backup_path(name)
    if path is None:
        raise Http404
    log_event(
        summary=f"Downloaded backup {name}",
        action=ActivityLog.Action.EXPORT,
        module="setup",
        request=request,
    )
    response = FileResponse(open(path, "rb"), as_attachment=True, filename=name)
    response["Cache-Control"] = "private, no-store"
    return response
