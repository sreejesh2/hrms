from django.urls import path

from . import zkteco_views

# Mounted at /iclock/ — ZKTeco ADMS / Push protocol (iFace990, etc.)
urlpatterns = [
    path("cdata", zkteco_views.iclock_cdata, name="iclock_cdata"),
    path("getrequest", zkteco_views.iclock_getrequest, name="iclock_getrequest"),
    path("devicecmd", zkteco_views.iclock_devicecmd, name="iclock_devicecmd"),
    path("registry", zkteco_views.iclock_registry, name="iclock_registry"),
]
