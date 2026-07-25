from django.contrib import admin

from .models import AdvanceRecovery, SalaryAdvance


@admin.register(SalaryAdvance)
class SalaryAdvanceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "amount",
        "recovered_amount",
        "status",
        "installments",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("employee__employee_code", "reason", "disburse_reference")


@admin.register(AdvanceRecovery)
class AdvanceRecoveryAdmin(admin.ModelAdmin):
    list_display = ("advance", "amount", "period", "created_at")
    list_filter = ("period",)
