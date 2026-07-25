from django.urls import path

from . import views

app_name = "docs"

urlpatterns = [
    path("", views.docs_home, name="home"),
    path("<slug:slug>/", views.docs_module, name="module"),
]
