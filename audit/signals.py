from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .models import ActivityLog
from .services import log_event


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    log_event(
        summary="Signed in",
        action=ActivityLog.Action.LOGIN,
        module="accounts",
        actor=user,
        request=request,
        view_name="accounts:login",
        object_type="user",
        object_id=user.pk,
        object_repr=getattr(user, "email", "") or str(user),
    )


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    log_event(
        summary="Signed out",
        action=ActivityLog.Action.LOGOUT,
        module="accounts",
        actor=user,
        request=request,
        view_name="accounts:logout",
        object_type="user",
        object_id=getattr(user, "pk", "") or "",
        object_repr=getattr(user, "email", "") if user else "",
    )


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request, **kwargs):
    email = ""
    if isinstance(credentials, dict):
        email = (
            credentials.get("username")
            or credentials.get("email")
            or ""
        )
    log_event(
        summary=f"Failed sign-in attempt ({email or 'unknown'})",
        action=ActivityLog.Action.LOGIN_FAILED,
        module="accounts",
        actor=None,
        request=request,
        view_name="accounts:login",
        detail=f"username={email}"[:500],
        metadata={"username": str(email)[:120]},
    )
