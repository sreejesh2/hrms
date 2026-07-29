"""Safe return-path helpers for attendance detail screens."""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def return_url(request) -> str:
    candidate = (request.GET.get("next") or request.POST.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return ""


def url_with_return(view_name, *, return_to="", kwargs=None) -> str:
    url = reverse(view_name, kwargs=kwargs)
    if return_to:
        return f"{url}?{urlencode({'next': return_to})}"
    return url
