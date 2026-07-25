from django.contrib import admin

from . import models

admin.site.register(models.SalaryComponent)
admin.site.register(models.SalaryTemplate)
admin.site.register(models.SalaryTemplateLine)
admin.site.register(models.SalaryStructure)
admin.site.register(models.SalaryStructureLine)
admin.site.register(models.IncentivePlan)
admin.site.register(models.IncentiveAward)
