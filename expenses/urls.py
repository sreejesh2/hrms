from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.claim_list, name="list"),
    path("new/", views.claim_create, name="create"),
    path("<int:pk>/", views.claim_detail, name="detail"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/new/", views.category_edit, name="category_create"),
    path("categories/<int:pk>/", views.category_edit, name="category_edit"),
]
