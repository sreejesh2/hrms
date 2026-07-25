from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import request_has_perm
from core.pagination import paginate
from people.forms import make_master_form
from people.masters import MASTER_REGISTRY


def _get_master(master_key: str):
    cfg = MASTER_REGISTRY.get(master_key)
    if not cfg:
        raise Http404("Unknown master")
    return cfg


def _deny(request):
    messages.error(request, "You do not have permission to access that page.")
    return redirect("core:dashboard")


@login_required
def master_list(request, master_key):
    cfg = _get_master(master_key)
    if not request_has_perm(request, cfg["view_perm"]):
        return _deny(request)

    model = cfg["model"]
    qs = model.objects.all()
    if master_key == "departments":
        qs = qs.select_related("division", "default_shift", "default_calendar")
    q = request.GET.get("q", "").strip()
    if q:
        search_q = Q(code__icontains=q) | Q(description__icontains=q)
        if master_key == "departments":
            search_q = search_q | Q(division__description__icontains=q) | Q(
                division__code__icontains=q
            )
        qs = qs.filter(search_q).distinct()
    page_obj = paginate(request, qs)
    return render(
        request,
        "setup/master_list.html",
        {
            "page_title": cfg["plural"],
            "cfg": cfg,
            "master_key": master_key,
            "page_obj": page_obj,
            "q": q,
            "can_manage": request_has_perm(request, cfg["manage_perm"]),
            "show_division": master_key == "departments",
            "show_shift_defaults": master_key == "departments",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def master_create(request, master_key):
    cfg = _get_master(master_key)
    if not request_has_perm(request, cfg["manage_perm"]):
        return _deny(request)

    Form = make_master_form(cfg["model"])
    form = Form(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{cfg['singular']} created.")
        return redirect("setup:master_list", master_key=master_key)
    return render(
        request,
        "setup/master_form.html",
        {
            "page_title": f"New {cfg['singular']}",
            "form": form,
            "cfg": cfg,
            "master_key": master_key,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def master_edit(request, master_key, pk):
    cfg = _get_master(master_key)
    if not request_has_perm(request, cfg["manage_perm"]):
        return _deny(request)

    obj = get_object_or_404(cfg["model"], pk=pk)
    Form = make_master_form(cfg["model"])
    form = Form(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{cfg['singular']} updated.")
        return redirect("setup:master_list", master_key=master_key)
    return render(
        request,
        "setup/master_form.html",
        {
            "page_title": f"Edit {cfg['singular']}",
            "form": form,
            "cfg": cfg,
            "master_key": master_key,
            "object": obj,
        },
    )


@login_required
@require_http_methods(["POST"])
def master_delete(request, master_key, pk):
    cfg = _get_master(master_key)
    if not request_has_perm(request, cfg["manage_perm"]):
        return _deny(request)

    obj = get_object_or_404(cfg["model"], pk=pk)
    obj.delete()
    messages.success(request, f"{cfg['singular']} deleted.")
    return redirect("setup:master_list", master_key=master_key)
