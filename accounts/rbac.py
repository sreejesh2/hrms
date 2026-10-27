"""Default permission catalog + starter roles (idempotent)."""

DEFAULT_PERMISSIONS = [
    # Core
    ("core", "core.view_dashboard", "View dashboard", "Access the main dashboard"),
    # People
    ("people", "people.view_employees", "View employees", "List and view employee profiles"),
    ("people", "people.manage_employees", "Manage employees", "Create/edit employee records"),
    ("people", "people.view_onboarding", "View onboarding", "See onboarding queue"),
    # Organization masters
    ("masters", "masters.view_departments", "View departments", ""),
    ("masters", "masters.manage_departments", "Manage departments", "Create/edit/delete departments"),
    ("masters", "masters.view_divisions", "View divisions", ""),
    ("masters", "masters.manage_divisions", "Manage divisions", "Create/edit/delete divisions"),
    ("masters", "masters.view_locations", "View locations", ""),
    ("masters", "masters.manage_locations", "Manage locations", "Create/edit/delete locations"),
    ("masters", "masters.view_positions", "View positions", ""),
    ("masters", "masters.manage_positions", "Manage positions", "Create/edit/delete positions"),
    ("masters", "masters.view_banks", "View banks", ""),
    ("masters", "masters.manage_banks", "Manage banks", "Create/edit/delete banks"),
    # Setup / Employee settings
    (
        "setup",
        "setup.manage_company",
        "Manage company settings",
        "Company name, country, and default currency (e.g. AED)",
    ),
    (
        "setup",
        "setup.manage_employee_fields",
        "Manage employee custom fields",
        "Create and edit dynamic employee attributes",
    ),
    (
        "setup",
        "setup.manage_backups",
        "Manage backups",
        "Create and download full backups (contain all personal and salary data)",
    ),
    # Access control
    ("access", "access.manage_roles", "Manage roles", "Create roles and assign permissions"),
    ("access", "access.manage_permissions", "Manage permissions", "Add/edit permission catalog"),
    ("access", "access.assign_user_roles", "Assign user roles", "Attach roles to users"),
    # Attendance & time settings
    ("attendance", "attendance.view", "View attendance", ""),
    ("attendance", "attendance.manage", "Manage attendance", ""),
    (
        "attendance",
        "attendance.manage_calendars",
        "Manage work calendars",
        "Create/edit work calendars under Time settings",
    ),
    (
        "attendance",
        "attendance.manage_shifts",
        "Manage work shifts",
        "Shift master, versions, and employee shift assignments",
    ),
    (
        "attendance",
        "attendance.manage_devices",
        "Manage punch devices",
        "Register biometric / card machines and API tokens",
    ),
    (
        "attendance",
        "attendance.request_regularization",
        "Request attendance regularization",
        "Submit a day correction for approval",
    ),
    (
        "attendance",
        "attendance.approve_regularization",
        "Approve attendance regularization",
        "Approve or reject attendance correction requests",
    ),
    ("leave", "leave.view", "View leave", ""),
    ("leave", "leave.manage", "Manage leave", "Leave types, balances, and full approval access"),
    (
        "leave",
        "leave.request",
        "Request leave",
        "Apply for leave for yourself",
    ),
    (
        "leave",
        "leave.approve",
        "Approve leave",
        "Approve or reject team leave requests",
    ),
    ("payroll", "payroll.view", "View payroll", ""),
    ("payroll", "payroll.manage", "Manage payroll", ""),
    ("performance", "performance.view", "View performance", ""),
    ("performance", "performance.manage", "Manage performance", ""),
    ("expenses", "expenses.view", "View reimbursements", ""),
    ("expenses", "expenses.request", "Submit reimbursement claims", ""),
    ("expenses", "expenses.approve", "Approve reimbursement claims", ""),
    ("expenses", "expenses.manage", "Manage reimbursements", "Categories, all claims, and mark paid"),
    ("expenses", "expenses.pay", "Mark reimbursements paid", "Finance payout / bank transfer"),
    ("loans", "loans.view", "View salary advances", ""),
    ("loans", "loans.request", "Request salary advance", ""),
    ("loans", "loans.approve", "Approve salary advances", ""),
    ("loans", "loans.manage", "Manage salary advances", "All advances and recovery overview"),
    ("loans", "loans.disburse", "Disburse salary advances", "Mark approved advances as paid out"),
    ("reports", "reports.view", "View reports", ""),
    (
        "audit",
        "audit.view",
        "View activity log",
        "See who created, updated, approved, or signed in — with search and filters",
    ),
]

MASTER_PERMS = [
    "masters.view_departments",
    "masters.manage_departments",
    "masters.view_divisions",
    "masters.manage_divisions",
    "masters.view_locations",
    "masters.manage_locations",
    "masters.view_positions",
    "masters.manage_positions",
    "masters.view_banks",
    "masters.manage_banks",
]

DEFAULT_ROLES = {
    "Admin": {
        "description": "Full system access",
        "permissions": "*",
    },
    "HR": {
        "description": "People operations",
        "permissions": [
            "core.view_dashboard",
            "people.view_employees",
            "people.manage_employees",
            "people.view_onboarding",
            "setup.manage_company",
            "setup.manage_employee_fields",
            *MASTER_PERMS,
            "leave.view",
            "leave.manage",
            "leave.request",
            "leave.approve",
            "payroll.view",
            "payroll.manage",
            "attendance.view",
            "attendance.manage",
            "attendance.manage_calendars",
            "attendance.manage_shifts",
            "attendance.manage_devices",
            "attendance.request_regularization",
            "attendance.approve_regularization",
            "reports.view",
            "expenses.view",
            "expenses.request",
            "expenses.approve",
            "expenses.manage",
            "expenses.pay",
            "loans.view",
            "loans.request",
            "loans.approve",
            "loans.manage",
            "loans.disburse",
            "performance.view",
            "performance.manage",
            "audit.view",
        ],
    },
    "Manager": {
        "description": "Team lead access",
        "permissions": [
            "core.view_dashboard",
            "people.view_employees",
            "masters.view_departments",
            "masters.view_divisions",
            "masters.view_locations",
            "masters.view_positions",
            "leave.view",
            "leave.request",
            "leave.approve",
            "attendance.view",
            "attendance.request_regularization",
            "attendance.approve_regularization",
            "expenses.view",
            "expenses.request",
            "expenses.approve",
            "loans.view",
            "loans.request",
            "loans.approve",
            "performance.view",
        ],
    },
    "Payroll": {
        "description": "Payroll processing",
        "permissions": [
            "core.view_dashboard",
            "people.view_employees",
            "masters.view_banks",
            "payroll.view",
            "payroll.manage",
            "reports.view",
            "expenses.view",
            "expenses.manage",
            "expenses.pay",
            "loans.view",
            "loans.manage",
            "loans.disburse",
        ],
    },
    "Employee": {
        "description": "Self-service basics",
        "permissions": [
            "core.view_dashboard",
            "attendance.request_regularization",
            "leave.view",
            "leave.request",
            "expenses.view",
            "expenses.request",
            "loans.view",
            "loans.request",
            "performance.view",
        ],
    },
}


def seed_rbac():
    from accounts.models import AppPermission, Role

    perm_map = {}
    for module, codename, name, description in DEFAULT_PERMISSIONS:
        obj, _ = AppPermission.objects.update_or_create(
            codename=codename,
            defaults={
                "module": module,
                "name": name,
                "description": description,
                "is_active": True,
            },
        )
        perm_map[codename] = obj

    all_perms = list(AppPermission.objects.filter(is_active=True))

    for role_name, cfg in DEFAULT_ROLES.items():
        role, created = Role.objects.get_or_create(
            name=role_name,
            defaults={"description": cfg["description"], "is_active": True},
        )
        if cfg["permissions"] == "*":
            # Admin always tracks full catalog (including newly added perms)
            role.permissions.set(all_perms)
            continue
        if created or not role.permissions.exists():
            role.permissions.set(
                [perm_map[c] for c in cfg["permissions"] if c in perm_map]
            )
        else:
            # Add any newly introduced default perms without removing custom ones
            for c in cfg["permissions"]:
                if c in perm_map:
                    role.permissions.add(perm_map[c])
