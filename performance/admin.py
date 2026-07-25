from django.contrib import admin

from . import models


class ReviewCompetencyScoreInline(admin.TabularInline):
    model = models.ReviewCompetencyScore
    extra = 0
    fields = ("competency", "self_rating", "manager_rating", "self_comment", "manager_comment")
    raw_id_fields = ("competency",)


@admin.register(models.ReviewCycle)
class ReviewCycleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "status",
        "start_date",
        "end_date",
        "self_review_due",
        "manager_review_due",
    )
    list_filter = ("status",)
    search_fields = ("code", "name")
    ordering = ("-start_date",)


@admin.register(models.Competency)
class CompetencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "name")


@admin.register(models.PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = (
        "cycle",
        "employee",
        "manager",
        "status",
        "overall_self_rating",
        "overall_manager_rating",
        "self_submitted_at",
        "manager_submitted_at",
        "completed_at",
    )
    list_filter = ("status", "cycle")
    search_fields = (
        "employee__employee_code",
        "employee__first_name",
        "employee__last_name",
    )
    raw_id_fields = ("cycle", "employee", "manager")
    inlines = [ReviewCompetencyScoreInline]


@admin.register(models.ReviewCompetencyScore)
class ReviewCompetencyScoreAdmin(admin.ModelAdmin):
    list_display = ("review", "competency", "self_rating", "manager_rating")
    list_filter = ("competency",)
    search_fields = ("review__employee__employee_code", "competency__code")
    raw_id_fields = ("review", "competency")
