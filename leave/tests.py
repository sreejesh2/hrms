from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from attendance.models import DailyAttendance
from people.models import Employee

from .models import LeaveBalance, LeaveRequest, LeaveType
from .services import approve_leave, cancel_leave, reject_leave, submit_leave


class LeaveTestBase(TestCase):
    def setUp(self):
        from accounts.models import Role
        from accounts.rbac import seed_rbac

        seed_rbac()
        User = get_user_model()
        self.hr = User.objects.create_user(email="hr-leave@example.com", password="x")
        self.hr.roles.set([Role.objects.get(name="HR")])
        self.worker_user = User.objects.create_user(email="worker@example.com", password="x")
        self.worker_user.roles.set([Role.objects.get(name="Employee")])
        self.employee = Employee.objects.create(
            employee_code="LV-1",
            first_name="Leave",
            last_name="Worker",
            status=Employee.Status.ACTIVE,
            user=self.worker_user,
        )
        self.annual = LeaveType.objects.create(
            code="AL-T", name="Annual test", default_entitlement=Decimal("30.0")
        )

    def submit(self, start, end, **kw):
        return submit_leave(
            employee=self.employee,
            leave_type=self.annual,
            start_date=start,
            end_date=end,
            reason="test",
            requested_by=self.worker_user,
            **kw,
        )

    def balance(self, year):
        return LeaveBalance.objects.get(employee=self.employee, leave_type=self.annual, year=year)


class CrossYearLeaveTests(LeaveTestBase):
    """Dec 28 → Jan 5 takes 4 days from the old year and 5 from the new year."""

    def test_pending_days_are_split_by_year(self):
        self.submit(date(2026, 12, 28), date(2027, 1, 5))

        self.assertEqual(self.balance(2026).pending, Decimal("4.0"))
        self.assertEqual(self.balance(2027).pending, Decimal("5.0"))

    def test_approval_moves_each_year_to_used(self):
        req = self.submit(date(2026, 12, 28), date(2027, 1, 5))

        approve_leave(req, reviewer=self.hr)

        self.assertEqual((self.balance(2026).used, self.balance(2026).pending), (Decimal("4.0"), 0))
        self.assertEqual((self.balance(2027).used, self.balance(2027).pending), (Decimal("5.0"), 0))

    def test_reject_and_cancel_release_both_years(self):
        rejected = self.submit(date(2026, 12, 28), date(2027, 1, 5))
        reject_leave(rejected, reviewer=self.hr)
        cancelled = self.submit(date(2026, 12, 30), date(2027, 1, 2))
        cancel_leave(cancelled, user=self.worker_user)

        self.assertEqual(self.balance(2026).pending, Decimal("0.0"))
        self.assertEqual(self.balance(2027).pending, Decimal("0.0"))

    def test_insufficient_balance_in_new_year_is_rejected(self):
        LeaveBalance.objects.create(
            employee=self.employee, leave_type=self.annual, year=2027, entitled=Decimal("2.0")
        )

        with self.assertRaisesMessage(ValueError, "2027"):
            self.submit(date(2026, 12, 28), date(2027, 1, 5))


class NoManagerLeaveTests(LeaveTestBase):
    def test_request_without_manager_notifies_hr(self):
        from notifications.models import Notification

        self.submit(date(2026, 7, 1), date(2026, 7, 2))

        self.assertTrue(
            Notification.objects.filter(recipient=self.hr, title="Leave request pending").exists()
        )

    def test_request_with_manager_notifies_only_manager(self):
        from notifications.models import Notification

        boss_user = get_user_model().objects.create_user(email="boss@example.com", password="x")
        boss = Employee.objects.create(employee_code="BOSS", first_name="B", user=boss_user)
        self.employee.manager = boss
        self.employee.save()

        self.submit(date(2026, 7, 1), date(2026, 7, 2))

        self.assertTrue(Notification.objects.filter(recipient=boss_user).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.hr).exists())


class CancelApprovedLeaveTests(LeaveTestBase):
    def setUp(self):
        super().setUp()
        self.past_day = timezone.localdate() - timedelta(days=3)
        self.req = self.submit(self.past_day, self.past_day)
        approve_leave(self.req, reviewer=self.hr)

    def test_hr_cancel_returns_days_and_releases_attendance(self):
        from .services import cancel_approved_leave

        cancel_approved_leave(self.req, user=self.hr)

        self.req.refresh_from_db()
        self.assertEqual(self.req.status, LeaveRequest.Status.CANCELLED)
        self.assertEqual(self.balance(self.past_day.year).used, Decimal("0.0"))
        row = DailyAttendance.objects.get(employee=self.employee, date=self.past_day)
        self.assertNotEqual(row.status, DailyAttendance.Status.ON_LEAVE)
        self.assertFalse(row.is_locked)

    def test_cancel_blocked_when_payroll_period_is_locked(self):
        from payroll.models import PayrollPeriod
        from payroll.run import create_period

        from .services import cancel_approved_leave

        period = create_period(year=self.past_day.year, month=self.past_day.month)
        if not (period.start_date <= self.past_day <= period.end_date):
            self.skipTest("company cycle puts this day in another period")
        PayrollPeriod.objects.filter(pk=period.pk).update(status=PayrollPeriod.Status.LOCKED)

        with self.assertRaisesMessage(ValueError, "locked"):
            cancel_approved_leave(self.req, user=self.hr)

    def test_hr_can_cancel_approved_leave_from_detail_page(self):
        self.client.force_login(self.hr)

        self.client.post(f"/leave/{self.req.pk}/", {"action": "cancel_approved"})

        self.req.refresh_from_db()
        self.assertEqual(self.req.status, LeaveRequest.Status.CANCELLED)

    def test_employee_cannot_cancel_approved_leave(self):
        self.client.force_login(self.worker_user)

        self.client.post(f"/leave/{self.req.pk}/", {"action": "cancel_approved"})

        self.req.refresh_from_db()
        self.assertEqual(self.req.status, LeaveRequest.Status.APPROVED)


class SkipOffDaysLeaveTests(LeaveTestBase):
    """Leave types can skip weekly off days and holidays (Thu–Sat with Friday off = 2 days)."""

    THU, FRI, SAT = date(2026, 7, 2), date(2026, 7, 3), date(2026, 7, 4)

    def setUp(self):
        super().setUp()
        from attendance.models import ShiftAssignment, WorkCalendar, WorkShift

        self.calendar = WorkCalendar.objects.create(
            code="FRI-OFF", name="Friday off", saturday=True, sunday=True, friday=False
        )
        shift = WorkShift.objects.create(code="LV-DAY", name="Day")
        ShiftAssignment.objects.create(
            employee=self.employee, shift=shift, calendar=self.calendar,
            effective_from=date(2026, 1, 1),
        )
        self.sick = LeaveType.objects.create(
            code="SL-T", name="Sick test", default_entitlement=Decimal("10.0"),
            exclude_off_days=True,
        )

    def submit_type(self, leave_type, start, end):
        return submit_leave(
            employee=self.employee, leave_type=leave_type, start_date=start, end_date=end,
            reason="test", requested_by=self.worker_user,
        )

    def test_skip_type_does_not_count_weekly_off(self):
        req = self.submit_type(self.sick, self.THU, self.SAT)

        self.assertEqual(req.days, Decimal("2"))
        self.assertEqual(
            LeaveBalance.objects.get(employee=self.employee, leave_type=self.sick, year=2026).pending,
            Decimal("2.0"),
        )

    def test_normal_type_still_counts_every_day(self):
        req = self.submit_type(self.annual, self.THU, self.SAT)

        self.assertEqual(req.days, Decimal("3"))

    def test_skip_type_does_not_count_holiday(self):
        from attendance.models import Holiday

        Holiday.objects.create(date=self.THU, name="Public holiday")

        req = self.submit_type(self.sick, self.THU, self.SAT)

        self.assertEqual(req.days, Decimal("1"))

    def test_only_off_days_selected_is_refused(self):
        with self.assertRaisesMessage(ValueError, "off days"):
            self.submit_type(self.sick, self.FRI, self.FRI)

    def test_approval_keeps_off_day_as_weekly_off(self):
        approve_leave(self.submit_type(self.sick, self.THU, self.SAT), reviewer=self.hr)

        status = dict(
            DailyAttendance.objects.filter(employee=self.employee).values_list("date", "status")
        )
        self.assertEqual(status[self.THU], DailyAttendance.Status.ON_LEAVE)
        self.assertEqual(status[self.SAT], DailyAttendance.Status.ON_LEAVE)
        self.assertNotEqual(status.get(self.FRI), DailyAttendance.Status.ON_LEAVE)

    def test_regenerating_off_day_does_not_turn_it_into_leave(self):
        from attendance.engine import generate_daily_attendance

        approve_leave(self.submit_type(self.sick, self.THU, self.SAT), reviewer=self.hr)

        row = generate_daily_attendance(self.employee, self.FRI, force=True)

        self.assertEqual(row.status, DailyAttendance.Status.WEEKLY_OFF)

    def test_balance_stays_consistent_if_calendar_changes_before_approval(self):
        req = self.submit_type(self.sick, self.THU, self.SAT)
        self.calendar.friday = True  # Friday becomes a working day after submitting
        self.calendar.save()

        approve_leave(req, reviewer=self.hr)

        bal = LeaveBalance.objects.get(employee=self.employee, leave_type=self.sick, year=2026)
        self.assertEqual((bal.used, bal.pending), (Decimal("2.0"), Decimal("0.0")))

    def test_unpaid_skip_type_off_day_is_not_deducted_in_payroll(self):
        from payroll.run import _unpaid_days

        unpaid = LeaveType.objects.create(
            code="LWP-T", name="Unpaid test", is_paid=False, exclude_off_days=True,
            default_entitlement=Decimal("30.0"),
        )
        approve_leave(self.submit_type(unpaid, self.THU, self.SAT), reviewer=self.hr)

        self.assertEqual(_unpaid_days(self.employee, self.THU, self.SAT), Decimal("2.00"))


class CheckBalanceSettingTests(LeaveTestBase):
    """Unpaid leave (LWP) can be applied for without a balance; days are still recorded."""

    def setUp(self):
        super().setUp()
        self.lwp = LeaveType.objects.create(
            code="LWP-B", name="Without pay", is_paid=False,
            default_entitlement=Decimal("0.0"), check_balance=False,
        )

    def test_type_without_balance_check_can_be_applied_with_zero_balance(self):
        req = submit_leave(
            employee=self.employee, leave_type=self.lwp, start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 5), reason="family", requested_by=self.worker_user,
        )

        self.assertEqual(req.days, Decimal("5"))

    def test_days_are_still_recorded_on_the_balance(self):
        req = submit_leave(
            employee=self.employee, leave_type=self.lwp, start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 5), reason="family", requested_by=self.worker_user,
        )
        approve_leave(req, reviewer=self.hr)

        bal = LeaveBalance.objects.get(employee=self.employee, leave_type=self.lwp, year=2026)
        self.assertEqual(bal.used, Decimal("5.0"))

    def test_type_with_balance_check_is_still_limited(self):
        capped = LeaveType.objects.create(
            code="CAP", name="Capped", default_entitlement=Decimal("2.0"), check_balance=True
        )

        with self.assertRaisesMessage(ValueError, "Insufficient balance"):
            submit_leave(
                employee=self.employee, leave_type=capped, start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 5), reason="x", requested_by=self.worker_user,
            )

    def test_seeded_lwp_does_not_check_balance(self):
        from .services import seed_default_leave_types

        LeaveType.objects.filter(code="LWP").delete()
        seed_default_leave_types()

        self.assertFalse(LeaveType.objects.get(code="LWP").check_balance)
        self.assertTrue(LeaveType.objects.get(code="CL").check_balance)
