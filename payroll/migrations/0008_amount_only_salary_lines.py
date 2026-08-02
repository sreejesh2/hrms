from django.db import migrations


def normalize_amount_only_salary_lines(apps, schema_editor):
    SalaryComponent = apps.get_model("payroll", "SalaryComponent")
    SalaryStructureLine = apps.get_model("payroll", "SalaryStructureLine")
    SalaryTemplateLine = apps.get_model("payroll", "SalaryTemplateLine")

    SalaryComponent.objects.filter(code__in=["HRA", "PF_EE"]).update(
        calc_method="fixed",
        default_percent=None,
    )
    SalaryStructureLine.objects.update(percent=None)
    SalaryTemplateLine.objects.update(percent=None)


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0007_salarycomponent_prorate_payslip_totals"),
    ]

    operations = [
        migrations.RunPython(
            normalize_amount_only_salary_lines,
            migrations.RunPython.noop,
        ),
    ]
