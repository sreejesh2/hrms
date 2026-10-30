"""Auto breadcrumb + back-link resolution from the current URL name."""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse

# Root crumb for each URL namespace (after Home).
NAMESPACE_HOME: dict[str, tuple[str, str]] = {
    "core": ("Dashboard", "core:dashboard"),
    "people": ("People", "people:employee_list"),
    "payroll": ("Payroll", "payroll:home"),
    "reports": ("Reports", "reports:home"),
    "leave": ("Leave", "leave:list"),
    "expenses": ("Reimbursements", "expenses:list"),
    "loans": ("Salary advances", "loans:list"),
    "performance": ("Performance", "performance:list"),
    "attendance": ("Time settings", "attendance:calendar_list"),
    "attendance_ops": ("Attendance", "attendance_ops:daily_list"),
    "setup": ("Settings", "setup:home"),
    "accounts": ("My profile", "accounts:profile"),
    "notifications": ("Notifications", "notifications:inbox"),
    "audit": ("Activity log", "audit:log_list"),
    "docs": ("Documentation", "docs:home"),
}

# Explicit trails: list of (label, url_name|None). None = current page (no link).
# Optional "back" url_name — defaults to previous crumb with a url_name.
# Crumb url_names may reuse current resolver kwargs (pk, etc.).
PAGE_TRAILS: dict[str, dict] = {
    "core:dashboard": {
        "crumbs": [("Dashboard", None)],
        "back": None,
    },
    # —— People ——
    "people:employee_list": {
        "crumbs": [("People", None)],
        "back": "core:dashboard",
    },
    "people:active_list": {
        "crumbs": [("People", "people:employee_list"), ("Active", None)],
        "back": "people:employee_list",
    },
    "people:vacation_list": {
        "crumbs": [("People", "people:employee_list"), ("On leave", None)],
        "back": "people:employee_list",
    },
    "people:onboarding_list": {
        "crumbs": [("People", "people:employee_list"), ("Onboarding", None)],
        "back": "people:employee_list",
    },
    "people:employee_import": {
        "crumbs": [("People", "people:employee_list"), ("Import employees", None)],
        "back": "people:employee_list",
    },
    "people:employee_create": {
        "crumbs": [("People", "people:employee_list"), ("New employee", None)],
        "back": "people:employee_list",
    },
    "people:employee_detail": {
        "crumbs": [("People", "people:employee_list"), ("Employee", None)],
        "back": "people:employee_list",
    },
    "people:employee_edit": {
        "crumbs": [
            ("People", "people:employee_list"),
            ("Employee", "people:employee_detail"),
            ("Edit", None),
        ],
        "back": "people:employee_detail",
    },
    "people:employee_login": {
        "crumbs": [
            ("People", "people:employee_list"),
            ("Employee", "people:employee_detail"),
            ("Login access", None),
        ],
        "back": "people:employee_detail",
    },
    # —— Payroll ——
    "payroll:home": {
        "crumbs": [("Payroll", None)],
        "back": "core:dashboard",
    },
    "reports:home": {
        "crumbs": [("Reports", None)],
        "back": "core:dashboard",
    },
    "reports:run": {
        "crumbs": [("Reports", "reports:home"), ("Run report", None)],
        "back": "reports:home",
    },
    "payroll:component_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Components", None)],
        "back": "payroll:home",
    },
    "payroll:component_create": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Components", "payroll:component_list"),
            ("New", None),
        ],
        "back": "payroll:component_list",
    },
    "payroll:component_edit": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Components", "payroll:component_list"),
            ("Edit", None),
        ],
        "back": "payroll:component_list",
    },
    "payroll:template_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Templates", None)],
        "back": "payroll:home",
    },
    "payroll:template_create": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Templates", "payroll:template_list"),
            ("New", None),
        ],
        "back": "payroll:template_list",
    },
    "payroll:template_edit": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Templates", "payroll:template_list"),
            ("Edit", None),
        ],
        "back": "payroll:template_list",
    },
    "payroll:structure_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Structures", None)],
        "back": "payroll:home",
    },
    "payroll:structure_create": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Structures", "payroll:structure_list"),
            ("New", None),
        ],
        "back": "payroll:structure_list",
    },
    "payroll:structure_detail": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Structures", "payroll:structure_list"),
            ("Structure", None),
        ],
        "back": "payroll:structure_list",
    },
    "payroll:structure_edit": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Structures", "payroll:structure_list"),
            ("Structure", "payroll:structure_detail"),
            ("Edit", None),
        ],
        "back": "payroll:structure_detail",
    },
    "payroll:apply_template": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Structures", "payroll:structure_list"),
            ("Apply template", None),
        ],
        "back": "payroll:structure_list",
    },
    "payroll:period_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Periods", None)],
        "back": "payroll:home",
    },
    "payroll:period_create": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Periods", "payroll:period_list"),
            ("New", None),
        ],
        "back": "payroll:period_list",
    },
    "payroll:period_detail": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Periods", "payroll:period_list"),
            ("Period", None),
        ],
        "back": "payroll:period_list",
    },
    "payroll:payslip_detail": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Periods", "payroll:period_list"),
            ("Payslip", None),
        ],
        "back": "payroll:period_list",
    },
    "payroll:payslip_template_edit": {
        "crumbs": [("Payroll", "payroll:home"), ("Payslip template", None)],
        "back": "payroll:home",
    },
    "payroll:statutory_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Statutory & deductions", None)],
        "back": "payroll:home",
    },
    "payroll:statutory_create": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Statutory & deductions", "payroll:statutory_list"),
            ("New", None),
        ],
        "back": "payroll:statutory_list",
    },
    "payroll:statutory_edit": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Statutory & deductions", "payroll:statutory_list"),
            ("Edit", None),
        ],
        "back": "payroll:statutory_list",
    },
    "payroll:incentive_plan_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Incentive plans", None)],
        "back": "payroll:home",
    },
    "payroll:incentive_plan_create": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Incentive plans", "payroll:incentive_plan_list"),
            ("New", None),
        ],
        "back": "payroll:incentive_plan_list",
    },
    "payroll:incentive_plan_edit": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Incentive plans", "payroll:incentive_plan_list"),
            ("Edit", None),
        ],
        "back": "payroll:incentive_plan_list",
    },
    "payroll:incentive_award_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Incentive awards", None)],
        "back": "payroll:home",
    },
    "payroll:incentive_award_create": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Incentive awards", "payroll:incentive_award_list"),
            ("New", None),
        ],
        "back": "payroll:incentive_award_list",
    },
    "payroll:incentive_award_edit": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Incentive awards", "payroll:incentive_award_list"),
            ("Edit", None),
        ],
        "back": "payroll:incentive_award_list",
    },
    "payroll:incentive_award_import": {
        "crumbs": [
            ("Payroll", "payroll:home"),
            ("Incentive awards", "payroll:incentive_award_list"),
            ("Import", None),
        ],
        "back": "payroll:incentive_award_list",
    },
    "payroll:gratuity_list": {
        "crumbs": [("Payroll", "payroll:home"), ("Gratuity estimates", None)],
        "back": "payroll:home",
    },
    # —— Leave ——
    "leave:list": {
        "crumbs": [("Leave", None)],
        "back": "core:dashboard",
    },
    "expenses:list": {
        "crumbs": [("Reimbursements", None)],
        "back": "core:dashboard",
    },
    "expenses:create": {
        "crumbs": [("Reimbursements", "expenses:list"), ("Submit claim", None)],
        "back": "expenses:list",
    },
    "expenses:detail": {
        "crumbs": [("Reimbursements", "expenses:list"), ("Claim", None)],
        "back": "expenses:list",
    },
    "expenses:category_list": {
        "crumbs": [("Reimbursements", "expenses:list"), ("Categories", None)],
        "back": "expenses:list",
    },
    "loans:list": {
        "crumbs": [("Salary advances", None)],
        "back": "core:dashboard",
    },
    "loans:create": {
        "crumbs": [("Salary advances", "loans:list"), ("Request", None)],
        "back": "loans:list",
    },
    "loans:detail": {
        "crumbs": [("Salary advances", "loans:list"), ("Advance", None)],
        "back": "loans:list",
    },
    "expenses:category_create": {
        "crumbs": [
            ("Reimbursements", "expenses:list"),
            ("Categories", "expenses:category_list"),
            ("New", None),
        ],
        "back": "expenses:category_list",
    },
    "expenses:category_edit": {
        "crumbs": [
            ("Reimbursements", "expenses:list"),
            ("Categories", "expenses:category_list"),
            ("Edit", None),
        ],
        "back": "expenses:category_list",
    },
    # —— Performance ——
    "performance:list": {
        "crumbs": [("Performance", None)],
        "back": "core:dashboard",
    },
    "performance:detail": {
        "crumbs": [("Performance", "performance:list"), ("Review", None)],
        "back": "performance:list",
    },
    "performance:cycle_list": {
        "crumbs": [("Performance", "performance:list"), ("Cycles", None)],
        "back": "performance:list",
    },
    "performance:cycle_create": {
        "crumbs": [
            ("Performance", "performance:list"),
            ("Cycles", "performance:cycle_list"),
            ("New", None),
        ],
        "back": "performance:cycle_list",
    },
    "performance:cycle_detail": {
        "crumbs": [
            ("Performance", "performance:list"),
            ("Cycles", "performance:cycle_list"),
            ("Cycle", None),
        ],
        "back": "performance:cycle_list",
    },
    "performance:cycle_edit": {
        "crumbs": [
            ("Performance", "performance:list"),
            ("Cycles", "performance:cycle_list"),
            ("Edit", None),
        ],
        "back": "performance:cycle_list",
    },
    "performance:competency_list": {
        "crumbs": [("Performance", "performance:list"), ("Competencies", None)],
        "back": "performance:list",
    },
    "performance:competency_create": {
        "crumbs": [
            ("Performance", "performance:list"),
            ("Competencies", "performance:competency_list"),
            ("New", None),
        ],
        "back": "performance:competency_list",
    },
    "performance:competency_edit": {
        "crumbs": [
            ("Performance", "performance:list"),
            ("Competencies", "performance:competency_list"),
            ("Edit", None),
        ],
        "back": "performance:competency_list",
    },
    "leave:create": {
        "crumbs": [("Leave", "leave:list"), ("Apply", None)],
        "back": "leave:list",
    },
    "leave:detail": {
        "crumbs": [("Leave", "leave:list"), ("Request", None)],
        "back": "leave:list",
    },
    "leave:type_list": {
        "crumbs": [("Leave", "leave:list"), ("Types", None)],
        "back": "leave:list",
    },
    "leave:type_create": {
        "crumbs": [
            ("Leave", "leave:list"),
            ("Types", "leave:type_list"),
            ("New", None),
        ],
        "back": "leave:type_list",
    },
    "leave:type_edit": {
        "crumbs": [
            ("Leave", "leave:list"),
            ("Types", "leave:type_list"),
            ("Edit", None),
        ],
        "back": "leave:type_list",
    },
    "leave:balance_list": {
        "crumbs": [("Leave", "leave:list"), ("Balances", None)],
        "back": "leave:list",
    },
    "leave:balance_create": {
        "crumbs": [
            ("Leave", "leave:list"),
            ("Balances", "leave:balance_list"),
            ("New", None),
        ],
        "back": "leave:balance_list",
    },
    "leave:balance_edit": {
        "crumbs": [
            ("Leave", "leave:list"),
            ("Balances", "leave:balance_list"),
            ("Edit", None),
        ],
        "back": "leave:balance_list",
    },
    # —— Attendance ops ——
    "attendance_ops:daily_list": {
        "crumbs": [("Attendance", None)],
        "back": "core:dashboard",
    },
    "attendance_ops:daily_detail": {
        "crumbs": [("Attendance", "attendance_ops:daily_list"), ("Day", None)],
        "back": "attendance_ops:daily_list",
    },
    "attendance_ops:punch_list": {
        "crumbs": [("Attendance", "attendance_ops:daily_list"), ("Punches", None)],
        "back": "attendance_ops:daily_list",
    },
    "attendance_ops:punch_create": {
        "crumbs": [
            ("Attendance", "attendance_ops:daily_list"),
            ("Punches", "attendance_ops:punch_list"),
            ("New", None),
        ],
        "back": "attendance_ops:punch_list",
    },
    "attendance_ops:punch_import": {
        "crumbs": [
            ("Attendance", "attendance_ops:daily_list"),
            ("Punches", "attendance_ops:punch_list"),
            ("Import", None),
        ],
        "back": "attendance_ops:punch_list",
    },
    "attendance_ops:register_month": {
        "crumbs": [("Attendance", "attendance_ops:daily_list"), ("Monthly register", None)],
        "back": "attendance_ops:daily_list",
    },
    "attendance_ops:register_day": {
        "crumbs": [
            ("Attendance", "attendance_ops:daily_list"),
            ("Monthly register", "attendance_ops:register_month"),
            ("Day", None),
        ],
        "back": "attendance_ops:register_month",
    },
    "attendance_ops:regularization_list": {
        "crumbs": [("Attendance", "attendance_ops:daily_list"), ("Corrections", None)],
        "back": "attendance_ops:daily_list",
    },
    "attendance_ops:regularization_create": {
        "crumbs": [
            ("Attendance", "attendance_ops:daily_list"),
            ("Corrections", "attendance_ops:regularization_list"),
            ("New", None),
        ],
        "back": "attendance_ops:regularization_list",
    },
    "attendance_ops:regularization_detail": {
        "crumbs": [
            ("Attendance", "attendance_ops:daily_list"),
            ("Corrections", "attendance_ops:regularization_list"),
            ("Request", None),
        ],
        "back": "attendance_ops:regularization_list",
    },
    # —— Time settings ——
    "attendance:calendar_list": {
        "crumbs": [("Settings", "setup:home"), ("Work calendars", None)],
        "back": "setup:home",
    },
    "attendance:calendar_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Work calendars", "attendance:calendar_list"),
            ("New", None),
        ],
        "back": "attendance:calendar_list",
    },
    "attendance:calendar_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Work calendars", "attendance:calendar_list"),
            ("Edit", None),
        ],
        "back": "attendance:calendar_list",
    },
    "attendance:holiday_list": {
        "crumbs": [("Settings", "setup:home"), ("Holidays", None)],
        "back": "setup:home",
    },
    "attendance:holiday_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Holidays", "attendance:holiday_list"),
            ("New", None),
        ],
        "back": "attendance:holiday_list",
    },
    "attendance:holiday_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Holidays", "attendance:holiday_list"),
            ("Edit", None),
        ],
        "back": "attendance:holiday_list",
    },
    "attendance:shift_list": {
        "crumbs": [("Settings", "setup:home"), ("Shifts", None)],
        "back": "setup:home",
    },
    "attendance:shift_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Shifts", "attendance:shift_list"),
            ("New", None),
        ],
        "back": "attendance:shift_list",
    },
    "attendance:shift_detail": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Shifts", "attendance:shift_list"),
            ("Shift", None),
        ],
        "back": "attendance:shift_list",
    },
    "attendance:shift_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Shifts", "attendance:shift_list"),
            ("Shift", "attendance:shift_detail"),
            ("Edit", None),
        ],
        "back": "attendance:shift_detail",
    },
    "attendance:shift_version_add": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Shifts", "attendance:shift_list"),
            ("Shift", "attendance:shift_detail"),
            ("New version", None),
        ],
        "back": "attendance:shift_detail",
    },
    "attendance:ot_policy_list": {
        "crumbs": [("Settings", "setup:home"), ("Overtime policies", None)],
        "back": "setup:home",
    },
    "attendance:ot_policy_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Overtime policies", "attendance:ot_policy_list"),
            ("New", None),
        ],
        "back": "attendance:ot_policy_list",
    },
    "attendance:ot_policy_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Overtime policies", "attendance:ot_policy_list"),
            ("Edit", None),
        ],
        "back": "attendance:ot_policy_list",
    },
    "attendance:assignment_list": {
        "crumbs": [("Settings", "setup:home"), ("Assignments", None)],
        "back": "setup:home",
    },
    "attendance:assignment_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Assignments", "attendance:assignment_list"),
            ("New", None),
        ],
        "back": "attendance:assignment_list",
    },
    "attendance:assignment_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Assignments", "attendance:assignment_list"),
            ("Edit", None),
        ],
        "back": "attendance:assignment_list",
    },
    "attendance:assignment_bulk": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Assignments", "attendance:assignment_list"),
            ("Bulk", None),
        ],
        "back": "attendance:assignment_list",
    },
    "attendance:assignment_import": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Assignments", "attendance:assignment_list"),
            ("Import", None),
        ],
        "back": "attendance:assignment_list",
    },
    "attendance:assignment_apply_defaults": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Assignments", "attendance:assignment_list"),
            ("Apply defaults", None),
        ],
        "back": "attendance:assignment_list",
    },
    "attendance:device_list": {
        "crumbs": [("Settings", "setup:home"), ("Devices", None)],
        "back": "setup:home",
    },
    "attendance:device_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Devices", "attendance:device_list"),
            ("New", None),
        ],
        "back": "attendance:device_list",
    },
    "attendance:device_detail": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Devices", "attendance:device_list"),
            ("Device", None),
        ],
        "back": "attendance:device_list",
    },
    "attendance:device_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Devices", "attendance:device_list"),
            ("Device", "attendance:device_detail"),
            ("Edit", None),
        ],
        "back": "attendance:device_detail",
    },
    "attendance:device_sync_time": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Devices", "attendance:device_list"),
            ("Device", "attendance:device_detail"),
        ],
        "back": "attendance:device_detail",
    },
    "attendance:device_resend_punches": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Devices", "attendance:device_list"),
            ("Device", "attendance:device_detail"),
        ],
        "back": "attendance:device_detail",
    },
    "attendance:device_check": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Devices", "attendance:device_list"),
            ("Device", "attendance:device_detail"),
        ],
        "back": "attendance:device_detail",
    },
    # —— Setup ——
    "setup:home": {
        "crumbs": [("Settings", None)],
        "back": "core:dashboard",
    },
    "audit:log_list": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Activity log", None),
        ],
        "back": "setup:home",
    },
    "audit:log_detail": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Activity log", "audit:log_list"),
            ("Detail", None),
        ],
        "back": "audit:log_list",
    },
    "docs:home": {
        "crumbs": [("Documentation", None)],
        "back": "core:dashboard",
    },
    "docs:module": {
        "crumbs": [
            ("Documentation", "docs:home"),
            ("Module", None),
        ],
        "back": "docs:home",
    },
    "setup:organization_settings": {
        "crumbs": [("Settings", "setup:home"), ("Company", None)],
        "back": "setup:home",
    },
    "setup:employee_fields": {
        "crumbs": [("Settings", "setup:home"), ("Custom fields", None)],
        "back": "setup:home",
    },
    "setup:employee_field_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Custom fields", "setup:employee_fields"),
            ("New", None),
        ],
        "back": "setup:employee_fields",
    },
    "setup:employee_field_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Custom fields", "setup:employee_fields"),
            ("Edit", None),
        ],
        "back": "setup:employee_fields",
    },
    "setup:master_list": {
        "crumbs": [("Settings", "setup:home"), ("Organization", None)],
        "back": "setup:home",
    },
    "setup:master_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Organization", "setup:master_list"),
            ("New", None),
        ],
        "back": "setup:master_list",
    },
    "setup:master_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Organization", "setup:master_list"),
            ("Edit", None),
        ],
        "back": "setup:master_list",
    },
    "setup:role_list": {
        "crumbs": [("Settings", "setup:home"), ("Roles", None)],
        "back": "setup:home",
    },
    "setup:role_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Roles", "setup:role_list"),
            ("New", None),
        ],
        "back": "setup:role_list",
    },
    "setup:role_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Roles", "setup:role_list"),
            ("Edit", None),
        ],
        "back": "setup:role_list",
    },
    "setup:permission_list": {
        "crumbs": [("Settings", "setup:home"), ("Permissions", None)],
        "back": "setup:home",
    },
    "setup:permission_create": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Permissions", "setup:permission_list"),
            ("New", None),
        ],
        "back": "setup:permission_list",
    },
    "setup:permission_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("Permissions", "setup:permission_list"),
            ("Edit", None),
        ],
        "back": "setup:permission_list",
    },
    "setup:backup_list": {
        "crumbs": [("Settings", "setup:home"), ("Backups", None)],
        "back": "setup:home",
    },
    "setup:user_role_list": {
        "crumbs": [("Settings", "setup:home"), ("User roles", None)],
        "back": "setup:home",
    },
    "setup:user_role_edit": {
        "crumbs": [
            ("Settings", "setup:home"),
            ("User roles", "setup:user_role_list"),
            ("Edit", None),
        ],
        "back": "setup:user_role_list",
    },
    # —— Account / notifications ——
    "accounts:profile": {
        "crumbs": [("My profile", None)],
        "back": "core:dashboard",
    },
    "notifications:inbox": {
        "crumbs": [("Notifications", None)],
        "back": "core:dashboard",
    },
}


def _safe_reverse(url_name: str | None, kwargs: dict | None = None) -> str | None:
    if not url_name:
        return None
    kwargs = kwargs or {}
    try:
        return reverse(url_name, kwargs=kwargs)
    except NoReverseMatch:
        pass
    # Retry with only pk if present
    if "pk" in kwargs:
        try:
            return reverse(url_name, kwargs={"pk": kwargs["pk"]})
        except NoReverseMatch:
            pass
    # Retry with master_key for setup masters
    if "master_key" in kwargs:
        try:
            return reverse(url_name, kwargs={"master_key": kwargs["master_key"]})
        except NoReverseMatch:
            pass
        if "pk" in kwargs:
            try:
                return reverse(
                    url_name,
                    kwargs={"master_key": kwargs["master_key"], "pk": kwargs["pk"]},
                )
            except NoReverseMatch:
                pass
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def _fallback_trail(view_name: str) -> dict:
    ns = view_name.split(":")[0] if ":" in view_name else ""
    crumbs: list[tuple[str, str | None]] = [("Home", "core:dashboard")]
    if ns in NAMESPACE_HOME:
        label, url = NAMESPACE_HOME[ns]
        if view_name != url:
            crumbs.append((label, url))
    action = view_name.split(":")[-1].replace("_", " ").title()
    crumbs.append((action, None))
    back = crumbs[-2][1] if len(crumbs) >= 2 else "core:dashboard"
    return {"crumbs": crumbs, "back": back}


def resolve_page_nav(view_name: str, kwargs: dict | None = None, page_title: str = ""):
    """
    Returns:
      crumbs: [{label, url|None}, ...]
      back_url: str|None
    """
    kwargs = dict(kwargs or {})
    spec = PAGE_TRAILS.get(view_name) or _fallback_trail(view_name)
    raw_crumbs = list(spec.get("crumbs") or [])

    # Prefill Home when trail doesn't start with it (except dashboard)
    if view_name != "core:dashboard":
        if not raw_crumbs or raw_crumbs[0][1] != "core:dashboard":
            if raw_crumbs and raw_crumbs[0][0] != "Home":
                raw_crumbs = [("Home", "core:dashboard"), *raw_crumbs]

    crumbs = []
    for label, url_name in raw_crumbs:
        url = _safe_reverse(url_name, kwargs) if url_name else None
        crumbs.append({"label": label, "url": url})

    if "back" in spec:
        back_name = spec.get("back")
        back_url = _safe_reverse(back_name, kwargs) if back_name else None
    else:
        back_url = None
        for item in reversed(crumbs[:-1]):
            if item["url"]:
                back_url = item["url"]
                break
        if not back_url:
            back_url = _safe_reverse("core:dashboard")

    return {"crumbs": crumbs, "back_url": back_url}
