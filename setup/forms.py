from django import forms

from core.form_widgets import select_attrs
from payroll.currencies import CURRENCY_CHOICES

from .models import OrganizationSettings


class OrganizationSettingsForm(forms.ModelForm):
    class Meta:
        model = OrganizationSettings
        fields = (
            "company_name",
            "legal_name",
            "logo",
            "address_line1",
            "address_line2",
            "city",
            "country",
            "phone",
            "email",
            "website",
            "trn",
            "default_currency",
            "cycle_start_day",
        )
        widgets = {
            "default_currency": forms.Select(attrs=select_attrs()),
            "cycle_start_day": forms.Select(attrs=select_attrs()),
            "address_line1": forms.TextInput(attrs={"placeholder": "Building / street"}),
            "address_line2": forms.TextInput(attrs={"placeholder": "Area / PO Box"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_currency"].choices = CURRENCY_CHOICES
        self.fields["default_currency"].help_text = (
            "New salary structures and templates default to this currency "
            "(e.g. AED for Dubai)."
        )
        self.fields["logo"].help_text = "PNG/JPG shown on payslip PDFs."
        cycle_choices = [
            (1, "1 — Calendar month (1st → last day)"),
            *[(d, f"{d} — {d}th → {d - 1}th next month") for d in range(2, 29)],
        ]
        # IntegerField + Select needs choices on the widget (not only .choices).
        self.fields["cycle_start_day"] = forms.TypedChoiceField(
            label="Attendance cycle",
            choices=cycle_choices,
            coerce=int,
            widget=forms.Select(attrs=select_attrs()),
            help_text=(
                "Used by attendance register and payroll periods. "
                "Example: 25 → August period is 25 Jul through 24 Aug."
            ),
            initial=self.instance.cycle_start_day if self.instance else 1,
        )

    def clean_cycle_start_day(self):
        day = int(self.cleaned_data["cycle_start_day"])
        if day < 1 or day > 28:
            raise forms.ValidationError("Choose a day between 1 and 28.")
        return day
