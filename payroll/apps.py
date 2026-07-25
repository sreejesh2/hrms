from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payroll"
    verbose_name = "Payroll"

    def ready(self):
        from django.db.models.signals import post_migrate

        def seed_payroll(sender, **kwargs):
            if sender.name != "payroll":
                return
            from payroll.incentives import seed_default_incentive_plans
            from payroll.services import seed_default_components
            from payroll.statutory import seed_default_statutory_rules

            seed_default_components()
            seed_default_statutory_rules()
            seed_default_incentive_plans()

        post_migrate.connect(seed_payroll, sender=self)
