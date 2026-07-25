"""Shared list pagination for function-based views."""

from __future__ import annotations

from django.core.paginator import Paginator
from django.http import QueryDict


def paginate(request, queryset, *, per_page: int = 25, page_param: str = "page"):
    """Return a Django Page object for the given queryset."""
    try:
        size = int(request.GET.get("per_page") or per_page)
    except (TypeError, ValueError):
        size = per_page
    size = max(10, min(size, 100))
    return Paginator(queryset, size).get_page(request.GET.get(page_param) or 1)


def querystring_without_page(request, *, page_param: str = "page") -> str:
    """Build `&foo=bar` query string excluding the page param (for pagination links)."""
    qd = request.GET.copy()
    qd.pop(page_param, None)
    encoded = qd.urlencode()
    return f"&{encoded}" if encoded else ""
