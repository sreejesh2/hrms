from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from notifications.models import Notification
from people.models import Employee

from .services import submit_advance


class NoManagerAdvanceTests(TestCase):
    def test_advance_without_manager_notifies_loan_managers(self):
        from accounts.models import Role
        from accounts.rbac import seed_rbac

        seed_rbac()
        User = get_user_model()
        payroll = User.objects.create_user(email="pay-adv@example.com", password="x")
        payroll.roles.set([Role.objects.get(name="Payroll")])
        worker = User.objects.create_user(email="adv-worker@example.com", password="x")
        employee = Employee.objects.create(employee_code="ADV-1", first_name="A", user=worker)

        submit_advance(
            employee=employee,
            amount=Decimal("500.00"),
            installments=2,
            reason="family",
            requested_by=worker,
        )

        self.assertTrue(
            Notification.objects.filter(recipient=payroll, title="Salary advance pending").exists()
        )
