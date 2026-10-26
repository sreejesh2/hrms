import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

MEDIA_TMP = tempfile.mkdtemp(prefix="daypay-media-test-")


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class ProtectedMediaTests(TestCase):
    """Uploaded files are served only to logged-in users allowed to see them."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TMP, ignore_errors=True)

    def setUp(self):
        from accounts.models import Role
        from accounts.rbac import seed_rbac
        from people.models import Employee, EmployeeDocument

        seed_rbac()
        User = get_user_model()
        self.hr = User.objects.create_user(email="hr@example.com", password="x")
        self.hr.roles.set([Role.objects.get(name="HR")])
        self.owner = User.objects.create_user(email="owner@example.com", password="x")
        self.owner.roles.set([Role.objects.get(name="Employee")])
        self.other = User.objects.create_user(email="other@example.com", password="x")
        self.other.roles.set([Role.objects.get(name="Employee")])

        self.employee = Employee.objects.create(
            employee_code="DOC-1", first_name="Doc", last_name="Owner", user=self.owner
        )
        self.doc = EmployeeDocument.objects.create(
            employee=self.employee,
            title="Passport",
            file=SimpleUploadedFile("passport.pdf", b"%PDF-secret"),
        )
        self.url = self.doc.file.url

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_hr_can_open_employee_document(self):
        self.client.force_login(self.hr)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-secret")

    def test_employee_can_open_own_document(self):
        self.client.force_login(self.owner)

        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_other_employee_cannot_open_document(self):
        self.client.force_login(self.other)

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_unknown_or_traversal_path_is_404(self):
        self.client.force_login(self.hr)

        self.assertEqual(self.client.get("/media/employee_docs/nope.pdf").status_code, 404)
        self.assertEqual(self.client.get("/media/../config/settings.py").status_code, 404)

    def test_expense_receipt_follows_claim_access(self):
        from expenses.models import ExpenseCategory, ExpenseClaim, ExpenseLine

        claim = ExpenseClaim.objects.create(
            employee=self.employee,
            title="Taxi",
            total_amount=Decimal("10.00"),
            requested_by=self.owner,
        )
        category, _ = ExpenseCategory.objects.get_or_create(code="TEST-RCPT", defaults={"name": "Test"})
        line = ExpenseLine.objects.create(
            claim=claim,
            category=category,
            amount=Decimal("10.00"),
            expense_date=date(2026, 7, 1),
            receipt=SimpleUploadedFile("r.jpg", b"img"),
        )

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(line.receipt.url).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(line.receipt.url).status_code, 404)
