from django import forms

from core.form_widgets import date_widget, select_attrs
from people.models import Employee

from .models import LeaveBalance, LeaveRequest, LeaveType
from .services import calc_leave_days, employee_for_user


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = (
            "code",
            "name",
            "description",
            "is_paid",
            "requires_approval",
            "exclude_off_days",
            "default_entitlement",
            "is_active",
        )


class LeaveRequestForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    leave_type = forms.ModelChoiceField(
        queryset=LeaveType.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    start_date = forms.DateField(widget=date_widget())
    end_date = forms.DateField(widget=date_widget())
    is_half_day = forms.BooleanField(
        required=False,
        initial=False,
        label="Half day",
        help_text="Only when start and end are the same date (counts as 0.5)",
    )
    reason = forms.CharField(
        min_length=5,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Reason for leave"}),
    )
    apply_to_attendance = forms.BooleanField(
        required=False,
        initial=True,
        label="Mark attendance On leave when approved",
    )

    def __init__(
        self,
        *args,
        user=None,
        allow_pick_employee=False,
        locked_employee=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.user = user
        self.allow_pick_employee = allow_pick_employee
        self.locked_employee = locked_employee
        self.fields["leave_type"].queryset = LeaveType.objects.filter(is_active=True)
        qs = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        ).order_by("employee_code")
        if locked_employee is not None:
            self.fields["employee"].queryset = Employee.objects.filter(
                pk=locked_employee.pk
            )
            self.fields["employee"].initial = locked_employee.pk
            self.fields["employee"].widget = forms.HiddenInput()
            self.fields["employee"].required = True
        elif allow_pick_employee:
            self.fields["employee"].queryset = qs
            self.fields["employee"].required = True
        else:
            self.fields["employee"].queryset = Employee.objects.none()
            self.fields["employee"].widget = forms.HiddenInput()
            self.fields["employee"].required = False

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        half = cleaned.get("is_half_day")
        if start and end:
            try:
                cleaned["days"] = calc_leave_days(start, end, is_half_day=half)
            except ValueError as exc:
                raise forms.ValidationError(str(exc)) from exc
        if self.locked_employee is not None:
            cleaned["employee"] = self.locked_employee
        elif self.allow_pick_employee:
            if not cleaned.get("employee"):
                self.add_error("employee", "Select an employee.")
        else:
            emp = employee_for_user(self.user)
            if not emp:
                raise forms.ValidationError(
                    "Your login is not linked to an employee profile. Ask HR to link it, "
                    "or have HR apply on your behalf."
                )
            cleaned["employee"] = emp
        return cleaned


class LeaveDecisionForm(forms.Form):
    notes = forms.CharField(
        required=False,
        label="Reviewer note",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional note"}),
    )


class LeaveBalanceForm(forms.ModelForm):
    class Meta:
        model = LeaveBalance
        fields = ("employee", "leave_type", "year", "entitled")
        widgets = {
            "employee": forms.Select(attrs=select_attrs(searchable=True)),
            "leave_type": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        ).order_by("employee_code")
        self.fields["leave_type"].queryset = LeaveType.objects.filter(is_active=True)
