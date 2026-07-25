from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """Immutable record of who did what, when."""

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        VIEW = "view", "View"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        LOGIN_FAILED = "login_failed", "Login failed"
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        SUBMIT = "submit", "Submit"
        CANCEL = "cancel", "Cancel"
        EXPORT = "export", "Export"
        IMPORT = "import", "Import"
        SYNC = "sync", "Sync"
        OTHER = "other", "Other"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        db_index=True,
    )
    actor_email = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Snapshot of actor email (kept if user is deleted)",
    )
    actor_name = models.CharField(max_length=255, blank=True)

    action = models.CharField(
        max_length=32, choices=Action.choices, default=Action.OTHER, db_index=True
    )
    module = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="App area, e.g. people, payroll, attendance",
    )
    summary = models.CharField(max_length=500)
    detail = models.TextField(blank=True)

    object_type = models.CharField(max_length=120, blank=True, db_index=True)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    object_repr = models.CharField(max_length=255, blank=True)

    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=500, blank=True, db_index=True)
    view_name = models.CharField(max_length=120, blank=True, db_index=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["-created_at", "module"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]
        verbose_name = "activity log"
        verbose_name_plural = "activity logs"

    def __str__(self):
        who = self.actor_email or self.actor_name or "System"
        return f"{self.created_at:%Y-%m-%d %H:%M} · {who} · {self.summary}"

    @property
    def actor_display(self):
        if self.actor_name and self.actor_email:
            return f"{self.actor_name} ({self.actor_email})"
        return self.actor_email or self.actor_name or "System"
