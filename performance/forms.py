from django import forms
from django.forms import modelformset_factory

from core.form_widgets import date_widget, select_attrs

from .models import RATING_CHOICES, Competency, ReviewCompetencyScore, ReviewCycle


class ReviewCycleForm(forms.ModelForm):
    class Meta:
        model = ReviewCycle
        fields = (
            "code",
            "name",
            "description",
            "start_date",
            "end_date",
            "self_review_due",
            "manager_review_due",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "start_date": date_widget(),
            "end_date": date_widget(),
            "self_review_due": date_widget(),
            "manager_review_due": date_widget(),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        self_due = cleaned.get("self_review_due")
        mgr_due = cleaned.get("manager_review_due")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        if self_due and mgr_due and mgr_due < self_due:
            self.add_error(
                "manager_review_due",
                "Manager review due date should be on or after the self-review due date.",
            )
        return cleaned


class CompetencyForm(forms.ModelForm):
    class Meta:
        model = Competency
        fields = ("code", "name", "description", "sort_order", "is_active")


RATING_SELECT_ATTRS = select_attrs(extra_class="perf-rating-select")


class SelfReviewForm(forms.Form):
    overall_self_rating = forms.TypedChoiceField(
        choices=[("", "—")] + list(RATING_CHOICES),
        coerce=int,
        required=False,
        empty_value=None,
        label="Overall self-rating",
        widget=forms.Select(attrs=RATING_SELECT_ATTRS),
    )
    self_summary = forms.CharField(
        required=False,
        label="Self-assessment summary",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Key wins, challenges, and context for this cycle"}),
    )
    employee_goals = forms.CharField(
        required=False,
        label="Goals for next cycle",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "What you want to focus on next"}),
    )


class ManagerReviewForm(forms.Form):
    overall_manager_rating = forms.TypedChoiceField(
        choices=[("", "—")] + list(RATING_CHOICES),
        coerce=int,
        required=False,
        empty_value=None,
        label="Overall manager rating",
        widget=forms.Select(attrs=RATING_SELECT_ATTRS),
    )
    manager_summary = forms.CharField(
        required=False,
        label="Manager assessment summary",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Performance summary and feedback"}),
    )
    development_plan = forms.CharField(
        required=False,
        label="Development plan",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Growth areas and support for next cycle"}),
    )


SelfCompetencyScoreFormSet = modelformset_factory(
    ReviewCompetencyScore,
    fields=("self_rating", "self_comment"),
    extra=0,
    can_delete=False,
    widgets={
        "self_rating": forms.Select(
            choices=[("", "—")] + list(RATING_CHOICES),
            attrs=RATING_SELECT_ATTRS,
        ),
        "self_comment": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional comment"}),
    },
)

ManagerCompetencyScoreFormSet = modelformset_factory(
    ReviewCompetencyScore,
    fields=("manager_rating", "manager_comment"),
    extra=0,
    can_delete=False,
    widgets={
        "manager_rating": forms.Select(
            choices=[("", "—")] + list(RATING_CHOICES),
            attrs=RATING_SELECT_ATTRS,
        ),
        "manager_comment": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional comment"}),
    },
)
