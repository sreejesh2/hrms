"""Capture mutating web requests into the activity log."""

from django.utils.deprecation import MiddlewareMixin

from .services import log_request

SKIP_PREFIXES = (
    "/static/",
    "/media/",
    "/__debug__/",
    "/favicon",
    "/iclock/",
    "/api/",
)

SKIP_VIEW_NAMES = {
    "audit:log_list",
    "audit:log_detail",
    "notifications:mark_read",
    "notifications:mark_all_read",
    "core:theme_toggle",
    "accounts:login",  # covered by auth signals
    "accounts:logout",
}

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class ActivityLogMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        try:
            if request.method not in MUTATING:
                return response
            status = getattr(response, "status_code", 500)
            if status >= 400:
                return response
            path = request.path or ""
            if any(path.startswith(p) for p in SKIP_PREFIXES):
                return response
            match = getattr(request, "resolver_match", None)
            if match and match.url_name:
                view_name = (
                    f"{match.namespace}:{match.url_name}"
                    if match.namespace
                    else match.url_name
                )
                if view_name in SKIP_VIEW_NAMES:
                    return response
            # Avoid logging password fields: never store POST body
            log_request(request, response)
        except Exception:
            # Logging must never break the response
            pass
        return response
