from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase


class EmployeeRoleAccessTests(TestCase):
    """An Employee login must not reach HR / payroll / admin pages or other people's data."""

    def setUp(self):
        from accounts.models import Role
        from accounts.rbac import seed_rbac
        from people.models import Employee

        seed_rbac()
        User = get_user_model()
        self.me = User.objects.create_user(email="me@example.com", password="x")
        self.me.roles.set([Role.objects.get(name="Employee")])
        self.other_user = User.objects.create_user(email="colleague@example.com", password="x")
        self.me_emp = Employee.objects.create(employee_code="ME", first_name="Me", user=self.me)
        self.other = Employee.objects.create(
            employee_code="OTHER", first_name="Other", user=self.other_user
        )
        self.client.force_login(self.me)

    def assertBlocked(self, url):
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404), url)
        if response.status_code == 302:
            self.assertNotEqual(response["Location"], url)

    def test_admin_and_hr_pages_are_blocked(self):
        for url in (
            "/people/",
            f"/people/{self.other.pk}/",
            "/payroll/",
            "/payroll/periods/",
            "/reports/",
            "/settings/access/roles/",
            "/settings/time/shifts/",
            "/audit/",
            "/attendance/daily/",
        ):
            with self.subTest(url=url):
                self.assertBlocked(url)

    def test_other_employees_leave_is_not_visible(self):
        from leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(code="ACL", name="Access test")
        req = LeaveRequest.objects.create(
            employee=self.other,
            leave_type=leave_type,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            days=Decimal("1"),
            reason="private",
            requested_by=self.other_user,
        )

        response = self.client.get(f"/leave/{req.pk}/")

        self.assertNotContains(response, "private", status_code=response.status_code)
        self.assertBlocked(f"/leave/{req.pk}/")

    def test_other_employees_claim_is_not_visible(self):
        from expenses.models import ExpenseClaim

        claim = ExpenseClaim.objects.create(
            employee=self.other,
            title="Secret dinner",
            total_amount=Decimal("50.00"),
            requested_by=self.other_user,
        )

        self.assertBlocked(f"/expenses/{claim.pk}/")

    def test_own_pages_are_allowed(self):
        for url in ("/leave/", "/expenses/", "/loans/", "/accounts/profile/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
