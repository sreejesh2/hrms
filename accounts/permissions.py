from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def user_has_perm(user, codename: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return user.has_hrms_perm(codename)


def users_with_perm(codename: str):
    """Active users granted `codename` through an active role (or superusers)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    return (
        get_user_model()
        .objects.filter(is_active=True)
        .filter(
            Q(is_superuser=True)
            | Q(
                roles__is_active=True,
                roles__permissions__codename=codename,
                roles__permissions__is_active=True,
            )
        )
        .distinct()
    )


def request_has_perm(request, codename: str) -> bool:
    perms = getattr(request, "hrms_perms", None)
    if perms is not None:
        user = getattr(request, "user", None)
        if user is not None and user.is_superuser:
            return True
        return codename in perms
    return user_has_perm(getattr(request, "user", None), codename)


def permission_required(codename: str, *, raise_exception: bool = False):
    """Require an HRMS AppPermission codename (dynamic RBAC)."""

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request_has_perm(request, codename):
                return view_func(request, *args, **kwargs)
            if raise_exception:
                raise PermissionDenied
            messages.error(request, "You do not have permission to access that page.")
            return redirect("core:dashboard")

        return _wrapped

    return decorator


def any_permission_required(*codenames: str):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if any(request_has_perm(request, c) for c in codenames):
                return view_func(request, *args, **kwargs)
            messages.error(request, "You do not have permission to access that page.")
            return redirect("core:dashboard")

        return _wrapped

    return decorator
