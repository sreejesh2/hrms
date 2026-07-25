from django.urls import path

from reports import views

app_name = "reports"

urlpatterns = [
    path("", views.home, name="home"),
    path("<slug:slug>/", views.run_report, name="run"),
]
