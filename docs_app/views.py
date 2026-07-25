from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from .catalog import MODULES, get_module


def _with_urls(module: dict) -> dict:
    """Resolve optional deep links; skip broken reverses quietly."""
    screens = []
    for item in module.get("screens") or []:
        row = dict(item)
        url_name = item.get("url_name")
        kwargs = item.get("url_kwargs") or {}
        if url_name:
            try:
                row["url"] = reverse(url_name, kwargs=kwargs)
            except NoReverseMatch:
                row["url"] = None
        screens.append(row)
    out = dict(module)
    out["screens"] = screens
    return out


@login_required
def docs_home(request):
    modules = [_with_urls(m) for m in MODULES]
    return render(
        request,
        "docs/home.html",
        {
            "page_title": "Documentation",
            "modules": modules,
        },
    )


@login_required
def docs_module(request, slug):
    module = get_module(slug)
    if not module:
        raise Http404("Unknown documentation module")
    module = _with_urls(module)
    # Adjacent modules for prev/next
    slugs = [m["slug"] for m in MODULES]
    idx = slugs.index(slug)
    prev_mod = MODULES[idx - 1] if idx > 0 else None
    next_mod = MODULES[idx + 1] if idx < len(slugs) - 1 else None
    return render(
        request,
        "docs/module.html",
        {
            "page_title": f"Docs · {module['title']}",
            "module": module,
            "prev_mod": prev_mod,
            "next_mod": next_mod,
            "all_modules": MODULES,
        },
    )
