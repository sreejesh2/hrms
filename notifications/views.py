from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.pagination import paginate

from .models import Notification


@login_required
def inbox(request):
    qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")
    page_obj = paginate(request, qs, per_page=40)
    return render(
        request,
        "notifications/inbox.html",
        {
            "page_title": "Notifications",
            "page_obj": page_obj,
            "notifications": page_obj,
        },
    )


@login_required
@require_POST
def mark_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, recipient=request.user)
    note.is_read = True
    note.save(update_fields=["is_read"])
    return redirect("notifications:inbox")
