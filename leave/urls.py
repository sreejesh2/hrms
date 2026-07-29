from django.urls import path

from . import views

app_name = "leave"

urlpatterns = [
    path("", views.leave_list, name="list"),
    path("apply/", views.leave_create, name="create"),
    path("apply/quick/", views.leave_quick_apply, name="quick_apply"),
    path("<int:pk>/", views.leave_detail, name="detail"),
    path("types/", views.leave_type_list, name="type_list"),
    path("types/new/", views.leave_type_edit, name="type_create"),
    path("types/<int:pk>/", views.leave_type_edit, name="type_edit"),
    path("balances/", views.leave_balance_list, name="balance_list"),
    path("balances/new/", views.leave_balance_edit, name="balance_create"),
    path("balances/<int:pk>/", views.leave_balance_edit, name="balance_edit"),
    path("balances/ensure-year/", views.leave_balance_ensure_year, name="balance_ensure"),
]
