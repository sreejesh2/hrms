from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.forms import ProfileForm, ProfilePasswordChangeForm
from accounts.permissions import request_has_perm


def _profile_initials(user, employee=None):
    if employee:
        parts = f"{employee.first_name} {employee.last_name}".strip().split()
        if parts:
            return "".join(p[0] for p in parts[:2]).upper()
    name = (user.get_full_name() or "").strip()
    if name:
        parts = name.split()
        return "".join(p[0] for p in parts[:2]).upper()
    return (user.email or "?")[:1].upper()


def _quick_links(request, employee):
    links = []
    if employee and request_has_perm(request, "people.view_employees"):
        links.append(
            {
                "label": "My employee record",
                "hint": employee.employee_code,
                "href": reverse("people:employee_detail", args=[employee.pk]),
            }
        )
    if request_has_perm(request, "leave.view") or request_has_perm(request, "leave.request"):
        links.append(
            {
                "label": "My leave",
                "hint": "Balances & requests",
                "href": reverse("leave:list") + "?scope=mine",
            }
        )
    if request_has_perm(request, "attendance.view") or request_has_perm(
        request, "attendance.request_regularization"
    ):
        links.append(
            {
                "label": "Attendance corrections",
                "hint": "My requests",
                "href": reverse("attendance_ops:regularization_list") + "?scope=mine",
            }
        )
    if request_has_perm(request, "expenses.view") or request_has_perm(
        request, "expenses.request"
    ):
        links.append(
            {
                "label": "My reimbursements",
                "hint": "Claims & payouts",
                "href": reverse("expenses:list") + "?scope=mine",
            }
        )
    if request_has_perm(request, "performance.view") or request_has_perm(
        request, "performance.manage"
    ):
        links.append(
            {
                "label": "My reviews",
                "hint": "Performance",
                "href": reverse("performance:list") + "?scope=mine",
            }
        )
    links.append(
        {
            "label": "Notifications",
            "hint": "Inbox",
            "href": reverse("notifications:inbox"),
        }
    )
    return links


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    user = request.user
    employee = getattr(user, "employee_profile", None)
    profile_form = ProfileForm(instance=user)
    password_form = ProfilePasswordChangeForm(user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("accounts:profile")
            messages.error(request, "Fix the highlighted profile fields.")
        elif action == "change_password":
            password_form = ProfilePasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password changed.")
                return redirect("accounts:profile")
            messages.error(request, "Could not change password. Check the form.")

    roles = list(user.roles.filter(is_active=True).order_by("name"))
    perms = sorted(getattr(request, "hrms_perms", set()) or set())
    module_counts = {}
    for code in perms:
        module = code.split(".", 1)[0] if "." in code else "other"
        module_counts[module] = module_counts.get(module, 0) + 1

    return render(
        request,
        "accounts/profile.html",
        {
            "page_title": "My profile",
            "employee": employee,
            "profile_form": profile_form,
            "password_form": password_form,
            "roles": roles,
            "perm_modules": sorted(module_counts.items()),
            "perm_count": len(perms),
            "quick_links": _quick_links(request, employee),
            "initials": _profile_initials(user, employee),
            "display_name": (
                (employee.full_name if employee else None)
                or user.get_full_name()
                or user.email
            ),
        },
    )
