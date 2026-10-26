from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from .engine import (
    apply_configured_break_fallback,
    calculate_break_overrun_minutes,
    calculate_break_overrun_penalty_minutes,
    worked_hours_after,
)


class ConfiguredBreakFallbackTests(TestCase):
    def setUp(self):
        self.version = SimpleNamespace(break_hours=Decimal("0.50"))

    def test_uses_shift_break_for_plain_in_out(self):
        worked, break_hours = apply_configured_break_fallback(
            worked=Decimal("12.00"),
            break_hours=Decimal("0.00"),
            punches=[object(), object()],
            version=self.version,
            is_working_day=True,
        )

        self.assertEqual(worked, Decimal("11.50"))
        self.assertEqual(break_hours, Decimal("0.50"))

    def test_actual_multi_segment_break_takes_priority(self):
        worked, break_hours = apply_configured_break_fallback(
            worked=Decimal("11.00"),
            break_hours=Decimal("1.00"),
            punches=[object(), object(), object(), object()],
            version=self.version,
            is_working_day=True,
        )

        self.assertEqual(worked, Decimal("11.00"))
        self.assertEqual(break_hours, Decimal("1.00"))

    def test_weekly_off_does_not_apply_configured_break(self):
        worked, break_hours = apply_configured_break_fallback(
            worked=Decimal("8.00"),
            break_hours=Decimal("0.00"),
            punches=[object(), object()],
            version=self.version,
            is_working_day=False,
        )

        self.assertEqual(worked, Decimal("8.00"))
        self.assertEqual(break_hours, Decimal("0.00"))

    def test_calculates_break_overrun(self):
        minutes = calculate_break_overrun_minutes(
            Decimal("1.00"),
            self.version,
        )

        self.assertEqual(minutes, 30)

    def test_no_overrun_within_shift_allowance(self):
        minutes = calculate_break_overrun_minutes(
            Decimal("0.50"),
            self.version,
        )

        self.assertEqual(minutes, 0)

    def test_break_penalty_disabled_by_default(self):
        shift = SimpleNamespace(
            break_overrun_penalty_enabled=False,
            break_overrun_grace_minutes=0,
        )
        self.assertEqual(calculate_break_overrun_penalty_minutes(30, shift), 0)

    def test_break_penalty_applies_after_grace(self):
        shift = SimpleNamespace(
            break_overrun_penalty_enabled=True,
            break_overrun_grace_minutes=5,
        )
        self.assertEqual(calculate_break_overrun_penalty_minutes(30, shift), 25)

    def test_actual_ot_counts_only_work_after_shift_end(self):
        punches = [
            SimpleNamespace(punched_at=datetime(2026, 7, 27, 7, 0), punch_type="in"),
            SimpleNamespace(
                punched_at=datetime(2026, 7, 27, 13, 0),
                punch_type="break_out",
            ),
            SimpleNamespace(
                punched_at=datetime(2026, 7, 27, 14, 0),
                punch_type="break_in",
            ),
            SimpleNamespace(punched_at=datetime(2026, 7, 27, 19, 0), punch_type="out"),
        ]

        actual_ot = worked_hours_after(
            punches,
            datetime(2026, 7, 27, 15, 30),
        )

        self.assertEqual(actual_ot, Decimal("3.50"))


class OvertimePositionMappingTests(TestCase):
    def setUp(self):
        from people.models import Position

        from .models import OvertimePolicy
        from .ot import seed_default_ot_policy

        seed_default_ot_policy()
        self.position = Position.objects.create(
            code="OT-TEST",
            description="OT Test Position",
            is_active=True,
        )
        self.no_ot = OvertimePolicy.objects.get(code="NO-OT")
        self.std = OvertimePolicy.objects.get(code="STD")

    def test_disable_ot_returns_zero(self):
        from .ot import calculate_overtime

        ot, rate, note = calculate_overtime(
            worked=Decimal("10.00"),
            expected=Decimal("8.00"),
            policy=self.no_ot,
        )
        self.assertEqual(ot, Decimal("0.00"))
        self.assertEqual(rate, Decimal("0.00"))
        self.assertIn("no OT", note)

    def test_position_mapping_overrides_shift(self):
        from .ot import get_ot_policy_for_employee

        self.no_ot.positions.add(self.position)
        employee = SimpleNamespace(position=self.position)
        shift = SimpleNamespace(ot_policy_id=self.std.pk, ot_policy=self.std)
        policy = get_ot_policy_for_employee(employee, shift)
        self.assertEqual(policy.code, "NO-OT")

    def test_unmapped_position_uses_shift(self):
        from .ot import get_ot_policy_for_employee

        employee = SimpleNamespace(position=self.position)
        shift = SimpleNamespace(ot_policy_id=self.std.pk, ot_policy=self.std)
        policy = get_ot_policy_for_employee(employee, shift)
        self.assertEqual(policy.code, "STD")


class ApprovedLeaveAttendanceTests(TestCase):
    def setUp(self):
        from datetime import date

        from django.contrib.auth import get_user_model

        from leave.models import LeaveRequest, LeaveType
        from people.models import Employee

        self.day = date(2026, 7, 29)
        self.employee = Employee.objects.create(
            employee_code="LEAVE-TEST",
            first_name="Leave",
            last_name="Test",
            status=Employee.Status.ACTIVE,
        )
        user = get_user_model().objects.create_user(
            email="leave-test@example.com",
            password="test",
        )
        leave_type = LeaveType.objects.create(
            code="SL-TEST",
            name="Sick Leave Test",
            default_entitlement=Decimal("10.0"),
        )
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=leave_type,
            start_date=self.day,
            end_date=self.day,
            days=Decimal("1.0"),
            reason="Approved sick leave",
            status=LeaveRequest.Status.APPROVED,
            requested_by=user,
            reviewed_by=user,
            apply_to_attendance=True,
        )

    def test_force_generation_preserves_approved_leave(self):
        from .engine import generate_daily_attendance
        from .models import DailyAttendance

        row = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.day,
            status=DailyAttendance.Status.ABSENT,
            notes="Leave: SL-TEST",
            is_locked=False,
        )

        generated = generate_daily_attendance(
            self.employee,
            self.day,
            force=True,
        )

        row.refresh_from_db()
        self.assertEqual(generated.pk, row.pk)
        self.assertEqual(row.status, DailyAttendance.Status.ON_LEAVE)
        self.assertTrue(row.is_locked)
        self.assertEqual(row.notes, "Leave: SL-TEST")


class ShiftAssignmentServiceTests(TestCase):
    def setUp(self):
        from people.models import Employee

        from .models import WorkShift

        self.employee = Employee.objects.create(
            employee_code="SHIFT-SVC",
            first_name="Shift",
            last_name="Service",
            status=Employee.Status.ACTIVE,
        )
        self.day = WorkShift.objects.create(code="SVC-DAY", name="Service Day")
        self.night = WorkShift.objects.create(code="SVC-NIGHT", name="Service Night")

    def test_same_assignment_is_skipped_idempotently(self):
        from .services import assign_employee_shift

        first = assign_employee_shift(
            employee=self.employee,
            shift=self.day,
            effective_from=date(2026, 7, 30),
            refresh_attendance=False,
        )
        second = assign_employee_shift(
            employee=self.employee,
            shift=self.day,
            effective_from=date(2026, 7, 30),
            refresh_attendance=False,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertFalse(second._assignment_created)

    def test_overlap_is_rejected_when_replace_is_off(self):
        from django.core.exceptions import ValidationError

        from .services import assign_employee_shift

        assign_employee_shift(
            employee=self.employee,
            shift=self.day,
            effective_from=date(2026, 7, 1),
            refresh_attendance=False,
        )

        with self.assertRaises(ValidationError):
            assign_employee_shift(
                employee=self.employee,
                shift=self.night,
                effective_from=date(2026, 7, 15),
                replace_overlapping=False,
                refresh_attendance=False,
            )

    def test_temporary_assignment_restores_prior_shift(self):
        from .models import ShiftAssignment
        from .services import assign_employee_shift

        assign_employee_shift(
            employee=self.employee,
            shift=self.day,
            effective_from=date(2026, 6, 26),
            refresh_attendance=False,
        )
        assign_employee_shift(
            employee=self.employee,
            shift=self.night,
            effective_from=date(2026, 8, 2),
            effective_to=date(2026, 8, 10),
            refresh_attendance=False,
        )

        night = ShiftAssignment.objects.get(
            employee=self.employee,
            shift=self.night,
            effective_from=date(2026, 8, 2),
            is_active=True,
        )
        self.assertEqual(night.effective_to, date(2026, 8, 10))

        resumed = ShiftAssignment.objects.get(
            employee=self.employee,
            shift=self.day,
            effective_from=date(2026, 8, 11),
            is_active=True,
        )
        self.assertIsNone(resumed.effective_to)

        closed_day = ShiftAssignment.objects.get(
            employee=self.employee,
            shift=self.day,
            effective_from=date(2026, 6, 26),
        )
        self.assertEqual(closed_day.effective_to, date(2026, 8, 1))


class ZKTecoUnknownDeviceTests(TestCase):
    """Unknown serial numbers must not be able to push punches (payroll fraud)."""

    def setUp(self):
        from people.models import Employee

        self.employee = Employee.objects.create(
            employee_code="ZK-001",
            first_name="Zk",
            last_name="Worker",
            biometric_id="101",
            status=Employee.Status.ACTIVE,
        )

    def _push_attlog(self, sn):
        return self.client.post(
            f"/iclock/cdata?SN={sn}&table=ATTLOG",
            data="101\t2026-07-01 08:00:00\t0\t1\n",
            content_type="text/plain",
        )

    def test_unknown_device_is_registered_inactive(self):
        from .models import PunchDevice

        self._push_attlog("FAKE1234")

        device = PunchDevice.objects.get(serial_number="FAKE1234")
        self.assertFalse(device.is_active)

    def test_unknown_device_punches_are_not_saved(self):
        from .models import PunchLog

        self._push_attlog("FAKE1234")

        self.assertFalse(PunchLog.objects.filter(employee=self.employee).exists())

    def test_approved_device_punches_are_saved(self):
        from .models import PunchDevice, PunchLog

        self._push_attlog("REAL5678")
        PunchDevice.objects.filter(serial_number="REAL5678").update(is_active=True)
        self._push_attlog("REAL5678")

        self.assertEqual(PunchLog.objects.filter(employee=self.employee).count(), 1)

    def test_resent_punches_are_skipped_and_new_ones_saved(self):
        from .models import PunchDevice, PunchLog
        from .zkteco import ingest_attlog

        device = PunchDevice.objects.create(
            code="ZK1", name="ZK1", serial_number="DUP0001", api_token="t-dup", is_active=True
        )
        ingest_attlog(device, "101\t2026-07-01 08:00:00\t0\t1\n")
        # Devices re-send old rows together with new ones
        result = ingest_attlog(
            device, "101\t2026-07-01 08:00:00\t0\t1\n101\t2026-07-01 17:00:00\t1\t1\n"
        )

        self.assertEqual(result["skipped"], 1)
        self.assertEqual(PunchLog.objects.filter(employee=self.employee).count(), 2)
