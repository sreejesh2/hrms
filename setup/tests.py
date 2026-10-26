from django.contrib.auth import get_user_model
from django.test import TestCase


class SettingsHomeLinksTests(TestCase):
    """Settings home only shows cards the user is allowed to open."""

    def setUp(self):
        from accounts.rbac import seed_rbac

        seed_rbac()

    def login_as(self, role_name):
        from accounts.models import Role

        user = get_user_model().objects.create_user(email=f"{role_name}@example.com", password="x")
        user.roles.set([Role.objects.get(name=role_name)])
        self.client.force_login(user)

    def test_employee_sees_no_admin_cards(self):
        self.login_as("Employee")

        html = self.client.get("/settings/").content.decode()

        for href in ("/settings/access/roles/", "/settings/employee-fields/", "/settings/time/shifts/"):
            self.assertNotIn(href, html)
        self.assertIn("/docs/", html)

    def test_admin_sees_all_cards(self):
        self.login_as("Admin")

        html = self.client.get("/settings/").content.decode()

        for href in ("/settings/access/roles/", "/settings/employee-fields/", "/settings/time/shifts/"):
            self.assertIn(href, html)
