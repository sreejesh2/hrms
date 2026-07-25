from django.contrib import admin

from .models import ExpenseCategory, ExpenseClaim, ExpenseLine


class ExpenseLineInline(admin.TabularInline):
    model = ExpenseLine
    extra = 0


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "requires_receipt", "is_active", "sort_order")
    list_filter = ("is_active", "requires_receipt")
    search_fields = ("code", "name")


@admin.register(ExpenseClaim)
class ExpenseClaimAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "employee",
        "status",
        "currency",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("title", "employee__employee_code", "employee__first_name")
    inlines = [ExpenseLineInline]
