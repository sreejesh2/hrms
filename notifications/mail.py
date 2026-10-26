"""In-app + optional email notifications."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .models import Notification

logger = logging.getLogger(__name__)


def absolute_link(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = getattr(settings, "SITE_URL", "") or ""
    if base:
        return base.rstrip("/") + path
    return path


def notify_user(
    user,
    *,
    title: str,
    body: str = "",
    level: str = Notification.Level.INFO,
    link: str = "",
    email: bool = True,
):
    """Create in-app notification and optionally email the user."""
    if not user:
        return None
    note = Notification.objects.create(
        recipient=user,
        title=title,
        body=body or "",
        level=level,
        link=link or "",
    )
    if email and getattr(settings, "HRMS_EMAIL_NOTIFICATIONS", True):
        _send_email(user, title=title, body=body, link=link)
    return note


def notify_approvers(assignee, *, fallback_perm: str, title: str, body: str = "", **kwargs):
    """
    Notify the employee's manager; if there is none, notify every user holding
    `fallback_perm` (e.g. HR via "leave.manage") so the request is not orphaned.
    """
    if assignee:
        notify_user(assignee, title=title, body=body, **kwargs)
        return
    from accounts.permissions import users_with_perm

    for user in users_with_perm(fallback_perm):
        notify_user(user, title=title, body=body, **kwargs)


def _send_email(user, *, title: str, body: str, link: str = ""):
    to = (getattr(user, "email", None) or "").strip()
    if not to:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@daypay.local"
    lines = [title, "", body or ""]
    if link:
        lines.extend(["", absolute_link(link)])
    lines.extend(["", "— Day Pay"])
    try:
        send_mail(
            subject=f"[Day Pay] {title}"[:200],
            message="\n".join(lines).strip(),
            from_email=from_email,
            recipient_list=[to],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Email notification failed for %s", to)
