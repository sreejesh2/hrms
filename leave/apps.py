from django.apps import AppConfig


class LeaveConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "leave"
    verbose_name = "Leave"

    def ready(self):
        from django.db.models.signals import post_migrate

        def seed_leave(sender, **kwargs):
            if sender.name != "leave":
                return
            from leave.services import seed_default_leave_types

            seed_default_leave_types()

        post_migrate.connect(seed_leave, sender=self)
