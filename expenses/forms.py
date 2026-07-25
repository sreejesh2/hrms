from django import forms
from django.forms import inlineformset_factory

from core.form_widgets import date_widget, select_attrs
from people.models import Employee
from payroll.currencies import CURRENCY_CHOICES, default_currency_code

from .models import ExpenseCategory, ExpenseClaim, ExpenseLine
from .services import employee_for_user


class ExpenseCategorySelect(forms.Select):
    """Expose requires_receipt on options for the claim UI."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        if value and hasattr(self, "categories_by_pk"):
            try:
                pk = int(value.value if hasattr(value, "value") else value)
            except (TypeError, ValueError):
                return option
            cat = self.categories_by_pk.get(pk)
            if cat:
                option["attrs"]["data-receipt"] = "1" if cat.requires_receipt else "0"
                option["label"] = (
                    f"{cat.name} · receipt" if cat.requires_receipt else cat.name
                )
        return option


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = (
            "code",
            "name",
            "description",
            "requires_receipt",
            "sort_order",
            "is_active",
        )


class ExpenseClaimForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        widget=forms.Select(attrs=select_attrs(searchable=True)),
        label="Employee",
    )
    title = forms.CharField(
        max_length=160,
        label="Claim title",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Dubai client visit — Jul",
                "autocomplete": "off",
                "class": "exp-claim-title",
            }
        ),
    )
    purpose = forms.CharField(
        required=False,
        label="Business purpose",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Optional — project, trip, cost centre, or why these costs were incurred",
                "class": "exp-claim-purpose",
            }
        ),
    )
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        widget=forms.Select(attrs=select_attrs(extra_class="exp-currency-select")),
        label="Currency",
    )

    def __init__(self, *args, user=None, allow_pick_employee=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.allow_pick_employee = allow_pick_employee
        self.fields["currency"].initial = default_currency_code()
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
        else:
            self.fields["employee"].queryset = Employee.objects.none()
            self.fields["employee"].widget = forms.HiddenInput()
            self.fields["employee"].required = False

    def clean(self):
        cleaned = super().clean()
        if self.allow_pick_employee:
            if not cleaned.get("employee"):
                self.add_error("employee", "Select an employee.")
        else:
            emp = employee_for_user(self.user)
            if not emp:
                raise forms.ValidationError(
                    "Your login is not linked to an employee profile. Ask HR to link it, "
                    "or have HR submit on your behalf."
                )
            cleaned["employee"] = emp
        return cleaned


class ExpenseLineForm(forms.ModelForm):
    class Meta:
        model = ExpenseLine
        fields = (
            "category",
            "expense_date",
            "amount",
            "merchant",
            "description",
            "receipt",
        )
        widgets = {
            "category": ExpenseCategorySelect(
                attrs=select_attrs(extra_class="exp-line-category")
            ),
            "expense_date": date_widget(**{"class": "exp-line-date"}),
            "amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0.01",
                    "placeholder": "0.00",
                    "class": "exp-line-amount",
                    "inputmode": "decimal",
                }
            ),
            "merchant": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Careem, Emirates, Staples",
                    "class": "exp-line-merchant",
                    "autocomplete": "organization",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "What was purchased / why — e.g. Airport transfer for client visit",
                    "class": "exp-line-desc",
                }
            ),
            "receipt": forms.ClearableFileInput(
                attrs={
                    "class": "exp-line-receipt-input",
                    "accept": "image/*,.pdf,.png,.jpg,.jpeg,.webp",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cats = list(
            ExpenseCategory.objects.filter(is_active=True).order_by("sort_order", "code")
        )
        self.fields["category"].queryset = ExpenseCategory.objects.filter(
            is_active=True
        ).order_by("sort_order", "code")
        self.fields["category"].empty_label = "Select category…"
        self.fields["category"].widget.categories_by_pk = {c.pk: c for c in cats}
        self.fields["amount"].required = False
        self.fields["expense_date"].required = False
        self.fields["category"].required = False
        self.fields["receipt"].label = "Receipt"

    def clean(self):
        cleaned = super().clean()
        has_any = any(
            [
                cleaned.get("category"),
                cleaned.get("expense_date"),
                cleaned.get("amount"),
                cleaned.get("merchant"),
                cleaned.get("description"),
                cleaned.get("receipt"),
            ]
        )
        cleaned["_has_content"] = bool(has_any)
        if not has_any:
            # Ignore DELETE on empty rows
            cleaned["DELETE"] = False
            return cleaned
        if not cleaned.get("category"):
            self.add_error("category", "Required.")
        if not cleaned.get("expense_date"):
            self.add_error("expense_date", "Required.")
        amount = cleaned.get("amount")
        if amount is None:
            self.add_error("amount", "Required.")
        elif amount <= 0:
            self.add_error("amount", "Must be greater than zero.")
        cat = cleaned.get("category")
        if cat and cat.requires_receipt and not cleaned.get("receipt"):
            if not (self.instance and self.instance.pk and self.instance.receipt):
                self.add_error("receipt", f"Receipt required for {cat.code}.")
        return cleaned


ExpenseLineFormSet = inlineformset_factory(
    ExpenseClaim,
    ExpenseLine,
    form=ExpenseLineForm,
    extra=2,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class ExpenseDecisionForm(forms.Form):
    notes = forms.CharField(
        required=False,
        label="Reviewer note",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional note"}),
    )


class ExpensePayForm(forms.Form):
    payment_method = forms.ChoiceField(
        choices=ExpenseClaim.PaymentMethod.choices,
        initial=ExpenseClaim.PaymentMethod.BANK,
        widget=forms.Select(attrs=select_attrs()),
        label="Payment method",
    )
    payment_reference = forms.CharField(
        required=False,
        max_length=120,
        label="Reference",
        widget=forms.TextInput(
            attrs={"placeholder": "Transfer ref / cheque no. / payroll period"}
        ),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional payout note"}),
    )
