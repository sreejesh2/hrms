from __future__ import annotations

import calendar
from datetime import date

from django import forms
from django.utils import timezone

from core.form_widgets import date_widget, select_attrs
from people.models import Department, Employee
from payroll.models import PayrollPeriod


def _year_choices(span: int = 6):
    y = timezone.localdate().year
    return [(i, str(i)) for i in range(y, y - span, -1)]


def _month_choices():
    return [(i, calendar.month_name[i]) for i in range(1, 13)]


class PeriodFilterForm(forms.Form):
    period = forms.ModelChoiceField(
        queryset=PayrollPeriod.objects.all(),
        empty_label="Select payroll period…",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
        label="Payroll period",
    )


class MonthFilterForm(forms.Form):
    year = forms.TypedChoiceField(
        choices=_year_choices,
        coerce=int,
        widget=forms.Select(attrs=select_attrs()),
    )
    month = forms.TypedChoiceField(
        choices=_month_choices,
        coerce=int,
        widget=forms.Select(attrs=select_attrs()),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True).order_by("code"),
        required=False,
        empty_label="All departments",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["year"].initial = today.year
        self.fields["month"].initial = today.month

    @property
    def month_bounds(self) -> tuple[date, date]:
        y = self.cleaned_data["year"]
        m = self.cleaned_data["month"]
        last = calendar.monthrange(y, m)[1]
        return date(y, m, 1), date(y, m, last)


class DateRangeFilterForm(forms.Form):
    date_from = forms.DateField(label="From", widget=date_widget())
    date_to = forms.DateField(label="To", widget=date_widget())
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True).order_by("code"),
        required=False,
        empty_label="All departments",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        start = today.replace(day=1)
        self.fields["date_from"].initial = start
        self.fields["date_to"].initial = today

    def clean(self):
        cleaned = super().clean()
        d0 = cleaned.get("date_from")
        d1 = cleaned.get("date_to")
        if d0 and d1 and d1 < d0:
            self.add_error("date_to", "End date must be on or after the start date.")
        return cleaned


class YearFilterForm(forms.Form):
    year = forms.TypedChoiceField(
        choices=_year_choices,
        coerce=int,
        widget=forms.Select(attrs=select_attrs()),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True).order_by("code"),
        required=False,
        empty_label="All departments",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].initial = timezone.localdate().year


class AsOfFilterForm(forms.Form):
    as_of = forms.DateField(label="As of", widget=date_widget())
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True).order_by("code"),
        required=False,
        empty_label="All departments",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
    status = forms.ChoiceField(
        choices=[("", "All statuses")] + list(Employee.Status.choices),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
        label="Employee status",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["as_of"].initial = timezone.localdate()
        self.fields["status"].initial = Employee.Status.ACTIVE


class HeadcountFilterForm(forms.Form):
    status = forms.ChoiceField(
        choices=[("", "All statuses")] + list(Employee.Status.choices),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True).order_by("code"),
        required=False,
        empty_label="All departments",
        widget=forms.Select(attrs=select_attrs(searchable=True)),
    )
