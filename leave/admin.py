from django.contrib import admin

from . import models

admin.site.register(models.LeaveType)
admin.site.register(models.LeaveBalance)
admin.site.register(models.LeaveRequest)
