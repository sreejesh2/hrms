"""Employee login provisioning — create/link User + HRMS role."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction

from accounts.models import Role

User = get_user_model()


class LoginProvisionError(ValueError):
    pass


def default_employee_role():
    role, _ = Role.objects.get_or_create(
        name="Employee",
        defaults={
            "description": "Self-service basics",
            "is_active": True,
        },
    )
    return role


@transaction.atomic
def provision_employee_login(
    employee,
    *,
    email: str,
    password: str,
    role_name: str = "Employee",
    update_password_if_exists: bool = True,
):
    """
    Ensure the employee has a linked login:
    - create User if email is new
    - or link an existing User that is not already tied to another employee
    Assign the chosen role (adds if missing) and set password.
    """
    if employee.user_id:
        raise LoginProvisionError("This employee already has a login linked.")

    email = (email or "").strip().lower()
    if not email:
        raise LoginProvisionError("Email is required to create a login.")
    if not password:
        raise LoginProvisionError("Password is required.")

    role = Role.objects.filter(name=role_name, is_active=True).first()
    if role is None:
        if role_name == "Employee":
            role = default_employee_role()
        else:
            raise LoginProvisionError(f"Role “{role_name}” was not found.")

    existing = User.objects.filter(email__iexact=email).first()
    if existing:
        linked = getattr(existing, "employee_profile", None)
        if linked and linked.pk != employee.pk:
            raise LoginProvisionError(
                f"{email} is already linked to {linked.employee_code} ({linked.full_name})."
            )
        user = existing
        if update_password_if_exists:
            user.set_password(password)
        if not user.first_name and employee.first_name:
            user.first_name = employee.first_name
        if not user.last_name and employee.last_name:
            user.last_name = employee.last_name
        user.is_active = True
        user.save()
    else:
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=employee.first_name or "",
            last_name=employee.last_name or "",
        )

    if not user.roles.filter(pk=role.pk).exists():
        user.roles.add(role)

    employee.user = user
    update_fields = ["user"]
    if not employee.email:
        employee.email = email
        update_fields.append("email")
    employee.save(update_fields=update_fields)

    return user


@transaction.atomic
def reset_employee_login_password(employee, *, password: str):
    if not employee.user_id:
        raise LoginProvisionError("This employee has no login yet.")
    if not password:
        raise LoginProvisionError("Password is required.")
    user = employee.user
    user.set_password(password)
    user.save(update_fields=["password"])
    return user


@transaction.atomic
def unlink_employee_login(employee):
    if not employee.user_id:
        raise LoginProvisionError("This employee has no login linked.")
    employee.user = None
    employee.save(update_fields=["user"])
    return employee
