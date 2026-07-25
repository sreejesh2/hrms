from django.urls import path

from . import device_api

app_name = "attendance_api"

urlpatterns = [
    path("punches/", device_api.device_punch_ingest, name="device_punch_ingest"),
]
