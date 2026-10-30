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


class NoManagerRegularizationTests(TestCase):
    def test_correction_without_manager_notifies_attendance_managers(self):
        from django.contrib.auth import get_user_model

        from accounts.models import Role
        from accounts.rbac import seed_rbac
        from notifications.models import Notification
        from people.models import Employee

        from .models import DailyAttendance
        from .regularization import submit_regularization

        seed_rbac()
        User = get_user_model()
        hr = User.objects.create_user(email="hr-reg@example.com", password="x")
        hr.roles.set([Role.objects.get(name="HR")])
        worker = User.objects.create_user(email="reg-worker@example.com", password="x")
        employee = Employee.objects.create(employee_code="REG-1", first_name="R", user=worker)

        submit_regularization(
            employee=employee,
            on_date=date(2026, 7, 1),
            requested_status=DailyAttendance.Status.PRESENT,
            reason="forgot to punch",
            requested_by=worker,
        )

        self.assertTrue(
            Notification.objects.filter(
                recipient=hr, title="Attendance correction requested"
            ).exists()
        )


class ZKTecoOfflinePunchTests(TestCase):
    """Punches made while the server was off arrive later and still count."""

    def setUp(self):
        from people.models import Employee

        from .models import PunchDevice

        self.employee = Employee.objects.create(
            employee_code="OFF-1", first_name="Off", last_name="Line",
            biometric_id="555", status=Employee.Status.ACTIVE,
        )
        self.device = PunchDevice.objects.create(
            code="GATE", name="Gate", serial_number="GATE0001", api_token="t-gate", is_active=True,
        )
        self.day = date(2026, 7, 1)  # Wednesday: a working day

    def test_old_punches_uploaded_after_outage_make_the_day_present(self):
        from .models import DailyAttendance, PunchLog
        from .zkteco import ingest_attlog

        # While the server was down, payroll/attendance had marked the day absent
        DailyAttendance.objects.create(
            employee=self.employee, date=self.day, status=DailyAttendance.Status.ABSENT
        )

        # Server is back: the device uploads its stored punches
        result = ingest_attlog(
            self.device, "555\t2026-07-01 08:00:00\t0\t1\n555\t2026-07-01 17:00:00\t1\t1\n"
        )

        self.assertEqual(result["created"], 2)
        self.assertEqual(PunchLog.objects.filter(employee=self.employee).count(), 2)
        row = DailyAttendance.objects.get(employee=self.employee, date=self.day)
        self.assertEqual(row.status, DailyAttendance.Status.PRESENT)
        self.assertGreater(row.worked_hours, 0)

    def test_device_is_told_to_send_everything_after_the_last_upload(self):
        from .zkteco import ingest_attlog, push_options_response

        ingest_attlog(self.device, "555\t2026-07-01 08:00:00\t0\t1\n")
        self.device.refresh_from_db()
        last_upload = self.device.attlog_stamp

        # Next handshake (e.g. after a reboot) asks for records after the last upload only
        self.assertIn(f"ATTLOGStamp={last_upload}", push_options_response(self.device))

    def test_server_down_then_full_resend_creates_no_duplicates(self):
        from .models import PunchLog
        from .zkteco import ingest_attlog

        body = "555\t2026-07-01 08:00:00\t0\t1\n555\t2026-07-01 17:00:00\t1\t1\n"
        ingest_attlog(self.device, body)
        ingest_attlog(self.device, body)  # device unsure what arrived: sends all again

        self.assertEqual(PunchLog.objects.filter(employee=self.employee).count(), 2)


class ZKTecoResendPunchesTests(TestCase):
    """Machine approved before employees existed: punches skipped, then re-sent."""

    BODY = "104\t2026-10-28 07:58:00\t0\t15\n104\t2026-10-28 17:02:00\t1\t15\n"

    def setUp(self):
        from .models import PunchDevice

        self.device = PunchDevice.objects.create(
            code="ZK1", name="Gate", vendor=PunchDevice.Vendor.ZKTECO,
            serial_number="SN0001", api_token="t-sn1", is_active=True,
        )

    def test_skipped_punches_arrive_after_import_and_resend(self):
        from people.models import Employee

        from .models import DeviceCommand, PunchLog
        from .zkteco import ingest_attlog, pending_commands_payload, queue_resend_punches

        result = ingest_attlog(self.device, self.BODY)
        self.assertEqual(result["unknown"], 2)
        self.device.refresh_from_db()
        self.assertNotEqual(self.device.attlog_stamp, "0")

        emp = Employee.objects.create(
            employee_code="A1P104", first_name="Ryan", biometric_id="104",
            status=Employee.Status.ACTIVE,
        )
        queue_resend_punches(self.device)

        self.device.refresh_from_db()
        self.assertEqual(self.device.attlog_stamp, "0")
        payload = pending_commands_payload(self.device)
        self.assertIn("DATA QUERY ATTLOG StartTime=2000-01-01 00:00:00\tEndTime=", payload)
        self.assertIn(":CHECK", payload)
        sent = DeviceCommand.objects.filter(status=DeviceCommand.Status.SENT)
        self.assertTrue(sent.filter(command__startswith="DATA QUERY ATTLOG").exists())
        self.assertTrue(sent.filter(command="CHECK").exists())

        # Machine answers with everything it has; sending twice adds nothing more
        ingest_attlog(self.device, self.BODY)
        ingest_attlog(self.device, self.BODY)
        self.assertEqual(PunchLog.objects.filter(employee=emp).count(), 2)


class DeviceResendViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        from accounts.models import Role
        from accounts.rbac import seed_rbac

        from .models import PunchDevice

        seed_rbac()
        user = get_user_model().objects.create_user(email="admin@example.com", password="x")
        user.roles.set([Role.objects.get(name="Admin")])
        self.client.force_login(user)
        self.device = PunchDevice.objects.create(
            code="ZK1", name="Gate", vendor=PunchDevice.Vendor.ZKTECO,
            serial_number="SN0001", api_token="t-sn1", is_active=True,
        )

    def url(self):
        from django.urls import reverse

        return reverse("attendance:device_resend_punches", args=[self.device.pk])

    def test_button_shown_and_queues_commands(self):
        from django.urls import reverse

        from .models import DeviceCommand

        detail = reverse("attendance:device_detail", args=[self.device.pk])
        self.assertContains(self.client.get(detail), "Re-send all punches")

        resp = self.client.post(self.url())

        self.assertRedirects(resp, detail)
        commands = set(DeviceCommand.objects.values_list("command", flat=True))
        self.assertIn("CHECK", commands)
        self.assertTrue(any(c.startswith("DATA QUERY ATTLOG") for c in commands))

    def test_refused_for_unapproved_device(self):
        from .models import DeviceCommand

        self.device.is_active = False
        self.device.save()

        self.client.post(self.url())

        self.assertFalse(DeviceCommand.objects.exists())


class ZKTecoNewerFirmwareTests(TestCase):
    """Push firmware that answers DATA QUERY on /iclock/querydata."""

    def setUp(self):
        from people.models import Employee

        from .models import PunchDevice

        self.emp = Employee.objects.create(
            employee_code="A1P104", first_name="Ryan", biometric_id="104",
            status=Employee.Status.ACTIVE,
        )
        self.device = PunchDevice.objects.create(
            code="ZK1", name="Gate", vendor=PunchDevice.Vendor.ZKTECO,
            serial_number="BRM9201160576", api_token="t-brm", is_active=True,
        )

    def test_querydata_reply_saves_punches(self):
        from .models import PunchLog

        resp = self.client.post(
            "/iclock/querydata?SN=BRM9201160576&type=tabledata&cmdid=7"
            "&tablename=ATTLOG&count=2&packcnt=1&packidx=1",
            data="104\t2026-10-28 07:58:00\t0\t15\n104\t2026-10-28 17:02:00\t1\t15\n",
            content_type="text/plain",
        )

        self.assertEqual(resp.content, b"ATTLOG=2")
        self.assertEqual(PunchLog.objects.filter(employee=self.emp).count(), 2)

    def test_key_value_lines_and_zero_padded_pin(self):
        from .models import PunchLog
        from .zkteco import ingest_attlog

        result = ingest_attlog(
            self.device,
            "log pin=0104\ttime=2026-10-28 07:58:00\tstatus=0\tverify=15\n"
            "pin=104\ttime=2026-10-28 17:02:00\tstatus=1\n",
        )

        self.assertEqual(result["created"], 2)
        self.assertEqual(PunchLog.objects.filter(employee=self.emp).count(), 2)

    def test_unknown_iclock_path_answers_ok(self):
        resp = self.client.post("/iclock/push?SN=BRM9201160576", data="x", content_type="text/plain")

        self.assertEqual(resp.status_code, 200)

    def test_no_more_set_time_after_device_rejects_it(self):
        from .models import DeviceCommand
        from .zkteco import maybe_auto_time_sync

        DeviceCommand.objects.create(
            device=self.device, command="SET TIME 2026-10-30 12:23:40",
            status=DeviceCommand.Status.FAILED, result="-1002",
        )

        self.assertIsNone(maybe_auto_time_sync(self.device, reconnected=True))


class ZKTecoTableDataUploadTests(TestCase):
    """Push 3.x: punches arrive as table=tabledata&tablename=… on /iclock/cdata."""

    def setUp(self):
        from people.models import Employee

        from .models import PunchDevice

        self.emp = Employee.objects.create(
            employee_code="A1P104", first_name="Ryan", biometric_id="104",
            status=Employee.Status.ACTIVE,
        )
        PunchDevice.objects.create(
            code="ZK1", name="Gate", vendor=PunchDevice.Vendor.ZKTECO,
            serial_number="BRM9201160576", api_token="t-brm", is_active=True,
        )

    def post(self, query, body):
        return self.client.post(
            f"/iclock/cdata?SN=BRM9201160576&{query}", data=body, content_type="text/plain"
        )

    def count(self):
        from .models import PunchLog

        return PunchLog.objects.filter(employee=self.emp).count()

    def test_tabledata_attlog_classic_lines(self):
        self.post("table=tabledata&tablename=ATTLOG&count=1", "104\t2026-10-28 07:58:00\t0\t15\t0\t0\n")
        self.assertEqual(self.count(), 1)

    def test_rtlog_key_value(self):
        self.post(
            "table=rtlog",
            "time=2026-10-30 13:40:00\tpin=104\tcardno=0\teventaddr=1\tevent=0\tinoutstatus=0\tverifytype=15\n",
        )
        self.assertEqual(self.count(), 1)

    def test_transaction_with_packed_time(self):
        from .zkteco import decode_zk_time

        packed = ((26 * 12 + 9) * 31 + 29) * 86400 + 13 * 3600 + 40 * 60  # 2026-10-30 13:40
        self.assertEqual(decode_zk_time(str(packed)), "2026-10-30 13:40:00")
        self.post(
            "table=tabledata&tablename=transaction&count=1",
            f"transaction cardno=0\tpin=104\tverified=15\tdoorid=1\teventtype=0\tinoutstate=0\ttime_second={packed}\n",
        )
        self.assertEqual(self.count(), 1)

    def test_tabledata_without_tablename_is_detected(self):
        self.post("table=tabledata", "pin=104\ttime=2026-10-28 07:58:00\tstatus=0\n")
        self.assertEqual(self.count(), 1)

    def test_operlog_user_lines_are_not_punches(self):
        from .zkteco import looks_like_punches

        self.assertFalse(looks_like_punches("USER PIN=104\tName=Ryan\tPri=0\n"))
