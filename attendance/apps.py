from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "attendance"
    verbose_name = "Attendance"

    def ready(self):
        from django.db.models.signals import post_migrate

        def seed_ot(sender, **kwargs):
            if sender.name != "attendance":
                return
            from attendance.ot import seed_default_ot_policy

            seed_default_ot_policy()

        post_migrate.connect(seed_ot, sender=self)
