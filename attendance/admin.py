from django.contrib import admin

from . import models

admin.site.register(models.WorkCalendar)
admin.site.register(models.WorkShift)
admin.site.register(models.WorkShiftVersion)
admin.site.register(models.OvertimePolicy)
admin.site.register(models.LatePenaltyPolicy)
admin.site.register(models.LatePenaltyTier)
admin.site.register(models.ShiftAssignment)
admin.site.register(models.Holiday)
admin.site.register(models.PunchDevice)
admin.site.register(models.DeviceCommand)
admin.site.register(models.DeviceBioTemplate)
admin.site.register(models.PunchLog)
admin.site.register(models.DailyAttendance)
admin.site.register(models.AttendanceRegularization)
