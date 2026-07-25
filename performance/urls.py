from django.urls import path

from . import views

app_name = "performance"

urlpatterns = [
    path("", views.review_list, name="list"),
    path("reviews/<int:pk>/", views.review_detail, name="detail"),
    path("cycles/", views.cycle_list, name="cycle_list"),
    path("cycles/new/", views.cycle_edit, name="cycle_create"),
    path("cycles/<int:pk>/", views.cycle_detail, name="cycle_detail"),
    path("cycles/<int:pk>/edit/", views.cycle_edit, name="cycle_edit"),
    path("cycles/<int:pk>/open/", views.cycle_open, name="cycle_open"),
    path("cycles/<int:pk>/close/", views.cycle_close, name="cycle_close"),
    path("cycles/<int:pk>/generate/", views.cycle_generate_reviews, name="cycle_generate"),
    path("competencies/", views.competency_list, name="competency_list"),
    path("competencies/new/", views.competency_edit, name="competency_create"),
    path("competencies/<int:pk>/edit/", views.competency_edit, name="competency_edit"),
]
