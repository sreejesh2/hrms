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


def run_all_seeders():
    """Everything post_migrate runs on every `migrate` (i.e. every update)."""
    from attendance.ot import (
        seed_company_ot_policies,
        seed_default_late_penalty_policy,
        seed_default_ot_policy,
    )
    from expenses.services import seed_default_categories
    from leave.services import seed_default_leave_types
    from payroll.incentives import seed_default_incentive_plans
    from payroll.services import seed_default_components
    from payroll.statutory import seed_default_statutory_rules
    from performance.services import seed_default_competencies

    seed_default_ot_policy()
    seed_company_ot_policies()
    seed_default_late_penalty_policy()
    seed_default_leave_types()
    seed_default_components()
    seed_default_statutory_rules()
    seed_default_incentive_plans()
    seed_default_categories()
    seed_default_competencies()


class SeedersKeepUserSettingsTests(TestCase):
    """Running migrate again (app update) must not undo HR's configuration."""

    def setUp(self):
        run_all_seeders()

    def test_payroll_and_attendance_settings_survive_reseed(self):
        from attendance.models import LatePenaltyTier, OvertimePolicy
        from leave.models import LeaveType
        from payroll.models import SalaryComponent, StatutoryRule

        SalaryComponent.objects.filter(code="HRA").update(
            calc_method=SalaryComponent.CalcMethod.PERCENT_BASIC,
            default_percent=Decimal("25.00"),
            name="Housing",
        )
        OvertimePolicy.objects.filter(code="STD").update(weekday_rate=Decimal("1.75"))
        OvertimePolicy.objects.filter(code="WRK-DAY").update(holiday_rate=Decimal("2.00"))
        tier = LatePenaltyTier.objects.filter(policy__code="STD-LATE").order_by("sort_order").first()
        LatePenaltyTier.objects.filter(pk=tier.pk).update(deduct_minutes=30)
        rule = StatutoryRule.objects.order_by("code").first()
        StatutoryRule.objects.filter(pk=rule.pk).update(is_active=not rule.is_active)
        LeaveType.objects.filter(code="SL").update(
            default_entitlement=Decimal("15.0"), is_active=False
        )

        run_all_seeders()

        hra = SalaryComponent.objects.get(code="HRA")
        self.assertEqual(
            (hra.calc_method, hra.default_percent, hra.name),
            (SalaryComponent.CalcMethod.PERCENT_BASIC, Decimal("25.00"), "Housing"),
        )
        self.assertEqual(OvertimePolicy.objects.get(code="STD").weekday_rate, Decimal("1.75"))
        self.assertEqual(OvertimePolicy.objects.get(code="WRK-DAY").holiday_rate, Decimal("2.00"))
        self.assertTrue(LatePenaltyTier.objects.filter(pk=tier.pk, deduct_minutes=30).exists())
        self.assertEqual(StatutoryRule.objects.get(pk=rule.pk).is_active, not rule.is_active)
        sick = LeaveType.objects.get(code="SL")
        self.assertEqual((sick.default_entitlement, sick.is_active), (Decimal("15.0"), False))

    def test_changed_default_ot_policy_is_kept(self):
        from attendance.models import OvertimePolicy

        OvertimePolicy.objects.update(is_default=False)
        OvertimePolicy.objects.filter(code="WRK-DAY").update(is_default=True)

        run_all_seeders()

        self.assertEqual(
            list(OvertimePolicy.objects.filter(is_default=True).values_list("code", flat=True)),
            ["WRK-DAY"],
        )

    def test_deleted_defaults_are_created_again(self):
        from expenses.models import ExpenseCategory
        from leave.models import LeaveType

        LeaveType.objects.filter(code="CL").delete()
        ExpenseCategory.objects.all().delete()

        run_all_seeders()

        self.assertTrue(LeaveType.objects.filter(code="CL").exists())
        self.assertTrue(ExpenseCategory.objects.exists())


class SeedCommandSafetyTests(TestCase):
    def test_plain_seed_does_not_create_demo_admin(self):
        from django.core.management import call_command

        call_command("seed", verbosity=0, stdout=open("/dev/null", "w"))

        self.assertFalse(get_user_model().objects.filter(email="admin@example.com").exists())

    def test_seed_admin_flag_still_creates_demo_admin(self):
        from django.core.management import call_command

        call_command("seed", "--admin", verbosity=0, stdout=open("/dev/null", "w"))

        self.assertTrue(get_user_model().objects.filter(email="admin@example.com").exists())

    def test_rerunning_ot_rules_keeps_edited_shift_times(self):
        from datetime import time

        from attendance.models import WorkCalendar, WorkShift, WorkShiftVersion
        from attendance.ot import seed_overtime_sheet_rules

        seed_overtime_sheet_rules()
        day = WorkShift.objects.get(code="DAY")
        WorkShiftVersion.objects.filter(shift=day).update(shift_from=time(6, 0))
        WorkCalendar.objects.filter(code="UAE-STD").update(sunday=True, friday=False)

        seed_overtime_sheet_rules()

        self.assertEqual(
            list(WorkShiftVersion.objects.filter(shift=day).values_list("shift_from", flat=True)),
            [time(6, 0)],
        )
        cal = WorkCalendar.objects.get(code="UAE-STD")
        self.assertEqual((cal.sunday, cal.friday), (True, False))


class ThemeSwitchRedirectTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(email="theme@example.com", password="x")
        self.client.force_login(user)

    def test_redirects_back_to_app_page(self):
        response = self.client.post("/theme/", {"theme": "dark", "next": "/leave/"})

        self.assertEqual(response["Location"], "/leave/")
        self.assertEqual(response.cookies["hrms_theme"].value, "dark")

    def test_external_next_url_is_ignored(self):
        response = self.client.post("/theme/", {"theme": "dark", "next": "https://evil.example/"})

        self.assertEqual(response["Location"], "/")
