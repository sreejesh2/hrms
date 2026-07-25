from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.advance_list, name="list"),
    path("new/", views.advance_create, name="create"),
    path("<int:pk>/", views.advance_detail, name="detail"),
]
