"""Write activity log entries (safe to call from views, signals, middleware)."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model

from .models import ActivityLog

logger = logging.getLogger(__name__)

# URL name → human summary. Method-specific overrides use "method:url_name".
VIEW_SUMMARIES: dict[str, str] = {
    "people:employee_create": "Created employee",
    "people:employee_import": "Imported employees",
    "people:employee_edit": "Updated employee",
    "people:document_delete": "Deleted employee document",
    "people:employee_login": "Managed employee login",
    "people:employee_device_enroll": "Queued employee on ZKTeco device",
    "accounts:login": "Signed in",
    "accounts:logout": "Signed out",
    "accounts:profile": "Updated profile",
    "attendance:device_create": "Created punch device",
    "attendance:device_edit": "Updated punch device",
    "attendance:device_delete": "Deleted punch device",
    "attendance:device_rotate_token": "Rotated device API token",
    "attendance:device_sync_time": "Queued device time sync",
    "attendance:device_check": "Queued device CHECK",
    "attendance:device_resend_punches": "Queued device punch re-send",
    "attendance:device_enroll": "Queued device enroll / user push",
    "attendance_ops:punch_create": "Created manual punch",
    "attendance_ops:punch_delete": "Deleted punch",
    "attendance_ops:punch_import": "Imported punches",
    "attendance_ops:daily_generate": "Generated daily attendance",
    "leave:request_create": "Applied for leave",
    "leave:request_approve": "Approved leave",
    "leave:request_reject": "Rejected leave",
    "leave:request_cancel": "Cancelled leave",
    "payroll:period_run": "Ran payroll period",
    "payroll:period_lock": "Locked payroll period",
    "expenses:claim_submit": "Submitted reimbursement",
    "expenses:claim_approve": "Approved reimbursement",
    "expenses:claim_reject": "Rejected reimbursement",
    "setup:organization_settings": "Updated company settings",
    "setup:role_create": "Created role",
    "setup:role_edit": "Updated role",
    "setup:user_role_edit": "Updated user roles",
}


def _client_ip(request) -> str | None:
    if not request:
        return None
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or None


def _actor_snapshot(user) -> tuple[Any, str, str]:
    if not user or not getattr(user, "is_authenticated", False):
        return None, "", "Anonymous"
    email = (getattr(user, "email", None) or getattr(user, "username", "") or "")[:255]
    name = ""
    for attr in ("get_full_name", "full_name"):
        fn = getattr(user, attr, None)
        if callable(fn):
            name = (fn() or "").strip()
            break
        if isinstance(fn, str):
            name = fn.strip()
            break
    if not name:
        name = email or f"User #{getattr(user, 'pk', '')}"
    return user, email, name[:255]


def infer_action(method: str = "", view_name: str = "", path: str = "") -> str:
    blob = f"{view_name} {path}".lower()
    if "login" in blob and "logout" not in blob:
        return ActivityLog.Action.LOGIN
    if "logout" in blob:
        return ActivityLog.Action.LOGOUT
    if any(k in blob for k in ("approve", "accept")):
        return ActivityLog.Action.APPROVE
    if any(k in blob for k in ("reject", "deny")):
        return ActivityLog.Action.REJECT
    if "cancel" in blob:
        return ActivityLog.Action.CANCEL
    if "submit" in blob:
        return ActivityLog.Action.SUBMIT
    if "import" in blob:
        return ActivityLog.Action.IMPORT
    if "export" in blob or "download" in blob or "pdf" in blob or "excel" in blob:
        return ActivityLog.Action.EXPORT
    if "sync" in blob or "enroll" in blob or "rotate" in blob:
        return ActivityLog.Action.SYNC
    if any(k in blob for k in ("delete", "remove", "destroy")):
        return ActivityLog.Action.DELETE
    if any(k in blob for k in ("create", "new", "add", "apply")):
        return ActivityLog.Action.CREATE
    if method.upper() == "POST" and any(
        k in blob for k in ("edit", "update", "save", "settings", "profile")
    ):
        return ActivityLog.Action.UPDATE
    if method.upper() == "DELETE":
        return ActivityLog.Action.DELETE
    if method.upper() in ("POST", "PUT", "PATCH"):
        return ActivityLog.Action.UPDATE
    return ActivityLog.Action.OTHER


def infer_module(view_name: str = "", path: str = "") -> str:
    if view_name and ":" in view_name:
        ns = view_name.split(":", 1)[0]
        if ns.startswith("attendance"):
            return "attendance"
        if ns in ("accounts", "setup", "people", "leave", "payroll", "expenses", "performance", "reports", "notifications", "core", "audit"):
            return ns
        return ns
    parts = [p for p in (path or "").strip("/").split("/") if p]
    if not parts:
        return "core"
    if parts[0] == "settings" and len(parts) > 1 and parts[1] == "time":
        return "attendance"
    if parts[0] == "settings":
        return "setup"
    if parts[0] == "api":
        return parts[1] if len(parts) > 1 else "api"
    return parts[0][:64]


def summarize_view(method: str, view_name: str, path: str) -> str:
    key = f"{method.upper()}:{view_name}" if view_name else ""
    if key and key in VIEW_SUMMARIES:
        return VIEW_SUMMARIES[key]
    if view_name and view_name in VIEW_SUMMARIES:
        return VIEW_SUMMARIES[view_name]
    if view_name:
        label = view_name.replace(":", " · ").replace("_", " ")
        return f"{method.upper()} · {label}"[:500]
    return f"{method.upper()} {path}"[:500]


def log_event(
    *,
    summary: str,
    action: str = ActivityLog.Action.OTHER,
    module: str = "",
    actor=None,
    request=None,
    detail: str = "",
    object_type: str = "",
    object_id: str | int | None = "",
    object_repr: str = "",
    view_name: str = "",
    status_code: int | None = None,
    metadata: dict | None = None,
) -> ActivityLog | None:
    """Persist one activity log row. Never raises to callers."""
    try:
        user = actor
        if user is None and request is not None:
            user = getattr(request, "user", None)
        user_obj, email, name = _actor_snapshot(user)

        method = ""
        path = ""
        ua = ""
        ip = None
        if request is not None:
            method = request.method or ""
            path = (request.path or "")[:500]
            ua = (request.META.get("HTTP_USER_AGENT") or "")[:400]
            ip = _client_ip(request)
            if not view_name and getattr(request, "resolver_match", None):
                match = request.resolver_match
                if match and match.url_name:
                    view_name = (
                        f"{match.namespace}:{match.url_name}"
                        if match.namespace
                        else match.url_name
                    )
            if not module:
                module = infer_module(view_name, path)

        return ActivityLog.objects.create(
            actor=user_obj,
            actor_email=email,
            actor_name=name,
            action=action or ActivityLog.Action.OTHER,
            module=(module or "")[:64],
            summary=(summary or "Activity")[:500],
            detail=detail or "",
            object_type=(object_type or "")[:120],
            object_id=str(object_id or "")[:64],
            object_repr=(object_repr or "")[:255],
            request_method=method[:10],
            request_path=path,
            view_name=(view_name or "")[:120],
            status_code=status_code,
            ip_address=ip,
            user_agent=ua,
            metadata=metadata or {},
        )
    except Exception:
        logger.exception("Failed to write activity log")
        return None


def log_request(request, response) -> ActivityLog | None:
    """Log a successful mutating HTTP request."""
    match = getattr(request, "resolver_match", None)
    view_name = ""
    if match and match.url_name:
        view_name = (
            f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
        )
    path = request.path or ""
    method = request.method or ""
    module = infer_module(view_name, path)
    action = infer_action(method, view_name, path)
    summary = summarize_view(method, view_name, path)
    detail_bits = []
    if match and match.kwargs:
        detail_bits.append("params=" + ", ".join(f"{k}={v}" for k, v in match.kwargs.items()))
    return log_event(
        summary=summary,
        action=action,
        module=module,
        request=request,
        detail="; ".join(detail_bits),
        view_name=view_name,
        status_code=getattr(response, "status_code", None),
        object_id=str((match.kwargs or {}).get("pk") or "") if match else "",
        metadata={"query": (request.META.get("QUERY_STRING") or "")[:200]},
    )
