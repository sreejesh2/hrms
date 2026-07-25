from django.utils.deprecation import MiddlewareMixin


class RBACMiddleware(MiddlewareMixin):
    """Attach request.hrms_perms (set of codenames) once per request — avoids N+1 checks."""

    def process_request(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            request.hrms_perms = user.permission_codenames()
        else:
            request.hrms_perms = set()
