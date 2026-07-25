from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def seed_rbac_after_migrate(sender, **kwargs):
    if sender.name != "accounts":
        return
    from accounts.rbac import seed_rbac

    seed_rbac()
