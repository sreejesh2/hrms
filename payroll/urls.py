from django.urls import path

from . import views

app_name = "payroll"

urlpatterns = [
    path("", views.payroll_home, name="home"),
    path("components/", views.component_list, name="component_list"),
    path("components/new/", views.component_edit, name="component_create"),
    path("components/<int:pk>/", views.component_edit, name="component_edit"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_edit, name="template_create"),
    path("templates/<int:pk>/", views.template_edit, name="template_edit"),
    path("structures/", views.structure_list, name="structure_list"),
    path("structures/new/", views.structure_create, name="structure_create"),
    path("structures/apply-template/", views.structure_apply_template, name="apply_template"),
    path("structures/<int:pk>/", views.structure_detail, name="structure_detail"),
    path("structures/<int:pk>/edit/", views.structure_edit, name="structure_edit"),
    path("periods/", views.period_list, name="period_list"),
    path("periods/new/", views.period_create, name="period_create"),
    path("periods/<int:pk>/", views.period_detail, name="period_detail"),
    path("periods/<int:pk>/run/", views.period_run, name="period_run"),
    path("periods/<int:pk>/lock/", views.period_lock, name="period_lock"),
    path("payslips/<int:pk>/", views.payslip_detail, name="payslip_detail"),
    path("payslips/<int:pk>/pdf/", views.payslip_pdf, name="payslip_pdf"),
    path("payslip-template/", views.payslip_template_edit, name="payslip_template_edit"),
    path(
        "payslip-template/sample.pdf",
        views.payslip_sample_pdf,
        name="payslip_sample_pdf",
    ),
    path("statutory/", views.statutory_list, name="statutory_list"),
    path("statutory/new/", views.statutory_edit, name="statutory_create"),
    path("statutory/<int:pk>/", views.statutory_edit, name="statutory_edit"),
    path("incentives/plans/", views.incentive_plan_list, name="incentive_plan_list"),
    path(
        "incentives/plans/new/",
        views.incentive_plan_edit,
        name="incentive_plan_create",
    ),
    path(
        "incentives/plans/<int:pk>/",
        views.incentive_plan_edit,
        name="incentive_plan_edit",
    ),
    path("incentives/awards/", views.incentive_award_list, name="incentive_award_list"),
    path(
        "incentives/awards/new/",
        views.incentive_award_edit,
        name="incentive_award_create",
    ),
    path(
        "incentives/awards/<int:pk>/",
        views.incentive_award_edit,
        name="incentive_award_edit",
    ),
    path(
        "incentives/awards/<int:pk>/approve/",
        views.incentive_award_approve,
        name="incentive_award_approve",
    ),
    path(
        "incentives/awards/<int:pk>/cancel/",
        views.incentive_award_cancel,
        name="incentive_award_cancel",
    ),
    path(
        "incentives/awards/import/",
        views.incentive_award_import,
        name="incentive_award_import",
    ),
    path(
        "incentives/awards/approve-selected/",
        views.incentive_award_approve_selected,
        name="incentive_award_approve_selected",
    ),
    path("gratuity/", views.gratuity_list, name="gratuity_list"),
]
