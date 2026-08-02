"""Shared attendance forms."""

import calendar as cal

from django import forms

from people.models import Department, Employee, Location

from core.form_widgets import date_widget, datetime_widget, select_attrs, time_widget

from .models import (
    DailyAttendance,
    Holiday,
    LatePenaltyPolicy,
    OvertimePolicy,
    PunchDevice,
    PunchLog,
    ShiftAssignment,
    WorkCalendar,
    WorkShift,
    WorkShiftVersion,
)


class WorkCalendarForm(forms.ModelForm):
    class Meta:
        model = WorkCalendar
        fields = (
            "code",
            "name",
            "description",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class WorkShiftForm(forms.ModelForm):
    class Meta:
        model = WorkShift
        fields = (
            "code",
            "name",
            "ot_policy",
            "late_penalty_policy",
            "break_overrun_penalty_enabled",
            "break_overrun_grace_minutes",
            "is_active",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. REGULAR"}),
            "name": forms.TextInput(attrs={"placeholder": "Office shift"}),
            "ot_policy": forms.Select(attrs=select_attrs()),
            "late_penalty_policy": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ot_policy"].queryset = OvertimePolicy.objects.filter(is_active=True)
        self.fields["ot_policy"].required = False
        self.fields["ot_policy"].empty_label = "— Default OT policy —"
        self.fields["late_penalty_policy"].queryset = LatePenaltyPolicy.objects.filter(
            is_active=True
        )
        self.fields["late_penalty_policy"].required = False
        self.fields["late_penalty_policy"].empty_label = "— None (no late deduction) —"
        self.fields["late_penalty_policy"].label = "Late penalty policy"
        self.fields["break_overrun_penalty_enabled"].label = "Deduct break overrun"
        self.fields["break_overrun_penalty_enabled"].help_text = (
            "If enabled, extra break beyond the shift allowance reduces payable hours"
        )
        self.fields["break_overrun_grace_minutes"].label = "Break overrun grace (minutes)"
        self.fields["break_overrun_grace_minutes"].help_text = (
            "Ignore this many minutes of break overrun before deducting payable hours"
        )


class OvertimePolicyForm(forms.ModelForm):
    class Meta:
        model = OvertimePolicy
        fields = (
            "code",
            "name",
            "description",
            "is_default",
            "is_active",
            "disable_ot",
            "positions",
            "ot_basis",
            "ot_base_hours",
            "grace_minutes",
            "round_minutes",
            "round_mode",
            "max_hours_per_day",
            "weekday_rate",
            "weekend_rate",
            "holiday_rate",
            "weekly_off_all_as_ot",
            "holiday_all_as_ot",
            "hourly_divisor",
            "special_ot_amount",
            "special_ot_on_weekday",
            "special_ot_on_weekend",
            "special_ot_on_holiday",
        )
        widgets = {
            "ot_basis": forms.Select(attrs=select_attrs()),
            "round_mode": forms.Select(attrs=select_attrs()),
            "description": forms.TextInput(
                attrs={"placeholder": "e.g. Standard company OT rules"}
            ),
            "positions": forms.CheckboxSelectMultiple(),
        }
        labels = {
            "disable_ot": "No overtime (OT hours stay 0)",
            "positions": "Mapped positions",
            "ot_basis": "When does OT start?",
            "ot_base_hours": "Fixed base hours (if using fixed hours)",
            "hourly_divisor": "Hourly divisor (Basic ÷ N)",
            "special_ot_amount": "Special OT amount / hour",
            "special_ot_on_weekday": "Special OT on weekdays",
            "special_ot_on_weekend": "Special OT on weekly off",
            "special_ot_on_holiday": "Special OT on holidays",
        }
        help_texts = {
            "disable_ot": "Use for office / salaried roles that should never earn OT",
            "positions": (
                "Optional. Employees in these positions use this policy "
                "(overrides shift OT). Each position can map to only one policy."
            ),
            "ot_basis": "A = after shift ends · B = after fixed hours (e.g. 8)",
            "ot_base_hours": "Only used when basis is “After fixed hours”",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from people.models import Position

        self.fields["positions"].queryset = Position.objects.filter(
            is_active=True
        ).order_by("code")
        self.fields["positions"].required = False

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            self._sync_exclusive_positions(instance)
        else:
            old_save_m2m = self.save_m2m

            def save_m2m():
                old_save_m2m()
                self._sync_exclusive_positions(instance)

            self.save_m2m = save_m2m
        return instance

    def _sync_exclusive_positions(self, instance):
        """A position may belong to only one OT policy."""
        pos_ids = list(instance.positions.values_list("pk", flat=True))
        if not pos_ids:
            return
        for other in (
            OvertimePolicy.objects.exclude(pk=instance.pk)
            .filter(positions__in=pos_ids)
            .distinct()
        ):
            overlap = other.positions.filter(pk__in=pos_ids)
            other.positions.remove(*overlap)


class LatePenaltyPolicyForm(forms.ModelForm):
    class Meta:
        model = LatePenaltyPolicy
        fields = (
            "code",
            "name",
            "description",
            "is_default",
            "is_active",
        )
        widgets = {
            "description": forms.TextInput(
                attrs={"placeholder": "e.g. ≤5 min → 15 min; else 4 hours"}
            ),
        }


class LatePenaltyTierForm(forms.Form):
    """Simple multi-row tier editor (max 6 tiers)."""

    MAX_TIERS = 6

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        tiers = []
        if instance is not None:
            tiers = list(instance.tiers.order_by("max_late_minutes", "id"))
        for i in range(self.MAX_TIERS):
            max_late = tiers[i].max_late_minutes if i < len(tiers) else ""
            deduct = tiers[i].deduct_minutes if i < len(tiers) else ""
            self.fields[f"max_late_{i}"] = forms.IntegerField(
                required=False,
                min_value=0,
                label=f"Tier {i + 1}: late ≤ (minutes)",
                initial=max_late,
            )
            self.fields[f"deduct_{i}"] = forms.IntegerField(
                required=False,
                min_value=0,
                label=f"Tier {i + 1}: deduct (minutes)",
                initial=deduct,
            )

    def clean(self):
        cleaned = super().clean()
        rows = []
        for i in range(self.MAX_TIERS):
            max_late = cleaned.get(f"max_late_{i}")
            deduct = cleaned.get(f"deduct_{i}")
            if max_late is None and deduct is None:
                continue
            if max_late is None or deduct is None:
                raise forms.ValidationError(
                    f"Tier {i + 1}: both late ≤ and deduct minutes are required."
                )
            rows.append((int(max_late), int(deduct)))
        if not rows:
            raise forms.ValidationError("Add at least one late-penalty tier.")
        rows.sort(key=lambda r: r[0])
        cleaned["tier_rows"] = rows
        return cleaned

    def save(self, policy: LatePenaltyPolicy):
        from .models import LatePenaltyTier

        LatePenaltyTier.objects.filter(policy=policy).delete()
        LatePenaltyTier.objects.bulk_create(
            [
                LatePenaltyTier(
                    policy=policy,
                    max_late_minutes=max_late,
                    deduct_minutes=deduct,
                    sort_order=idx + 1,
                )
                for idx, (max_late, deduct) in enumerate(self.cleaned_data["tier_rows"])
            ]
        )
        return policy


class WorkShiftVersionForm(forms.ModelForm):
    class Meta:
        model = WorkShiftVersion
        fields = (
            "effective_from",
            "shift_from",
            "shift_to",
            "day_span",
            "break_from",
            "break_to",
            "notes",
            "calc_attendance_by_work_hrs",
            "single_punch_at_shift_start",
            "punch_shift_and_break_start",
            "attendance_by_first_in_last_punch",
        )
        widgets = {
            "effective_from": date_widget(),
            "shift_from": time_widget(),
            "shift_to": time_widget(),
            "break_from": time_widget(),
            "break_to": time_widget(),
            "notes": forms.TextInput(attrs={"placeholder": "e.g. OFFICE SHIFT"}),
        }
        labels = {
            "calc_attendance_by_work_hrs": "Calc by work hours",
            "single_punch_at_shift_start": "Single punch at start",
            "punch_shift_and_break_start": "Punch shift & break",
            "attendance_by_first_in_last_punch": "First in / last out",
        }
        help_texts = {
            "calc_attendance_by_work_hrs": "Use expected shift hours when calculating attendance",
            "single_punch_at_shift_start": "One punch at shift start counts as present",
            "punch_shift_and_break_start": "Require punches at shift start and break start",
            "attendance_by_first_in_last_punch": "Hours from first punch in to last punch out",
        }

    def __init__(self, *args, **kwargs):
        self.shift = kwargs.pop("shift", None)
        super().__init__(*args, **kwargs)
        for name in ("break_from", "break_to", "notes"):
            self.fields[name].required = False
        for name in (
            "calc_attendance_by_work_hrs",
            "single_punch_at_shift_start",
            "punch_shift_and_break_start",
            "attendance_by_first_in_last_punch",
        ):
            self.fields[name].required = False

    def clean_effective_from(self):
        value = self.cleaned_data["effective_from"]
        shift = self.shift or getattr(self.instance, "shift", None)
        if shift and value:
            qs = WorkShiftVersion.objects.filter(shift=shift, effective_from=value)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "A version already exists for this effective date."
                )
        return value


class ShiftAssignmentForm(forms.ModelForm):
    class Meta:
        model = ShiftAssignment
        fields = (
            "employee",
            "shift",
            "calendar",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
        )
        widgets = {
            "effective_from": date_widget(),
            "effective_to": date_widget(),
            "notes": forms.TextInput(attrs={"placeholder": "Optional note"}),
            "employee": forms.Select(attrs=select_attrs(searchable=True)),
            "shift": forms.Select(attrs=select_attrs(searchable=True)),
            "calendar": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            status__in=[Employee.Status.ACTIVE, Employee.Status.DRAFT, Employee.Status.ON_LEAVE]
        ).order_by("employee_code")
        self.fields["shift"].queryset = WorkShift.objects.filter(is_active=True)
        self.fields["calendar"].queryset = WorkCalendar.objects.filter(is_active=True)
        self.fields["calendar"].required = False
        self.fields["effective_to"].required = False
        self.fields["notes"].required = False
        self.fields["calendar"].empty_label = "— No calendar —"


class BulkShiftAssignForm(forms.Form):
    shift = forms.ModelChoiceField(
        queryset=WorkShift.objects.none(),
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    calendar = forms.ModelChoiceField(
        queryset=WorkCalendar.objects.none(),
        required=False,
        empty_label="— No calendar —",
        widget=forms.Select(attrs=select_attrs()),
    )
    effective_from = forms.DateField(widget=date_widget())
    effective_to = forms.DateField(
        required=False,
        widget=date_widget(),
        label="Effective to",
        help_text="Optional. Leave blank for an ongoing assignment.",
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Production rotation"}),
    )
    replace_overlapping = forms.BooleanField(
        required=False,
        initial=True,
        label="Replace existing assignments",
        help_text="Close previous active shifts for selected employees",
    )
    employee_ids = forms.CharField(widget=forms.HiddenInput, required=False)
    assign_all_matching = forms.BooleanField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shift"].queryset = WorkShift.objects.filter(is_active=True).order_by(
            "code"
        )
        self.fields["calendar"].queryset = WorkCalendar.objects.filter(
            is_active=True
        ).order_by("code")

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("effective_from")
        end = cleaned.get("effective_to")
        if start and end and end < start:
            self.add_error("effective_to", "Must be on or after effective from.")
        return cleaned


class ShiftAssignmentImportForm(forms.Form):
    file = forms.FileField(
        label="CSV file",
        help_text="Columns: employee_code, shift_code, calendar_code (optional), effective_from, effective_to (optional), notes (optional)",
    )
    replace_overlapping = forms.BooleanField(
        required=False,
        initial=True,
        label="Replace existing assignments",
    )


class ApplyDepartmentDefaultsForm(forms.Form):
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        empty_label=None,
        help_text="Uses each department’s default shift/calendar",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    effective_from = forms.DateField(
        required=False,
        widget=date_widget(),
        help_text="Leave blank to use each employee’s join date",
    )
    only_without_assignment = forms.BooleanField(
        required=False,
        initial=True,
        label="Only employees with no active shift",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = (
            Department.objects.filter(is_active=True, default_shift__isnull=False)
            .select_related("default_shift", "default_calendar")
            .order_by("code")
        )


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = (
            "date",
            "name",
            "code",
            "holiday_type",
            "location",
            "is_paid",
            "is_active",
            "notes",
        )
        widgets = {
            "date": date_widget(),
            "notes": forms.TextInput(attrs={"placeholder": "Optional note"}),
            "holiday_type": forms.Select(attrs=select_attrs()),
            "location": forms.Select(attrs=select_attrs(searchable=True)),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.filter(is_active=True)
        self.fields["location"].required = False
        self.fields["location"].empty_label = "— All locations —"
        self.fields["code"].required = False
        self.fields["notes"].required = False


class PunchDeviceForm(forms.ModelForm):
    class Meta:
        model = PunchDevice
        fields = (
            "code",
            "name",
            "vendor",
            "connection_mode",
            "serial_number",
            "lan_host",
            "lan_port",
            "device_type",
            "location",
            "is_active",
            "notes",
        )
        widgets = {
            "vendor": forms.Select(attrs=select_attrs()),
            "connection_mode": forms.Select(attrs=select_attrs()),
            "device_type": forms.Select(attrs=select_attrs()),
            "location": forms.Select(attrs=select_attrs(searchable=True)),
            "serial_number": forms.TextInput(
                attrs={"placeholder": "e.g. CF4G… (from iFace Comm / About)"}
            ),
            "lan_host": forms.TextInput(attrs={"placeholder": "e.g. 192.168.1.50"}),
        }
        labels = {
            "serial_number": "Device serial (SN)",
            "lan_host": "Device LAN IP",
            "lan_port": "Device TCP port",
            "connection_mode": "Connection",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.filter(is_active=True)
        self.fields["location"].required = False
        self.fields["location"].empty_label = "— No location —"
        self.fields["notes"].required = False
        self.fields["serial_number"].required = False
        self.fields["lan_host"].required = False
        self.fields["lan_port"].required = False
        self.fields["vendor"].help_text = "Choose ZKTeco for iFace990 ADMS push"
        self.fields["connection_mode"].help_text = (
            "Local = ADMS server is Day Pay on your LAN · Global = public HTTPS URL · "
            "HTTP bridge = middleware posting JSON"
        )

    def clean_serial_number(self):
        sn = (self.cleaned_data.get("serial_number") or "").strip().upper()
        return sn

    def save(self, commit=True):
        import secrets

        obj = super().save(commit=False)
        if not obj.api_token:
            obj.api_token = secrets.token_urlsafe(32)
        if obj.vendor == PunchDevice.Vendor.ZKTECO and not obj.device_type:
            obj.device_type = PunchDevice.DeviceType.BIOMETRIC
        if commit:
            obj.save()
        return obj


class DeviceEnrollForm(forms.Form):
    """Push / enroll an employee on a ZKTeco device."""

    ACTION_ADD = "add"
    ACTION_FINGER = "finger"
    ACTION_FACE = "face"
    ACTION_REMOVE = "remove"
    ACTION_CHOICES = (
        (ACTION_ADD, "Add / update user on machine"),
        (ACTION_FINGER, "Enroll fingerprint on machine"),
        (ACTION_FACE, "Enroll face on machine"),
        ("sync_bio", "Push stored face/finger templates"),
        (ACTION_REMOVE, "Remove user from machine"),
    )

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs=select_attrs()),
        initial=ACTION_ADD,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = (
            Employee.objects.filter(
                status__in=[
                    Employee.Status.ACTIVE,
                    Employee.Status.DRAFT,
                    Employee.Status.ON_LEAVE,
                ]
            )
            .exclude(biometric_id="")
            .order_by("employee_code")
        )
        self.fields["employee"].help_text = (
            "Employee must have Biometric / device ID (machine PIN)."
        )
        self.fields["action"].help_text = (
            "Face/finger capture happens on the iFace screen after the command is queued."
        )


class ManualPunchForm(forms.ModelForm):
    class Meta:
        model = PunchLog
        fields = ("employee", "punched_at", "punch_type", "device", "notes")
        widgets = {
            "punched_at": datetime_widget(),
            "notes": forms.TextInput(attrs={"placeholder": "Optional"}),
            "employee": forms.Select(attrs=select_attrs(searchable=True)),
            "punch_type": forms.Select(attrs=select_attrs()),
            "device": forms.Select(attrs=select_attrs(searchable=True)),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.DRAFT,
                Employee.Status.ON_LEAVE,
            ]
        ).order_by("employee_code")
        self.fields["device"].queryset = PunchDevice.objects.filter(is_active=True)
        self.fields["device"].required = False
        self.fields["device"].empty_label = "— No device (manual) —"
        self.fields["notes"].required = False


class DayPunchForm(forms.Form):
    """Add a punch on a known employee + date (day editor)."""

    punch_time = forms.TimeField(widget=time_widget(), label="Time")
    punch_type = forms.ChoiceField(
        choices=PunchLog.PunchType.choices,
        widget=forms.Select(attrs=select_attrs()),
        initial=PunchLog.PunchType.OUT,
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Optional note"}),
    )


class DayPunchEditForm(forms.Form):
    """Edit an existing punch's time / type on a day."""

    punch_id = forms.IntegerField(widget=forms.HiddenInput)
    punch_time = forms.TimeField(widget=time_widget(), label="Time")
    punch_type = forms.ChoiceField(
        choices=PunchLog.PunchType.choices,
        widget=forms.Select(attrs=select_attrs()),
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Optional note"}),
    )


class GenerateAttendanceForm(forms.Form):
    date = forms.DateField(widget=date_widget())
    force = forms.BooleanField(
        required=False,
        initial=False,
        label="Overwrite locked rows",
        help_text="Only use if you intentionally re-open locked attendance",
    )


class MonthRegisterForm(forms.Form):
    year = forms.IntegerField(min_value=2020, max_value=2100)
    month = forms.ChoiceField(
        choices=[(i, cal.month_name[i]) for i in range(1, 13)],
        widget=forms.Select(attrs=select_attrs()),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        empty_label="— All departments —",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(
            is_active=True
        ).order_by("code")
        self.fields["month"].widget.attrs["data-auto-submit-field"] = "1"
        self.fields["department"].widget.attrs["data-auto-submit-field"] = "1"
        # Keep month as int after clean
        self.fields["month"].choices = [(str(i), cal.month_name[i]) for i in range(1, 13)]

    def clean_month(self):
        return int(self.cleaned_data["month"])


class DailyAttendanceEditForm(forms.ModelForm):
    class Meta:
        model = DailyAttendance
        fields = (
            "status",
            "worked_hours",
            "payable_hours",
            "break_hours",
            "expected_hours",
            "overtime_hours",
            "late_minutes",
            "penalty_minutes",
            "early_leave_minutes",
            "notes",
        )
        widgets = {
            "status": forms.Select(attrs=select_attrs()),
            "notes": forms.TextInput(attrs={"placeholder": "HR note / reason for edit"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        from .engine import (
            calculate_break_overrun_minutes,
            calculate_break_overrun_penalty_minutes,
            shift_version_on,
        )

        version = shift_version_on(instance.shift, instance.date)
        instance.break_overrun_minutes = calculate_break_overrun_minutes(
            instance.break_hours,
            version,
        )
        instance.break_overrun_penalty_minutes = calculate_break_overrun_penalty_minutes(
            instance.break_overrun_minutes,
            instance.shift,
        )
        if commit:
            instance.save()
        return instance


class PunchImportForm(forms.Form):
    format = forms.ChoiceField(
        label="File format",
        choices=[
            ("generic", "Generic CSV (employee_code / biometric_id)"),
            ("zkteco", "ZKTeco / eSSL style (AccNo + DateTime + Status)"),
        ],
        initial="generic",
        widget=forms.Select(attrs=select_attrs()),
    )
    file = forms.FileField(
        label="CSV file",
        help_text="Map machine user id to Employee → Biometric / device ID before import",
    )
    device = forms.ModelChoiceField(
        queryset=PunchDevice.objects.none(),
        required=False,
        empty_label="— Default device (optional) —",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["device"].queryset = PunchDevice.objects.filter(is_active=True)


class RegularizationRequestForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        widget=forms.Select(attrs=select_attrs(searchable=True)),
        help_text="Leave blank to request for yourself (when your user is linked to an employee).",
    )
    date = forms.DateField(widget=date_widget())
    requested_status = forms.ChoiceField(
        choices=DailyAttendance.Status.choices,
        widget=forms.Select(attrs=select_attrs()),
        label="Correct status to",
    )
    requested_worked_hours = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        min_value=0,
        label="Worked hours (optional)",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Why should this day be corrected?"}),
        min_length=8,
    )
    lock_on_approve = forms.BooleanField(
        required=False,
        initial=True,
        label="Lock day after approval",
        help_text="Recommended — stops Generate from overwriting the approved correction",
    )

    def __init__(self, *args, user=None, allow_pick_employee=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.allow_pick_employee = allow_pick_employee
        qs = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        ).order_by("employee_code")
        if allow_pick_employee:
            self.fields["employee"].queryset = qs
            self.fields["employee"].required = True
            self.fields["employee"].help_text = "Employee this correction is for."
        else:
            self.fields["employee"].queryset = Employee.objects.none()
            self.fields["employee"].widget = forms.HiddenInput()
            self.fields["employee"].required = False

    def clean(self):
        cleaned = super().clean()
        emp = cleaned.get("employee")
        if self.allow_pick_employee:
            if not emp:
                self.add_error("employee", "Select an employee.")
        else:
            from .regularization import employee_for_user

            emp = employee_for_user(self.user)
            if not emp:
                raise forms.ValidationError(
                    "Your login is not linked to an employee profile. Ask HR to link it, "
                    "or have HR submit on your behalf."
                )
            cleaned["employee"] = emp
        return cleaned


class RegularizationDecisionForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional note to the requester"}),
        label="Reviewer note",
    )
