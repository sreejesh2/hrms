from django import forms
from django.forms import modelform_factory
from django.utils.text import slugify

from .models import (
    Bank,
    Department,
    Division,
    Employee,
    EmployeeAttributeDefinition,
    EmployeeAttributeValue,
    EmployeeDocument,
    Location,
    Position,
)
from .phone_codes import COUNTRY_DIAL_CODES, DEFAULT_COUNTRY_CODE


from core.form_widgets import date_widget, select_attrs

# Lazy-safe empty queryset; real queryset set in EmployeeForm.__init__.
def _empty_shift_qs():
    from attendance.models import WorkShift

    return WorkShift.objects.none()


def make_master_form(model):
    if model is Department:
        class DepartmentForm(forms.ModelForm):
            class Meta:
                model = Department
                fields = (
                    "code",
                    "description",
                    "division",
                    "default_shift",
                    "default_calendar",
                    "is_active",
                )
                widgets = {
                    "division": forms.Select(attrs=select_attrs()),
                    "default_shift": forms.Select(attrs=select_attrs(searchable=True)),
                    "default_calendar": forms.Select(attrs=select_attrs()),
                }

            def __init__(self, *args, **kwargs):
                from attendance.models import WorkCalendar, WorkShift

                super().__init__(*args, **kwargs)
                self.fields["division"].queryset = Division.objects.filter(
                    is_active=True
                ).order_by("code")
                self.fields["division"].required = False
                self.fields["division"].empty_label = "— No division —"
                self.fields["division"].help_text = (
                    "Optional — link this department to a division"
                )
                self.fields["default_shift"].queryset = WorkShift.objects.filter(
                    is_active=True
                ).order_by("code")
                self.fields["default_shift"].required = False
                self.fields["default_shift"].empty_label = "— No default shift —"
                self.fields["default_calendar"].queryset = WorkCalendar.objects.filter(
                    is_active=True
                ).order_by("code")
                self.fields["default_calendar"].required = False
                self.fields["default_calendar"].empty_label = "— No default calendar —"

        return DepartmentForm
    return modelform_factory(model, fields=("code", "description", "is_active"))


class EmployeeForm(forms.ModelForm):
    phone_country_code = forms.ChoiceField(
        label="Country code",
        choices=COUNTRY_DIAL_CODES,
        initial=DEFAULT_COUNTRY_CODE,
        required=False,
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    phone = forms.CharField(
        label="Phone number",
        required=False,
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "placeholder": "9876543210",
                "inputmode": "tel",
                "autocomplete": "tel-national",
            }
        ),
        help_text="Enter the number without the country code",
    )
    assigned_shift = forms.ModelChoiceField(
        label="Work shift",
        required=False,
        queryset=_empty_shift_qs(),
        empty_label="— No shift —",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
        help_text="Optional. Defaults to Day shift for new employees.",
    )

    class Meta:
        model = Employee
        fields = (
            "employee_code",
            "biometric_id",
            "first_name",
            "last_name",
            "email",
            "phone_country_code",
            "phone",
            "date_of_joining",
            "date_of_exit",
            "status",
            "department",
            "division",
            "location",
            "position",
            "bank",
            "manager",
        )
        widgets = {
            "date_of_joining": date_widget(),
            "date_of_exit": date_widget(),
            "employee_code": forms.TextInput(attrs={"placeholder": "e.g. E001"}),
            "biometric_id": forms.TextInput(
                attrs={"placeholder": "e.g. 10023 (device PIN / AccNo)"}
            ),
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"placeholder": "name@company.com"}),
            "status": forms.Select(attrs=select_attrs()),
            "department": forms.Select(attrs=select_attrs(searchable=True)),
            "division": forms.Select(attrs=select_attrs()),
            "location": forms.Select(attrs=select_attrs(searchable=True)),
            "position": forms.Select(attrs=select_attrs(searchable=True)),
            "bank": forms.Select(attrs=select_attrs()),
            "manager": forms.Select(attrs=select_attrs(searchable=True)),
            "phone_country_code": forms.Select(attrs=select_attrs(searchable=True)),
        }
        labels = {
            "employee_code": "Employee code",
            "biometric_id": "Biometric / device ID",
            "date_of_joining": "Date of joining",
            "date_of_exit": "Date of exit",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from attendance.models import ShiftAssignment, WorkShift

        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["division"].queryset = Division.objects.filter(is_active=True)
        self.fields["location"].queryset = Location.objects.filter(is_active=True)
        self.fields["position"].queryset = Position.objects.filter(is_active=True)
        self.fields["bank"].queryset = Bank.objects.filter(is_active=True)
        managers = Employee.objects.filter(
            status__in=[Employee.Status.ACTIVE, Employee.Status.ON_LEAVE]
        ).order_by("first_name", "last_name")
        if self.instance and self.instance.pk:
            managers = managers.exclude(pk=self.instance.pk)
        self.fields["manager"].queryset = managers

        shifts = WorkShift.objects.filter(is_active=True).order_by("code")
        self.fields["assigned_shift"].queryset = shifts
        day_shift = (
            shifts.filter(code__iexact="DAYSHIFT").first()
            or shifts.filter(code__iexact="DAY").first()
            or shifts.filter(name__icontains="day shift").first()
        )

        self.fields["employee_code"].help_text = "Unique ID used across attendance and payroll"
        self.fields["biometric_id"].help_text = (
            "Same ID enrolled on biometric / card machines (PIN, AccNo, badge)"
        )
        self.fields["biometric_id"].required = False
        self.fields["status"].help_text = "Onboarding starts as Draft until activated"
        self.fields["manager"].help_text = "Reporting manager for approvals"
        self.fields["position"].help_text = (
            "Optional. If this position is mapped to an OT policy, that overrides the work shift OT."
        )

        for name in (
            "department",
            "division",
            "location",
            "position",
            "bank",
            "manager",
            "last_name",
            "email",
            "phone",
            "phone_country_code",
            "date_of_joining",
            "biometric_id",
            "assigned_shift",
        ):
            self.fields[name].required = False

        if self.instance and self.instance.pk:
            code = (self.instance.phone_country_code or "").strip() or DEFAULT_COUNTRY_CODE
            if code not in dict(COUNTRY_DIAL_CODES):
                self.fields["phone_country_code"].choices = [
                    (code, f"Other ({code})")
                ] + list(COUNTRY_DIAL_CODES)
            self.fields["phone_country_code"].initial = code
            current = (
                ShiftAssignment.objects.filter(
                    employee=self.instance, is_active=True
                )
                .select_related("shift")
                .order_by("-effective_from", "-id")
                .first()
            )
            if current:
                self.fields["assigned_shift"].initial = current.shift_id
            elif day_shift:
                self.fields["assigned_shift"].initial = day_shift.pk
        else:
            self.fields["phone_country_code"].initial = DEFAULT_COUNTRY_CODE
            self.fields["status"].initial = Employee.Status.DRAFT
            if day_shift:
                self.fields["assigned_shift"].initial = day_shift.pk

        # Empty labels for selects
        for name in ("department", "division", "location", "position", "bank", "manager"):
            self.fields[name].empty_label = f"— Select {name.replace('_', ' ')} —"

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return ""
        # Keep digits, spaces, hyphens only for local part
        cleaned = "".join(ch for ch in phone if ch.isdigit() or ch in " -")
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        if len(digits) < 6:
            raise forms.ValidationError("Enter a valid phone number (at least 6 digits).")
        if len(digits) > 15:
            raise forms.ValidationError("Phone number is too long.")
        return digits

    def clean_phone_country_code(self):
        code = (self.cleaned_data.get("phone_country_code") or "").strip()
        if not code:
            return DEFAULT_COUNTRY_CODE
        if not code.startswith("+"):
            code = f"+{code}"
        return code

    def clean(self):
        cleaned = super().clean()
        phone = cleaned.get("phone") or ""
        code = cleaned.get("phone_country_code") or DEFAULT_COUNTRY_CODE
        if phone and not code:
            self.add_error("phone_country_code", "Select a country code for the phone number.")
        joined, exited = cleaned.get("date_of_joining"), cleaned.get("date_of_exit")
        if joined and exited and exited < joined:
            self.add_error("date_of_exit", "Date of exit cannot be before date of joining.")
        return cleaned


class EmployeeDocumentForm(forms.ModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ("title", "category", "file", "expires_on", "notes")
        widgets = {
            "expires_on": date_widget(),
            "notes": forms.TextInput(attrs={"placeholder": "Optional note"}),
        }
        labels = {
            "expires_on": "Expiry date",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expires_on"].required = False
        self.fields["expires_on"].help_text = "Optional — leave blank if not applicable"


class EmployeeAttributeDefinitionForm(forms.ModelForm):
    choices_text = forms.CharField(
        required=False,
        label="Dropdown options",
        help_text="One option per line (only for Dropdown type).",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Option A\nOption B"}),
    )

    class Meta:
        model = EmployeeAttributeDefinition
        fields = (
            "label",
            "key",
            "field_type",
            "help_text",
            "required",
            "sort_order",
            "is_active",
        )
        widgets = {
            "help_text": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["key"].required = False
        if self.instance and self.instance.pk and self.instance.choices:
            self.fields["choices_text"].initial = "\n".join(self.instance.choice_list())

    def clean_key(self):
        key = self.cleaned_data.get("key") or ""
        label = self.cleaned_data.get("label") or ""
        if not key:
            key = slugify(label).replace("-", "_")[:64]
        key = slugify(key).replace("-", "_")
        if not key:
            raise forms.ValidationError("Could not build a key from the label.")
        return key

    def clean(self):
        cleaned = super().clean()
        field_type = cleaned.get("field_type")
        raw = (cleaned.get("choices_text") or "").strip()
        options = [line.strip() for line in raw.splitlines() if line.strip()]
        if field_type == EmployeeAttributeDefinition.FieldType.SELECT and not options:
            self.add_error("choices_text", "Add at least one dropdown option.")
        cleaned["choices"] = options
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.choices = self.cleaned_data.get("choices") or []
        if commit:
            obj.save()
        return obj


class EmployeeDynamicAttributesForm(forms.Form):
    """Build fields from active EmployeeAttributeDefinition rows."""

    def __init__(self, employee: Employee, definitions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        self.definitions = list(definitions)
        existing = {}
        if employee is not None and getattr(employee, "pk", None):
            existing = {
                v.definition_id: v.value
                for v in employee.attribute_values.all()
            }
        for d in self.definitions:
            name = f"attr_{d.pk}"
            initial = existing.get(d.pk, "")
            if d.field_type == EmployeeAttributeDefinition.FieldType.TEXTAREA:
                field = forms.CharField(
                    label=d.label,
                    required=d.required,
                    initial=initial,
                    help_text=d.help_text,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            elif d.field_type == EmployeeAttributeDefinition.FieldType.NUMBER:
                field = forms.DecimalField(
                    label=d.label,
                    required=d.required,
                    initial=initial or None,
                    help_text=d.help_text,
                )
            elif d.field_type == EmployeeAttributeDefinition.FieldType.DATE:
                field = forms.DateField(
                    label=d.label,
                    required=d.required,
                    initial=initial or None,
                    help_text=d.help_text,
                    widget=date_widget(),
                )
            elif d.field_type == EmployeeAttributeDefinition.FieldType.BOOLEAN:
                field = forms.BooleanField(
                    label=d.label,
                    required=False,
                    initial=initial.lower() in ("1", "true", "yes", "on"),
                    help_text=d.help_text,
                )
            elif d.field_type == EmployeeAttributeDefinition.FieldType.SELECT:
                choices = [("", "— Select —")] + [(c, c) for c in d.choice_list()]
                field = forms.ChoiceField(
                    label=d.label,
                    required=d.required,
                    choices=choices,
                    initial=initial,
                    help_text=d.help_text,
                )
            else:
                field = forms.CharField(
                    label=d.label,
                    required=d.required,
                    initial=initial,
                    help_text=d.help_text,
                    max_length=500,
                )
            self.fields[name] = field

    def save(self):
        for d in self.definitions:
            name = f"attr_{d.pk}"
            raw = self.cleaned_data.get(name)
            if d.field_type == EmployeeAttributeDefinition.FieldType.BOOLEAN:
                value = "true" if raw else "false"
            elif raw is None:
                value = ""
            else:
                value = str(raw)
            EmployeeAttributeValue.objects.update_or_create(
                employee=self.employee,
                definition=d,
                defaults={"value": value},
            )


class EmployeeCreateLoginForm(forms.Form):
    email = forms.EmailField(
        label="Login email",
        widget=forms.EmailInput(
            attrs={"autocomplete": "off", "placeholder": "name@company.com"}
        ),
    )
    role = forms.ChoiceField(
        label="Role",
        choices=(
            ("Employee", "Employee — self-service"),
            ("Manager", "Manager — team approvals"),
        ),
        initial="Employee",
        widget=forms.Select(attrs=select_attrs()),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Temporary password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Confirm password",
            }
        ),
    )

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        if employee and employee.email and not self.is_bound:
            self.fields["email"].initial = employee.email

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1 and len(p1) < 8:
            self.add_error("password1", "Use at least 8 characters.")
        return cleaned


class EmployeeResetPasswordForm(forms.Form):
    password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": "New password"}
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": "Confirm password"}
        ),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1 and len(p1) < 8:
            self.add_error("password1", "Use at least 8 characters.")
        return cleaned

