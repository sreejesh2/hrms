from django.contrib import admin

from . import models

admin.site.register(models.Department)
admin.site.register(models.Division)
admin.site.register(models.Location)
admin.site.register(models.Position)
admin.site.register(models.Bank)
admin.site.register(models.Employee)
admin.site.register(models.EmployeeDocument)
admin.site.register(models.OnboardingChecklist)
admin.site.register(models.EmployeeAttributeDefinition)
admin.site.register(models.EmployeeAttributeValue)
