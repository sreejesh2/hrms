from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import permission_required
from reports.export import export_response
from reports.registry import get_report, reports_by_category


@permission_required("reports.view")
def home(request):
    return render(
        request,
        "reports/home.html",
        {
            "page_title": "Reports",
            "categories": reports_by_category(),
        },
    )


@permission_required("reports.view")
@require_http_methods(["GET", "POST"])
def run_report(request, slug: str):
    spec = get_report(slug)
    if not spec:
        messages.error(request, "Unknown report.")
        return redirect("reports:home")

    form = spec.form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fmt = (request.POST.get("format") or "xlsx").lower()
        if fmt not in ("xlsx", "pdf"):
            fmt = "xlsx"
        try:
            doc = spec.builder(form)
            return export_response(doc, fmt)
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("reports:run", slug=slug)

    return render(
        request,
        "reports/run.html",
        {
            "page_title": spec.title,
            "spec": spec,
            "form": form,
        },
    )
