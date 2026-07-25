from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor_email",
        "action",
        "module",
        "summary",
        "request_path",
        "ip_address",
    )
    list_filter = ("action", "module", "created_at")
    search_fields = (
        "summary",
        "detail",
        "actor_email",
        "actor_name",
        "request_path",
        "view_name",
        "object_repr",
    )
    readonly_fields = [f.name for f in ActivityLog._meta.fields]
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
