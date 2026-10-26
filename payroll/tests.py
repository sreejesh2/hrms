"""Payroll calculation and company salary sheet tests."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from attendance.models import DailyAttendance
from people.models import Employee

from .models import SalaryComponent
from .run import _build_payslip, _short_hour_unpaid, create_period, run_period
from .services import create_structure, seed_default_components


class PayrollCompanySheetCalcTests(TestCase):
    def setUp(self):
        seed_default_components()
        # Keep statutory noise out of assertions
        from .models import StatutoryRule

        StatutoryRule.objects.filter(is_active=True).update(is_active=False)
        # Use fixed HRA amounts in tests (seed defaults HRA to % of basic)
        SalaryComponent.objects.filter(code="HRA").update(
            calc_method=SalaryComponent.CalcMethod.FIXED,
            default_percent=None,
        )

        self.employee = Employee.objects.create(
            employee_code="PAY-001",
            first_name="Pay",
            last_name="Sheet",
            status=Employee.Status.ACTIVE,
        )
        self.structure = create_structure(
            employee=self.employee,
            effective_from=date(2026, 1, 1),
            currency="AED",
            notes="test",
            lines=[
                {"component": SalaryComponent.objects.get(code="BASIC"), "amount": Decimal("2400.00")},
                {"component": SalaryComponent.objects.get(code="COL"), "amount": Decimal("600.00")},
                {"component": SalaryComponent.objects.get(code="FOOD"), "amount": Decimal("200.00")},
                {"component": SalaryComponent.objects.get(code="HRA"), "amount": Decimal("400.00")},
                {
                    "component": SalaryComponent.objects.get(code="EXTRA_ALLOW"),
                    "amount": Decimal("100.00"),
                },
                {
                    "component": SalaryComponent.objects.get(code="OTHER_DED"),
                    "amount": Decimal("50.00"),
                },
            ],
            created_by=None,
            template=None,
        )
        self.period = create_period(year=2026, month=7)

    def _by_code(self, slip):
        return {ln.code: ln.amount for ln in slip.lines.all()}

    def test_food_stays_fixed_when_unpaid_days(self):
        # One full absent day → Food still full 200; Basic/COL/HRA prorate
        DailyAttendance.objects.create(
            employee=self.employee,
            date=self.period.start_date,
            status=DailyAttendance.Status.ABSENT,
        )
        slip = _build_payslip(self.period, self.employee, self.structure)
        by = self._by_code(slip)
        factor = (slip.paid_days / Decimal(slip.calendar_days)).quantize(Decimal("0.0001"))

        self.assertEqual(by["FOOD"], Decimal("200.00"))
        self.assertEqual(by["BASIC"], (Decimal("2400.00") * factor).quantize(Decimal("0.01")))
        self.assertEqual(by["COL"], (Decimal("600.00") * factor).quantize(Decimal("0.01")))
        self.assertEqual(by["HRA"], (Decimal("400.00") * factor).quantize(Decimal("0.01")))
        self.assertEqual(slip.unpaid_days, Decimal("1.00"))

    def test_ot_amount_and_staged_totals(self):
        DailyAttendance.objects.create(
            employee=self.employee,
            date=self.period.start_date,
            status=DailyAttendance.Status.PRESENT,
            overtime_hours=Decimal("10.00"),
            ot_rate=Decimal("1.25"),
            hourly_divisor=240,
            special_ot_amount=Decimal("5.00"),
            expected_hours=Decimal("8.00"),
            payable_hours=Decimal("8.00"),
        )
        slip = _build_payslip(self.period, self.employee, self.structure)
        by = self._by_code(slip)

        # OT = (2400/240) × 10 × 1.25 = 10 × 1.25 × 10 = 125
        self.assertEqual(slip.ot_hours, Decimal("10.00"))
        self.assertEqual(slip.ot_amount, Decimal("125.00"))
        self.assertEqual(by["OT"], Decimal("125.00"))
        # Extra OT = 10 × 5 = 50
        self.assertEqual(slip.special_ot_amount, Decimal("50.00"))
        self.assertEqual(by["SPECIAL_OT"], Decimal("50.00"))
        # Total Salary = Basic + COL + OT (no Food/HRA/Extra OT)
        self.assertEqual(
            slip.total_salary,
            Decimal("2400.00") + Decimal("600.00") + Decimal("125.00"),
        )
        # Gross includes Food + HRA + Extra OT + Extra Allow
        expected_gross = (
            Decimal("2400.00")
            + Decimal("600.00")
            + Decimal("125.00")
            + Decimal("200.00")
            + Decimal("400.00")
            + Decimal("50.00")
            + Decimal("100.00")
        )
        self.assertEqual(slip.earnings_total, expected_gross)
        self.assertEqual(slip.deductions_total, Decimal("50.00"))
        self.assertEqual(slip.net_pay, expected_gross - Decimal("50.00"))

    def test_break_overrun_shortfall_counts_as_lwp(self):
        # Present day with break overrun already reducing payable (penalty_minutes=0)
        DailyAttendance.objects.create(
            employee=self.employee,
            date=self.period.start_date,
            status=DailyAttendance.Status.PRESENT,
            expected_hours=Decimal("8.00"),
            payable_hours=Decimal("7.00"),
            penalty_minutes=0,
            break_overrun_penalty_minutes=60,
        )
        unpaid = _short_hour_unpaid(
            self.employee, self.period.start_date, self.period.end_date
        )
        self.assertEqual(unpaid, Decimal("0.12"))  # 1/8 = 0.125 → 0.12

        slip = _build_payslip(self.period, self.employee, self.structure)
        self.assertGreater(slip.unpaid_days, Decimal("0.00"))
        by = self._by_code(slip)
        self.assertEqual(by["FOOD"], Decimal("200.00"))
        self.assertLess(by["BASIC"], Decimal("2400.00"))

    def test_company_salary_sheet_column_totals(self):
        from reports.builders.payroll import build_company_salary_sheet

        DailyAttendance.objects.create(
            employee=self.employee,
            date=self.period.start_date,
            status=DailyAttendance.Status.PRESENT,
            overtime_hours=Decimal("8.00"),
            ot_rate=Decimal("1.00"),
            hourly_divisor=240,
            special_ot_amount=Decimal("0.00"),
            expected_hours=Decimal("8.00"),
            payable_hours=Decimal("8.00"),
        )
        run_period(self.period)
        form = SimpleNamespace(cleaned_data={"period": self.period})
        doc = build_company_salary_sheet(form)
        sheet = doc.sheets[0]
        self.assertEqual(sheet.headers[0], "Sl.No")
        self.assertIn("Total Salary", sheet.headers)
        self.assertIn("Food Allow", sheet.headers)
        self.assertEqual(len(sheet.rows), 1)
        row = sheet.rows[0]
        # Indices match headers in build_company_salary_sheet
        basic, col, ot_hrs, ot_amt, total, food, hra, extra_ot, extra_allow, gross, other, net = (
            row[4],
            row[5],
            row[6],
            row[7],
            row[8],
            row[9],
            row[10],
            row[11],
            row[12],
            row[13],
            row[14],
            row[15],
        )
        self.assertEqual(basic, Decimal("2400.00"))
        self.assertEqual(col, Decimal("600.00"))
        self.assertEqual(ot_hrs, Decimal("8.00"))
        self.assertEqual(ot_amt, Decimal("80.00"))  # (2400/240)*8*1
        self.assertEqual(total, basic + col + ot_amt)
        self.assertEqual(food, Decimal("200.00"))
        self.assertEqual(hra, Decimal("400.00"))
        self.assertEqual(extra_ot, Decimal("0.00"))
        self.assertEqual(extra_allow, Decimal("100.00"))
        self.assertEqual(gross, total + food + hra + extra_ot + extra_allow)
        self.assertEqual(other, Decimal("50.00"))
        self.assertEqual(net, gross - other)

        from reports.payroll_pdf import build_company_salary_sheet_pdf

        self.assertEqual(
            doc.pdf_context["pdf_engine"],
            "reportlab_salary_sheet",
        )
        pdf = build_company_salary_sheet_pdf(
            title=doc.title,
            period_label=doc.pdf_context["period_label"],
            currency=doc.pdf_context["currency"],
            status_label=doc.pdf_context["status_label"],
            headers=sheet.headers,
            rows=sheet.rows,
        )
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 3000)

    def test_enhanced_monthly_payroll_register_pdf_renders(self):
        from reports.builders.payroll import build_payroll_register
        from reports.payroll_pdf import build_monthly_payroll_register_pdf

        run_period(self.period)
        form = SimpleNamespace(cleaned_data={"period": self.period})
        doc = build_payroll_register(form)
        self.assertEqual(
            doc.pdf_context["pdf_engine"],
            "reportlab_payroll_register",
        )
        pdf = build_monthly_payroll_register_pdf(
            title=doc.title,
            period_label=doc.pdf_context["period_label"],
            currency=doc.pdf_context["currency"],
            status_label=doc.pdf_context["status_label"],
            sheets=doc.sheets,
            earning_codes=doc.pdf_context["earning_codes"],
            deduction_codes=doc.pdf_context["deduction_codes"],
        )
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 4000)


class FoodComponentSeedTests(TestCase):
    def test_food_component_is_not_prorated_by_default(self):
        seed_default_components()
        food = SalaryComponent.objects.get(code="FOOD")
        self.assertFalse(food.prorate_with_attendance)
        for code in ("BASIC", "COL", "HRA", "EXTRA_ALLOW"):
            self.assertTrue(SalaryComponent.objects.get(code=code).prorate_with_attendance)

    def test_enhanced_sample_payslip_pdf_renders(self):
        from .pdf import render_sample_payslip_pdf

        pdf = render_sample_payslip_pdf()
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 3000)


class PayrollRunTestBase(TestCase):
    """Shared setup for run_period / lock_period behaviour tests."""

    def setUp(self):
        seed_default_components()
        from .models import StatutoryRule

        StatutoryRule.objects.filter(is_active=True).update(is_active=False)
        self.period = create_period(year=2026, month=7)

    def make_employee(self, code, basic="3000.00", **fields):
        employee = Employee.objects.create(
            employee_code=code,
            first_name=code,
            last_name="Test",
            status=fields.pop("status", Employee.Status.ACTIVE),
            **fields,
        )
        create_structure(
            employee=employee,
            effective_from=date(2026, 1, 1),
            currency="AED",
            notes="test",
            lines=[
                {"component": SalaryComponent.objects.get(code="BASIC"), "amount": Decimal(basic)},
            ],
            created_by=None,
            template=None,
        )
        return employee

    def assign_shift(self, employee):
        from attendance.models import ShiftAssignment, WorkShift

        shift, _ = WorkShift.objects.get_or_create(code="RUN-DAY", defaults={"name": "Run Day"})
        ShiftAssignment.objects.create(
            employee=employee, shift=shift, effective_from=date(2026, 1, 1)
        )

    def slip_for(self, employee, period=None):
        return (period or self.period).payslips.get(employee=employee)

    def working_days(self, period):
        from datetime import timedelta

        days, cur = 0, period.start_date
        while cur <= period.end_date:
            days += cur.weekday() < 5
            cur += timedelta(days=1)
        return days


class RunPeriodMissingAttendanceTests(PayrollRunTestBase):
    def test_shift_worker_without_punches_is_unpaid_for_working_days(self):
        worker = self.make_employee("NOPUNCH")
        self.assign_shift(worker)

        run_period(self.period)

        slip = self.slip_for(worker)
        self.assertEqual(slip.unpaid_days, Decimal(self.working_days(self.period)))

    def test_employee_without_shift_is_not_marked_absent(self):
        office = self.make_employee("OFFICE")

        run_period(self.period)

        self.assertEqual(self.slip_for(office).unpaid_days, Decimal("0.00"))
        self.assertFalse(DailyAttendance.objects.filter(employee=office).exists())

    def test_existing_attendance_rows_are_not_overwritten(self):
        worker = self.make_employee("EDITED")
        self.assign_shift(worker)
        DailyAttendance.objects.create(
            employee=worker,
            date=date(2026, 7, 1),
            status=DailyAttendance.Status.PRESENT,
            notes="HR corrected",
        )

        run_period(self.period)

        row = DailyAttendance.objects.get(employee=worker, date=date(2026, 7, 1))
        self.assertEqual(row.status, DailyAttendance.Status.PRESENT)
        self.assertEqual(row.notes, "HR corrected")

    def test_future_days_are_not_marked_absent(self):
        from django.utils import timezone

        future = create_period(year=timezone.localdate().year + 1, month=1)
        worker = self.make_employee("FUTURE")
        self.assign_shift(worker)

        run_period(future)

        self.assertEqual(self.slip_for(worker, future).unpaid_days, Decimal("0.00"))


class LockPeriodSettlementTests(PayrollRunTestBase):
    """Claims/advances must be settled exactly once across periods."""

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(email="settle@example.com", password="x")
        self.worker = self.make_employee("SETTLE")
        self.august = create_period(year=2026, month=8)

    def approved_claim(self, amount="100.00"):
        from expenses.models import ExpenseClaim

        return ExpenseClaim.objects.create(
            employee=self.worker,
            title="Taxi",
            status=ExpenseClaim.Status.APPROVED,
            total_amount=Decimal(amount),
            requested_by=self.user,
        )

    def disbursed_advance(self, amount="500.00", installment="500.00"):
        from loans.models import SalaryAdvance

        return SalaryAdvance.objects.create(
            employee=self.worker,
            amount=Decimal(amount),
            installments=1,
            installment_amount=Decimal(installment),
            status=SalaryAdvance.Status.DISBURSED,
            requested_by=self.user,
        )

    def test_claim_paid_in_one_period_blocks_lock_of_other(self):
        from .run import lock_period

        claim = self.approved_claim()
        run_period(self.period)
        run_period(self.august)
        lock_period(self.period)

        with self.assertRaisesMessage(ValueError, "Re-run payroll"):
            lock_period(self.august)
        self.august.refresh_from_db()
        self.assertFalse(self.august.is_locked)
        claim.refresh_from_db()
        self.assertEqual(claim.status, claim.Status.PAID)

    def test_advance_recovered_in_one_period_blocks_lock_of_other(self):
        from .run import lock_period

        self.disbursed_advance()
        run_period(self.period)
        run_period(self.august)
        lock_period(self.period)

        with self.assertRaisesMessage(ValueError, "Re-run payroll"):
            lock_period(self.august)

    def test_rerun_after_settlement_drops_paid_items_and_locks(self):
        from .run import lock_period

        self.approved_claim()
        self.disbursed_advance()
        run_period(self.period)
        run_period(self.august)
        lock_period(self.period)

        run_period(self.august)
        lock_period(self.august)

        aug = self.slip_for(self.worker, self.august)
        jul = self.slip_for(self.worker, self.period)
        self.assertEqual(jul.net_pay - aug.net_pay, Decimal("100.00") - Decimal("500.00"))

    def test_many_claims_are_all_marked_paid(self):
        from expenses.models import ExpenseClaim

        from .run import lock_period

        claims = [self.approved_claim("1.00") for _ in range(150)]
        run_period(self.period)
        lock_period(self.period)

        paid = ExpenseClaim.objects.filter(
            pk__in=[c.pk for c in claims], status=ExpenseClaim.Status.PAID
        ).count()
        self.assertEqual(paid, 150)


class RunPeriodEmploymentDatesTests(PayrollRunTestBase):
    """Pay only for days inside the employee's joining → exit window."""

    def test_mid_month_leaver_is_paid_until_exit_date(self):
        leaver = self.make_employee(
            "LEAVER", status=Employee.Status.TERMINATED, date_of_exit=date(2026, 7, 15)
        )

        run_period(self.period)

        slip = self.slip_for(leaver)
        self.assertEqual(slip.unpaid_days, Decimal((self.period.end_date - date(2026, 7, 15)).days))

    def test_leaver_who_exited_before_period_gets_no_payslip(self):
        gone = self.make_employee(
            "GONE", status=Employee.Status.TERMINATED, date_of_exit=date(2026, 5, 31)
        )

        run_period(self.period)

        self.assertFalse(self.period.payslips.filter(employee=gone).exists())

    def test_mid_month_joiner_is_unpaid_before_joining_date(self):
        joiner = self.make_employee("JOINER", date_of_joining=date(2026, 7, 10))

        run_period(self.period)

        slip = self.slip_for(joiner)
        self.assertEqual(slip.unpaid_days, Decimal((date(2026, 7, 10) - self.period.start_date).days))

    def test_leaver_shift_days_after_exit_are_not_generated(self):
        from attendance.models import DailyAttendance

        leaver = self.make_employee(
            "LVSHIFT", status=Employee.Status.TERMINATED, date_of_exit=date(2026, 7, 15)
        )
        self.assign_shift(leaver)

        run_period(self.period)

        self.assertFalse(
            DailyAttendance.objects.filter(employee=leaver, date__gt=date(2026, 7, 15)).exists()
        )
        self.assertTrue(
            DailyAttendance.objects.filter(employee=leaver, date__lte=date(2026, 7, 15)).exists()
        )
