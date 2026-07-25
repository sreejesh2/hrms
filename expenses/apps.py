from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "expenses"
    verbose_name = "Reimbursements"

    def ready(self):
        from django.db.models.signals import post_migrate

        def seed_expenses(sender, **kwargs):
            if sender.name != "expenses":
                return
            from expenses.services import seed_default_categories

            seed_default_categories()

        post_migrate.connect(seed_expenses, sender=self)
