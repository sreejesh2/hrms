from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


def hours_between(start, end, day_span=False) -> Decimal:
    """Return hours between two time values as Decimal(0.00)."""
    if not start or not end:
        return Decimal("0.00")
    base = datetime(2000, 1, 1, start.hour, start.minute, start.second)
    finish = datetime(2000, 1, 1, end.hour, end.minute, end.second)
    if day_span or finish <= base:
        finish += timedelta(days=1)
    seconds = (finish - base).total_seconds()
    return (Decimal(str(seconds)) / Decimal("3600")).quantize(Decimal("0.01"))


class WorkCalendar(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    monday = models.BooleanField(default=True)
    tuesday = models.BooleanField(default=True)
    wednesday = models.BooleanField(default=True)
    thursday = models.BooleanField(default=True)
    friday = models.BooleanField(default=True)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def working_days_label(self):
        days = []
        mapping = (
            ("Mon", self.monday),
            ("Tue", self.tuesday),
            ("Wed", self.wednesday),
            ("Thu", self.thursday),
            ("Fri", self.friday),
            ("Sat", self.saturday),
            ("Sun", self.sunday),
        )
        for label, on in mapping:
            if on:
                days.append(label)
        return ", ".join(days) if days else "None"


class WorkShift(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120, blank=True)
    ot_policy = models.ForeignKey(
        "OvertimePolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts",
        help_text="Leave blank to use the default OT policy",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)
        verbose_name = "work shift"
        verbose_name_plural = "work shifts"

    def __str__(self):
        return self.code if not self.name else f"{self.code} — {self.name}"

    def current_version(self):
        return self.versions.order_by("-effective_from", "-id").first()


class OvertimePolicy(models.Model):
    """Rules for calculating overtime hours from worked vs expected."""

    class RoundMode(models.TextChoices):
        NONE = "none", "No rounding"
        NEAREST = "nearest", "Nearest"
        UP = "up", "Round up"
        DOWN = "down", "Round down"

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Used when a shift has no OT policy assigned",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    grace_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minutes over expected before OT starts counting",
    )
    round_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Round OT to this many minutes (0 = exact)",
    )
    round_mode = models.CharField(
        max_length=16, choices=RoundMode.choices, default=RoundMode.NEAREST
    )
    max_hours_per_day = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cap OT hours per day (blank = no cap)",
    )

    weekday_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.50"),
        help_text="Pay multiplier for weekday OT (for payroll later)",
    )
    weekend_rate = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("2.00")
    )
    holiday_rate = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("2.00")
    )

    weekly_off_all_as_ot = models.BooleanField(
        default=True,
        help_text="On weekly off, count all worked hours as OT",
    )
    holiday_all_as_ot = models.BooleanField(
        default=True,
        help_text="On holiday, count all worked hours as OT",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)
        verbose_name_plural = "overtime policies"

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            OvertimePolicy.objects.exclude(pk=self.pk).filter(is_default=True).update(
                is_default=False
            )


class WorkShiftVersion(models.Model):
    shift = models.ForeignKey(
        WorkShift, on_delete=models.CASCADE, related_name="versions", db_index=True
    )
    effective_from = models.DateField(db_index=True)
    shift_from = models.TimeField()
    shift_to = models.TimeField()
    day_span = models.BooleanField(
        default=False, help_text="Shift crosses midnight"
    )
    work_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    break_from = models.TimeField(null=True, blank=True)
    break_to = models.TimeField(null=True, blank=True)
    break_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)

    calc_attendance_by_work_hrs = models.BooleanField(
        default=False, verbose_name="Calc attendance by work hours"
    )
    single_punch_at_shift_start = models.BooleanField(
        default=False, verbose_name="Single punch at shift start"
    )
    punch_shift_and_break_start = models.BooleanField(
        default=False, verbose_name="Punch shift & break start"
    )
    attendance_by_first_in_last_punch = models.BooleanField(
        default=False, verbose_name="Attendance by first in & last punch"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shift_versions_created",
    )

    class Meta:
        ordering = ("-effective_from", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["shift", "effective_from"],
                name="uniq_shift_effective_from",
            )
        ]
        indexes = [
            models.Index(fields=["shift", "-effective_from"]),
        ]

    def __str__(self):
        return f"{self.shift.code} @ {self.effective_from}"

    def clean(self):
        if self.break_from and self.break_to and not self.day_span:
            # break should usually sit inside shift; soft check only
            pass
        if self.break_from and not self.break_to:
            raise ValidationError({"break_to": "Provide break end time."})
        if self.break_to and not self.break_from:
            raise ValidationError({"break_from": "Provide break start time."})

    def recalculate_hours(self):
        self.work_hours = hours_between(self.shift_from, self.shift_to, self.day_span)
        if self.work_hours > Decimal("24.00"):
            self.work_hours = Decimal("24.00")
        if self.break_from and self.break_to:
            self.break_hours = hours_between(
                self.break_from, self.break_to, day_span=False
            )
            if self.break_hours > Decimal("24.00"):
                self.break_hours = Decimal("24.00")
        else:
            self.break_hours = Decimal("0.00")
        # Net expected work often excludes break when break is configured
        if self.break_hours and self.work_hours >= self.break_hours:
            # keep gross shift length in work_hours (InfoSoft-style); net used at attendance time
            pass

    def save(self, *args, **kwargs):
        self.recalculate_hours()
        super().save(*args, **kwargs)


class ShiftAssignment(models.Model):
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="shift_assignments",
        db_index=True,
    )
    shift = models.ForeignKey(
        WorkShift, on_delete=models.PROTECT, related_name="assignments", db_index=True
    )
    calendar = models.ForeignKey(
        WorkCalendar,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
    )
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-effective_from", "-id")
        indexes = [
            models.Index(fields=["employee", "-effective_from"]),
        ]

    def __str__(self):
        return f"{self.employee} → {self.shift} from {self.effective_from}"

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Must be on or after effective from."})
        overlap = ShiftAssignment.objects.filter(
            employee=self.employee, is_active=True
        ).exclude(pk=self.pk)
        for other in overlap:
            other_end = other.effective_to
            self_end = self.effective_to
            starts_before_other_ends = other_end is None or self.effective_from <= other_end
            other_starts_before_self_ends = self_end is None or other.effective_from <= self_end
            if starts_before_other_ends and other_starts_before_self_ends:
                raise ValidationError(
                    "This employee already has an overlapping shift assignment."
                )


class Holiday(models.Model):
    class HolidayType(models.TextChoices):
        NATIONAL = "national", "National"
        REGIONAL = "regional", "Regional"
        OPTIONAL = "optional", "Optional"
        COMPANY = "company", "Company"

    date = models.DateField(db_index=True)
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, blank=True)
    holiday_type = models.CharField(
        max_length=20, choices=HolidayType.choices, default=HolidayType.NATIONAL
    )
    location = models.ForeignKey(
        "people.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="holidays",
        help_text="Blank = applies to all locations",
    )
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["date", "name", "location"],
                name="uniq_holiday_date_name_location",
            )
        ]
        indexes = [models.Index(fields=["date", "is_active"])]

    def __str__(self):
        return f"{self.date} — {self.name}"


class PunchDevice(models.Model):
    """Physical biometric / punch machine or software terminal."""

    class DeviceType(models.TextChoices):
        BIOMETRIC = "biometric", "Biometric"
        CARD = "card", "Card reader"
        MOBILE = "mobile", "Mobile app"
        MANUAL = "manual", "Manual / HR desk"
        OTHER = "other", "Other"

    class Vendor(models.TextChoices):
        GENERIC = "generic", "Generic HTTP"
        ZKTECO = "zkteco", "ZKTeco (iFace / ADMS)"

    class ConnectionMode(models.TextChoices):
        LOCAL = "local", "Local LAN (ADMS)"
        GLOBAL = "global", "Global / cloud (ADMS)"
        HTTP_BRIDGE = "http_bridge", "HTTP JSON bridge"

    ONLINE_SECONDS = 180  # seen within 3 minutes ⇒ online

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    device_type = models.CharField(
        max_length=20, choices=DeviceType.choices, default=DeviceType.BIOMETRIC
    )
    vendor = models.CharField(
        max_length=20, choices=Vendor.choices, default=Vendor.GENERIC, db_index=True
    )
    connection_mode = models.CharField(
        max_length=20,
        choices=ConnectionMode.choices,
        default=ConnectionMode.HTTP_BRIDGE,
        db_index=True,
        help_text="Local = device points at Day Pay on LAN; Global = public URL; Bridge = middleware JSON API",
    )
    serial_number = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="ZKTeco SN from the device sticker / Comm settings (required for ADMS)",
    )
    lan_host = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional device LAN IP for reference (local mode)",
    )
    lan_port = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=4370,
        help_text="Optional device TCP port (default 4370 for ZK local SDK)",
    )
    location = models.ForeignKey(
        "people.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="punch_devices",
    )
    api_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Used by HTTP JSON bridge machines (not ADMS)",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_time_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time Day Pay queued or served a clock sync to this device",
    )
    firmware_info = models.CharField(max_length=255, blank=True)
    attlog_stamp = models.CharField(max_length=32, blank=True, default="0")
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=["vendor", "serial_number"]),
            models.Index(fields=["connection_mode", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["serial_number"],
                condition=~Q(serial_number=""),
                name="uniq_punchdevice_serial_number",
            )
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def is_online(self):
        stamp = self.last_heartbeat_at or self.last_seen_at
        if not stamp:
            return False
        from django.utils import timezone

        return (timezone.now() - stamp).total_seconds() <= self.ONLINE_SECONDS

    @property
    def connection_status(self):
        if not self.is_active:
            return "off"
        return "online" if self.is_online else "offline"

    @property
    def connection_status_label(self):
        return {
            "online": "Online",
            "offline": "Offline",
            "off": "Disabled",
        }.get(self.connection_status, self.connection_status)


class DeviceCommand(models.Model):
    """Queued remote command for ZKTeco ADMS (time sync, reboot, INFO, …)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent to device"
        ACKED = "acked", "Acknowledged"
        FAILED = "failed", "Failed"

    device = models.ForeignKey(
        PunchDevice, on_delete=models.CASCADE, related_name="commands", db_index=True
    )
    command = models.TextField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    result = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["device", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.device_id} · {self.command[:40]} ({self.status})"

    @property
    def adms_line(self):
        return f"C:{self.pk}:{self.command}"


class DeviceBioTemplate(models.Model):
    """Fingerprint / face template captured from a ZKTeco device (for re-push)."""

    class BioType(models.TextChoices):
        FINGER = "finger", "Fingerprint"
        FACE = "face", "Face"
        OTHER = "other", "Other"

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="bio_templates",
        db_index=True,
    )
    bio_type = models.CharField(
        max_length=16, choices=BioType.choices, default=BioType.OTHER, db_index=True
    )
    finger_index = models.PositiveSmallIntegerField(default=0)
    template_data = models.TextField(help_text="Base64 / vendor template payload")
    source_device = models.ForeignKey(
        PunchDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bio_templates",
    )
    pin = models.CharField(max_length=64, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("employee_id", "bio_type", "finger_index")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "bio_type", "finger_index"],
                name="uniq_employee_bio_template_slot",
            )
        ]

    def __str__(self):
        return f"{self.employee_id} · {self.bio_type} #{self.finger_index}"


class PunchLog(models.Model):
    """Raw punch — supports many punches per employee per day (in/break/out)."""

    class Source(models.TextChoices):
        DEVICE = "device", "Device"
        MANUAL = "manual", "Manual"
        IMPORT = "import", "File import"
        API = "api", "API"

    class PunchType(models.TextChoices):
        AUTO = "auto", "Auto"
        IN = "in", "In"
        OUT = "out", "Out"
        BREAK_OUT = "break_out", "Break out"
        BREAK_IN = "break_in", "Break in"

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="punches",
        db_index=True,
    )
    punched_at = models.DateTimeField(db_index=True)
    punch_type = models.CharField(
        max_length=20, choices=PunchType.choices, default=PunchType.AUTO
    )
    device = models.ForeignKey(
        PunchDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="punches",
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.DEVICE, db_index=True
    )
    external_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Vendor punch id — used for idempotent device sync",
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="punches_created",
    )

    class Meta:
        ordering = ("-punched_at", "-id")
        indexes = [
            models.Index(fields=["employee", "punched_at"]),
            models.Index(fields=["device", "punched_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["device", "external_id"],
                condition=~Q(external_id=""),
                name="uniq_device_external_punch",
            )
        ]

    def __str__(self):
        return f"{self.employee_id} @ {self.punched_at}"


class DailyAttendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        HALF_DAY = "half_day", "Half day"
        WEEKLY_OFF = "weekly_off", "Weekly off"
        HOLIDAY = "holiday", "Holiday"
        ON_LEAVE = "on_leave", "On leave"
        MISSING_PUNCH = "missing_punch", "Missing punch"

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="daily_attendance",
        db_index=True,
    )
    date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ABSENT, db_index=True
    )
    shift = models.ForeignKey(
        WorkShift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    calendar = models.ForeignKey(
        WorkCalendar, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    holiday = models.ForeignKey(
        Holiday, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    first_punch_at = models.DateTimeField(null=True, blank=True)
    last_punch_at = models.DateTimeField(null=True, blank=True)
    punch_count = models.PositiveSmallIntegerField(default=0)
    worked_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    break_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    expected_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ot_policy = models.ForeignKey(
        "OvertimePolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    ot_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Pay multiplier applied for this day's OT",
    )
    late_minutes = models.PositiveIntegerField(default=0)
    early_leave_minutes = models.PositiveIntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "employee_id")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="uniq_employee_attendance_date"
            )
        ]
        indexes = [
            models.Index(fields=["date", "status"]),
            models.Index(fields=["employee", "-date"]),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.date} {self.status}"


class AttendanceRegularization(models.Model):
    """Employee/HR request to correct a day's attendance (approve to apply)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="regularizations",
        db_index=True,
    )
    date = models.DateField(db_index=True)
    attendance = models.ForeignKey(
        DailyAttendance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regularizations",
    )
    current_status = models.CharField(
        max_length=20, choices=DailyAttendance.Status.choices, blank=True
    )
    requested_status = models.CharField(
        max_length=20, choices=DailyAttendance.Status.choices
    )
    requested_worked_hours = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    reason = models.TextField()
    reviewer_notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    lock_on_approve = models.BooleanField(
        default=True,
        help_text="After approval, freeze the day so Generate will not overwrite it",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="regularization_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regularization_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approval = models.ForeignKey(
        "workflows.ApprovalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["employee", "date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"],
                condition=models.Q(status="pending"),
                name="uniq_pending_regularization_employee_date",
            )
        ]

    def __str__(self):
        return f"{self.employee_id} {self.date} → {self.requested_status} ({self.status})"
