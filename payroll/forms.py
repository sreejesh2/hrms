from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
import calendar

from core.form_widgets import date_widget, select_attrs
from people.models import Employee

from .currencies import CURRENCY_CHOICES, default_currency_code
from .models import (
    IncentiveAward,
    IncentivePlan,
    PayrollPeriod,
    PayslipTemplate,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureLine,
    SalaryTemplate,
    SalaryTemplateLine,
    StatutoryRule,
)


class SalaryComponentSelect(forms.Select):
    """Embeds calc-method metadata on options for Amount / % UI hints."""

    def __init__(self, *args, components_by_pk=None, **kwargs):
        self.components_by_pk = components_by_pk or {}
        super().__init__(*args, **kwargs)

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        raw = getattr(value, "value", value)
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            return option
        c = self.components_by_pk.get(pk)
        if c:
            option["attrs"]["data-calc"] = c.calc_method
            option["attrs"]["data-percent"] = (
                str(c.default_percent) if c.default_percent is not None else ""
            )
            option["attrs"]["data-basic"] = "1" if c.is_basic else "0"
            option["attrs"]["data-kind"] = c.kind
        return option


_AMOUNT_ATTRS = {
    "class": "pay-line-input pay-line-amount",
    "step": "0.01",
    "min": "0",
    "placeholder": "0.00",
    "inputmode": "decimal",
    "size": "10",
}
_PERCENT_ATTRS = {
    "class": "pay-line-input pay-line-percent",
    "inputmode": "decimal",
    "placeholder": "40",
    "autocomplete": "off",
    "maxlength": "6",
    "size": "4",
    "style": "width:2.6rem;max-width:2.6rem;min-width:0",
}


def _setup_money_line_fields(form):
    comps = list(
        SalaryComponent.objects.filter(is_active=True).order_by("sort_order", "code")
    )
    form.fields["component"].queryset = SalaryComponent.objects.filter(
        is_active=True
    ).order_by("sort_order", "code")
    form.fields["component"].empty_label = "Select component…"
    form.fields["component"].widget.components_by_pk = {c.pk: c for c in comps}
    form.fields["amount"].label = "Amount"
    form.fields["percent"].label = "%"
    form.fields["amount"].help_text = ""
    form.fields["percent"].help_text = ""
    form.fields["percent"].widget = forms.TextInput(attrs=_PERCENT_ATTRS)


class SalaryComponentForm(forms.ModelForm):
    class Meta:
        model = SalaryComponent
        fields = (
            "code",
            "name",
            "kind",
            "calc_method",
            "default_percent",
            "is_basic",
            "is_taxable",
            "affects_ot_base",
            "sort_order",
            "is_active",
        )
        widgets = {
            "kind": forms.Select(attrs=select_attrs()),
            "calc_method": forms.Select(attrs=select_attrs()),
        }


class SalaryTemplateForm(forms.ModelForm):
    class Meta:
        model = SalaryTemplate
        fields = ("code", "name", "description", "currency", "is_active")
        widgets = {"currency": forms.Select(attrs=select_attrs())}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].choices = CURRENCY_CHOICES
        if not self.instance.pk:
            self.fields["currency"].initial = default_currency_code()


class SalaryTemplateLineForm(forms.ModelForm):
    class Meta:
        model = SalaryTemplateLine
        fields = ("component", "amount", "percent")
        widgets = {
            "component": SalaryComponentSelect(
                attrs=select_attrs(extra_class="pay-line-component")
            ),
            "amount": forms.NumberInput(attrs=_AMOUNT_ATTRS),
            "percent": forms.NumberInput(attrs=_PERCENT_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _setup_money_line_fields(self)


SalaryTemplateLineFormSet = inlineformset_factory(
    SalaryTemplate,
    SalaryTemplateLine,
    form=SalaryTemplateLineForm,
    extra=4,
    can_delete=True,
)


class SalaryStructureForm(forms.ModelForm):
    class Meta:
        model = SalaryStructure
        fields = ("employee", "effective_from", "currency", "notes")
        widgets = {
            "employee": forms.Select(attrs=select_attrs(searchable=True)),
            "effective_from": date_widget(),
            "currency": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, lock_employee=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].choices = CURRENCY_CHOICES
        if not self.instance.pk:
            self.fields["currency"].initial = default_currency_code()
        self.fields["employee"].queryset = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        ).order_by("employee_code")
        if lock_employee and self.instance.pk:
            self.fields["employee"].disabled = True
            self.fields["employee"].required = False


class SalaryStructureLineForm(forms.ModelForm):
    class Meta:
        model = SalaryStructureLine
        fields = ("component", "amount", "percent")
        widgets = {
            "component": SalaryComponentSelect(
                attrs=select_attrs(extra_class="pay-line-component")
            ),
            "amount": forms.NumberInput(attrs=_AMOUNT_ATTRS),
            "percent": forms.NumberInput(attrs=_PERCENT_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _setup_money_line_fields(self)


SalaryStructureLineFormSet = inlineformset_factory(
    SalaryStructure,
    SalaryStructureLine,
    form=SalaryStructureLineForm,
    extra=5,
    can_delete=True,
)


class ApplyTemplateForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    template = forms.ModelChoiceField(
        queryset=SalaryTemplate.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    effective_from = forms.DateField(widget=date_widget())
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        widget=forms.Select(attrs=select_attrs()),
        help_text="Defaults to the template currency; change if needed.",
    )
    notes = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        ).order_by("employee_code")
        self.fields["template"].queryset = SalaryTemplate.objects.filter(is_active=True)
        self.fields["currency"].choices = CURRENCY_CHOICES
        self.fields["currency"].initial = default_currency_code()


class PayrollPeriodForm(forms.Form):
    year = forms.IntegerField(min_value=2000, max_value=2100)
    month = forms.TypedChoiceField(
        coerce=int,
        choices=[(i, calendar.month_name[i]) for i in range(1, 13)],
        widget=forms.Select(attrs=select_attrs()),
    )
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        widget=forms.Select(attrs=select_attrs()),
    )
    notes = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from setup.cycles import cycle_help_text, period_bounds, period_for_date

        today = timezone.localdate()
        y, m, start, end = period_for_date(today)
        self.fields["year"].initial = y
        self.fields["month"].initial = m
        self.fields["currency"].choices = CURRENCY_CHOICES
        self.fields["currency"].initial = default_currency_code()
        self.fields["month"].help_text = (
            f"{cycle_help_text()} Current selection preview uses company cycle "
            f"({start.isoformat()} → {end.isoformat()} for {calendar.month_name[m]} {y})."
        )

    def period_preview(self):
        from setup.cycles import period_bounds

        year = self.cleaned_data.get("year") or self.fields["year"].initial
        month = self.cleaned_data.get("month") or self.fields["month"].initial
        return period_bounds(int(year), int(month))


class PayslipTemplateForm(forms.ModelForm):
    class Meta:
        model = PayslipTemplate
        fields = (
            "name",
            "document_title",
            "header_note",
            "footer_text",
            "bank_note",
            "show_logo",
            "show_address",
            "show_phone",
            "show_email",
            "show_trn",
            "show_paid_days",
            "show_ot",
            "header_html",
            "footer_html",
            "is_default",
        )
        widgets = {
            "footer_text": forms.Textarea(attrs={"rows": 3}),
            "header_html": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Optional advanced HTML — leave blank for default header",
                }
            ),
            "footer_html": forms.Textarea(attrs={"rows": 3}),
        }


class StatutoryRuleForm(forms.ModelForm):
    class Meta:
        model = StatutoryRule
        fields = (
            "code",
            "name",
            "kind",
            "calc_method",
            "amount",
            "percent",
            "min_amount",
            "max_amount",
            "country",
            "notes",
            "sort_order",
            "apply_in_payroll",
            "is_active",
        )
        widgets = {
            "kind": forms.Select(attrs=select_attrs()),
            "calc_method": forms.Select(attrs=select_attrs()),
            "notes": forms.TextInput(),
        }


class IncentivePlanForm(forms.ModelForm):
    class Meta:
        model = IncentivePlan
        fields = ("code", "name", "component", "frequency", "is_active")
        widgets = {
            "component": SalaryComponentSelect(attrs=select_attrs()),
            "frequency": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["component"].queryset = SalaryComponent.objects.filter(
            is_active=True, kind=SalaryComponent.Kind.EARNING
        ).order_by("sort_order", "code")
        self.fields["component"].help_text = (
            "Payslip earning head (e.g. BONUS or INCENTIVE)."
        )


class IncentiveAwardForm(forms.ModelForm):
    class Meta:
        model = IncentiveAward
        fields = ("plan", "employee", "period", "amount", "currency", "notes")
        widgets = {
            "plan": forms.Select(attrs=select_attrs()),
            "employee": forms.Select(attrs=select_attrs()),
            "period": forms.Select(attrs=select_attrs()),
            "currency": forms.Select(attrs=select_attrs()),
            "notes": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from people.models import Employee

        from .currencies import default_currency_code

        self.fields["plan"].queryset = IncentivePlan.objects.filter(
            is_active=True
        ).select_related("component")
        self.fields["employee"].queryset = Employee.objects.filter(
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.ON_LEAVE,
                Employee.Status.DRAFT,
            ]
        ).order_by("employee_code")
        self.fields["period"].queryset = PayrollPeriod.objects.exclude(
            status=PayrollPeriod.Status.LOCKED
        ).order_by("-year", "-month")
        self.fields["currency"].choices = CURRENCY_CHOICES
        if not self.instance.pk:
            self.fields["currency"].initial = default_currency_code()

    def clean(self):
        cleaned = super().clean()
        period = cleaned.get("period")
        amount = cleaned.get("amount")
        plan = cleaned.get("plan")
        employee = cleaned.get("employee")
        if period and period.is_locked:
            raise forms.ValidationError("Cannot assign awards to a locked period.")
        if amount is not None and amount <= 0:
            self.add_error("amount", "Amount must be greater than zero.")
        if plan and employee and period:
            qs = IncentiveAward.objects.filter(
                plan=plan,
                employee=employee,
                period=period,
                status__in=[
                    IncentiveAward.Status.DRAFT,
                    IncentiveAward.Status.APPROVED,
                ],
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "An open award already exists for this employee, plan, and period."
                )
        return cleaned


class IncentiveAwardImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV file",
        help_text=(
            "Columns: employee_code, plan_code, amount, period_year, period_month "
            "(optional: notes, currency). Creates draft awards."
        ),
    )
