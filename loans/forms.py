from django import forms

from core.form_widgets import select_attrs
from people.models import Employee
from payroll.currencies import CURRENCY_CHOICES, default_currency_code

from .models import SalaryAdvance


class SalaryAdvanceForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    installments = forms.IntegerField(
        min_value=1,
        max_value=36,
        initial=1,
        help_text="Recover over this many payroll months",
    )
    currency = forms.ChoiceField(choices=CURRENCY_CHOICES, widget=forms.Select(attrs=select_attrs()))
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Optional reason"}),
    )

    def __init__(self, *args, user=None, can_pick_employee=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].initial = default_currency_code()
        qs = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        ).order_by("employee_code")
        if can_pick_employee:
            self.fields["employee"].queryset = qs
            self.fields["employee"].required = True
        else:
            self.fields.pop("employee", None)


class AdvanceDecisionForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional notes"}),
    )


class AdvanceDisburseForm(forms.Form):
    disburse_method = forms.ChoiceField(
        choices=SalaryAdvance.DisburseMethod.choices,
        widget=forms.Select(attrs=select_attrs()),
        initial=SalaryAdvance.DisburseMethod.BANK,
    )
    disburse_reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Transfer / voucher ref"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
