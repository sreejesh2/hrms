from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from notifications.models import Notification
from people.models import Employee

from .models import ExpenseCategory
from .services import submit_claim


class NoManagerClaimTests(TestCase):
    def test_claim_without_manager_notifies_expense_managers(self):
        from accounts.models import Role
        from accounts.rbac import seed_rbac

        seed_rbac()
        User = get_user_model()
        hr = User.objects.create_user(email="hr-exp@example.com", password="x")
        hr.roles.set([Role.objects.get(name="HR")])
        worker = User.objects.create_user(email="exp-worker@example.com", password="x")
        employee = Employee.objects.create(employee_code="EXP-1", first_name="E", user=worker)
        category, _ = ExpenseCategory.objects.get_or_create(
            code="TEST-NR", defaults={"name": "No receipt", "requires_receipt": False}
        )

        submit_claim(
            employee=employee,
            title="Taxi",
            purpose="",
            currency="AED",
            requested_by=worker,
            line_rows=[
                {"category": category, "amount": Decimal("10.00"), "expense_date": date(2026, 7, 1)}
            ],
        )

        self.assertTrue(
            Notification.objects.filter(recipient=hr, title="Reimbursement claim pending").exists()
        )
