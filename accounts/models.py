from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class AppPermission(models.Model):
    """
    Dynamic permission catalog.
    codename examples: people.view_employees, setup.manage_roles
    """

    module = models.CharField(max_length=64, db_index=True)
    codename = models.CharField(max_length=120, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("module", "codename")

    def __str__(self):
        return f"{self.codename} — {self.name}"


class Role(models.Model):
    """Fully dynamic role — create any role and attach permissions."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    permissions = models.ManyToManyField(
        AppPermission, blank=True, related_name="roles"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Email is the login identity — no username."""

    username = None
    email = models.EmailField("email address", unique=True, db_index=True)
    roles = models.ManyToManyField(Role, blank=True, related_name="users")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email

    def permission_codenames(self) -> set[str]:
        if not self.is_authenticated:
            return set()
        if self.is_superuser:
            return set(
                AppPermission.objects.filter(is_active=True).values_list(
                    "codename", flat=True
                )
            )
        return set(
            AppPermission.objects.filter(
                is_active=True,
                roles__is_active=True,
                roles__users=self,
            )
            .values_list("codename", flat=True)
            .distinct()
        )

    def has_hrms_perm(self, codename: str) -> bool:
        if not self.is_authenticated:
            return False
        if self.is_superuser:
            return True
        return AppPermission.objects.filter(
            codename=codename,
            is_active=True,
            roles__is_active=True,
            roles__users=self,
        ).exists()

    def has_any_hrms_perm(self, *codenames: str) -> bool:
        if self.is_superuser:
            return True
        return any(self.has_hrms_perm(c) for c in codenames)
