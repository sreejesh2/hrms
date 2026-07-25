from django.apps import AppConfig


class PerformanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "performance"
    verbose_name = "Performance"

    def ready(self):
        from django.db.models.signals import post_migrate

        def seed_performance(sender, **kwargs):
            if sender.name != "performance":
                return
            from performance.services import seed_default_competencies

            seed_default_competencies()

        post_migrate.connect(seed_performance, sender=self)
