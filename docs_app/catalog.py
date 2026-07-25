"""In-app Day Pay module documentation catalog."""

from __future__ import annotations

# Each module: slug, title, summary, audience, prerequisites, workflows, screens, tips
MODULES: list[dict] = [
    {
        "slug": "getting-started",
        "title": "Getting started",
        "icon": "home",
        "summary": "How Day Pay is organized, how to sign in, and the recommended setup order.",
        "audience": "All users · Admins setting up a new company",
        "prerequisites": [
            "Day Pay is running and migrated",
            "At least one Admin user (dev: admin@example.com / admin123)",
        ],
        "workflows": [
            "Sign in with your email and password at /accounts/login/",
            "Open Dashboard for KPIs, charts, and pending approvals",
            "Admins: configure Company → org masters → Time settings → People → Payroll",
            "Use Settings → Access control → Roles to assign HR / Manager / Payroll / Employee",
            "Open this Documentation hub anytime from the sidebar",
        ],
        "screens": [
            {"label": "Dashboard", "url_name": "core:dashboard"},
            {"label": "My profile", "url_name": "accounts:profile"},
            {"label": "Company settings", "url_name": "setup:organization_settings"},
        ],
        "tips": [
            "Sidebar items respect your roles — if something is missing, ask Admin for a permission",
            "Light/dark theme toggles from the top bar",
            "Activity log records who changed what (HR/Admin)",
        ],
    },
    {
        "slug": "dashboard",
        "title": "Dashboard",
        "icon": "home",
        "summary": "Home screen with KPIs, attendance charts, leave/reimbursement queues, and quick actions based on your role.",
        "audience": "All roles with dashboard access",
        "prerequisites": [
            "Signed-in user with core.view_dashboard",
            "Richer cards need People / Attendance / Leave / Expenses data",
        ],
        "workflows": [
            "Review headcount, attendance, leave, and reimbursement snapshots",
            "Jump to pending leave or reimbursement approvals (managers/HR)",
            "Open quick links into People, Attendance, Payroll, or self-service",
        ],
        "screens": [
            {"label": "Dashboard", "url_name": "core:dashboard"},
        ],
        "tips": [
            "Charts shrink on smaller screens; data is permission-aware",
        ],
    },
    {
        "slug": "accounts",
        "title": "Accounts & profile",
        "icon": "users",
        "summary": "Email login, logout, and self-service profile (name, password, roles, quick links).",
        "audience": "Every signed-in user",
        "prerequisites": [
            "User account created (Admin/HR can provision from the employee profile)",
        ],
        "workflows": [
            "Sign in with email → Dashboard",
            "Open My profile to update name or password",
            "Use quick links to linked employee, leave, corrections, reimbursements, reviews",
            "Sign out from the top bar",
        ],
        "screens": [
            {"label": "Login", "url_name": "accounts:login"},
            {"label": "Profile", "url_name": "accounts:profile"},
        ],
        "tips": [
            "Employee portal access is created under People → employee → Create login",
            "Failed and successful sign-ins appear in the Activity log",
        ],
    },
    {
        "slug": "people",
        "title": "People (employees)",
        "icon": "users",
        "summary": "Employee roster, profiles, documents, onboarding, salary preview, login provisioning, and ZKTeco enroll.",
        "audience": "HR · Admin · Managers (view)",
        "prerequisites": [
            "Organization masters (department, location, position) recommended",
            "Biometric / device ID required before ZK enroll or punch matching",
        ],
        "workflows": [
            "List / search employees; filter Active, On vacation, Onboarding",
            "Create or edit an employee profile",
            "Upload documents; fill custom fields; update onboarding checklist",
            "Open Salary / Leave / Performance tabs on the profile",
            "Create, reset, or unlink portal login",
            "Queue Add user / Enroll face / Enroll finger on a ZKTeco device",
        ],
        "screens": [
            {"label": "All employees", "url_name": "people:employee_list"},
            {"label": "Active", "url_name": "people:active_list"},
            {"label": "Onboarding", "url_name": "people:onboarding_list"},
            {"label": "Add employee", "url_name": "people:employee_create"},
        ],
        "tips": [
            "Biometric / device ID must match the iFace PIN / AccNo",
            "Department default shift can auto-assign on create when configured",
        ],
    },
    {
        "slug": "organization",
        "title": "Organization & company",
        "icon": "gear",
        "summary": "Company profile (AED / Dubai-ready), logo, and masters: departments, divisions, locations, positions, banks.",
        "audience": "HR · Admin",
        "prerequisites": [
            "Admin or setup/masters permissions",
        ],
        "workflows": [
            "Set company name, address, TRN, logo, default currency",
            "Maintain departments (optional default shift/calendar), divisions, locations, positions",
            "Maintain banks used on employee salary profiles and bank payment reports",
            "Define custom employee attribute fields under Employee settings",
        ],
        "screens": [
            {"label": "Settings home", "url_name": "setup:home"},
            {"label": "Company", "url_name": "setup:organization_settings"},
            {"label": "Departments", "url_name": "setup:master_list", "url_kwargs": {"master_key": "departments"}},
            {"label": "Locations", "url_name": "setup:master_list", "url_kwargs": {"master_key": "locations"}},
            {"label": "Banks", "url_name": "setup:master_list", "url_kwargs": {"master_key": "banks"}},
            {"label": "Custom fields", "url_name": "setup:employee_fields"},
        ],
        "tips": [
            "Company currency and logo feed payslip PDFs and reports",
            "Bank master is for employee salary banks — not the company IBAN alone",
        ],
    },
    {
        "slug": "access-control",
        "title": "Access control (RBAC)",
        "icon": "gear",
        "summary": "Roles, permission catalog, and assigning roles to users. Controls which sidebar items and screens each person sees.",
        "audience": "Admin only (by default)",
        "prerequisites": [
            "RBAC seeded on migrate (Admin, HR, Manager, Payroll, Employee)",
        ],
        "workflows": [
            "Review default roles and their permissions",
            "Create custom roles or edit HR/Manager scopes",
            "Add permission catalog entries if you extend the product",
            "Assign one or more roles to each user under User roles",
        ],
        "screens": [
            {"label": "Roles", "url_name": "setup:role_list"},
            {"label": "Permissions", "url_name": "setup:permission_list"},
            {"label": "User roles", "url_name": "setup:user_role_list"},
            {"label": "Activity log", "url_name": "audit:log_list"},
        ],
        "tips": [
            "Superusers bypass permission checks",
            "Re-run `python manage.py seed --only rbac` after pulling new permission codenames",
        ],
    },
    {
        "slug": "attendance",
        "title": "Attendance operations",
        "icon": "clock",
        "summary": "Punches, daily attendance generation, monthly register (lock/edit), and regularization (day corrections).",
        "audience": "HR · Managers · Employees (corrections)",
        "prerequisites": [
            "Employees with shifts/calendars ideally assigned",
            "Punches from devices, import, or manual entry",
        ],
        "workflows": [
            "Review punches; create manual punches; import vendor CSV",
            "Generate daily attendance for a date; open day detail; regenerate if needed",
            "Build the monthly register; edit day status/hours; lock the month",
            "Employees submit regularization → managers/HR approve or reject",
        ],
        "screens": [
            {"label": "Punches", "url_name": "attendance_ops:punch_list"},
            {"label": "Daily attendance", "url_name": "attendance_ops:daily_list"},
            {"label": "Monthly register", "url_name": "attendance_ops:register_month"},
            {"label": "Regularization", "url_name": "attendance_ops:regularization_list"},
        ],
        "tips": [
            "Locked days are not overwritten by Generate until unlocked",
            "After approval, mark regularization as frozen so Generate keeps the correction",
        ],
    },
    {
        "slug": "time-settings",
        "title": "Time settings",
        "icon": "calendar",
        "summary": "Work calendars, holidays, shifts & versions, shift assignments, OT policies, and punch device registry.",
        "audience": "HR · Admin",
        "prerequisites": [
            "attendance.manage_calendars / manage_shifts / manage_devices as needed",
        ],
        "workflows": [
            "Define work calendars (which weekdays are working)",
            "Add holidays (global or per location)",
            "Create shifts and dated versions (times, breaks, attendance rules)",
            "Assign shifts to employees (single, bulk, CSV, or department defaults)",
            "Configure overtime policies (grace, rounding, rates)",
            "Register biometric devices and manage tokens / ZK commands",
        ],
        "screens": [
            {"label": "Calendars", "url_name": "attendance:calendar_list"},
            {"label": "Holidays", "url_name": "attendance:holiday_list"},
            {"label": "Shifts", "url_name": "attendance:shift_list"},
            {"label": "Assignments", "url_name": "attendance:assignment_list"},
            {"label": "OT policies", "url_name": "attendance:ot_policy_list"},
            {"label": "Punch devices", "url_name": "attendance:device_list"},
        ],
        "tips": [
            "Shift versions are effective-dated — keep history instead of overwriting",
            "See the ZKTeco module doc for iFace990 ADMS setup",
        ],
    },
    {
        "slug": "zkteco",
        "title": "ZKTeco devices (iFace990)",
        "icon": "clock",
        "summary": "ADMS push integration: online/offline status, local vs global connection, auto time sync, user push, and face/finger enroll triggers.",
        "audience": "HR · IT · Admin",
        "prerequisites": [
            "Device with ADMS / Cloud Server support",
            "Day Pay reachable on LAN (local) or public HTTPS (global)",
            "Employee Biometric / device ID = machine PIN",
        ],
        "workflows": [
            "Create device: Vendor = ZKTeco, set SN, Connection = Local or Global",
            "On the machine: enable ADMS, server = Day Pay host, path /iclock",
            "Watch Online/Offline on the device list (heartbeat within 3 minutes)",
            "Time syncs automatically (every ~5 min + on reconnect); or press Sync time",
            "From Devices or People: Add user / Enroll face / Enroll finger (capture on device)",
            "Punches arrive as ATTLOG → Punch log → Daily attendance",
        ],
        "screens": [
            {"label": "Punch devices", "url_name": "attendance:device_list"},
        ],
        "tips": [
            "ADMS endpoints: /iclock/cdata, /iclock/getrequest, /iclock/devicecmd",
            "HTTP JSON bridge devices use POST /api/attendance/punches/ with Bearer token",
            "Face/finger cannot be captured in the browser — only on the iFace hardware",
            "Offline devices reconnect automatically when the network returns",
        ],
    },
    {
        "slug": "leave",
        "title": "Leave",
        "icon": "calendar",
        "summary": "Leave types, balances, apply/approve/cancel requests, and year ensure for active staff.",
        "audience": "Employees · Managers · HR",
        "prerequisites": [
            "Leave types configured",
            "Balances created (or Ensure year for active employees)",
            "User linked to employee for self-service",
        ],
        "workflows": [
            "HR defines leave types and opening balances",
            "Employee (or HR) applies for leave",
            "Manager/HR approves or rejects; employee can cancel pending",
            "Ensure year creates missing balances for the selected year",
        ],
        "screens": [
            {"label": "Leave requests", "url_name": "leave:list"},
            {"label": "Apply", "url_name": "leave:create"},
            {"label": "Leave types", "url_name": "leave:type_list"},
            {"label": "Balances", "url_name": "leave:balance_list"},
        ],
        "tips": [
            "Managers typically see team requests; HR sees all when leave.manage is granted",
        ],
    },
    {
        "slug": "salary-advances",
        "title": "Salary advances",
        "icon": "wallet",
        "summary": "Request, approve, and disburse salary advances; recover installments automatically on payroll.",
        "audience": "Employees · Managers · HR · Payroll",
        "prerequisites": [
            "Employee linked to user for self-service requests",
            "Payroll periods for recovery",
        ],
        "workflows": [
            "Employee or HR requests an advance (amount + installment months)",
            "Manager/HR approves or rejects",
            "Finance/HR marks disbursed (bank/cash)",
            "Next payroll run deducts installment (ADV line); lock applies recovery",
            "Advance closes when fully recovered",
        ],
        "screens": [
            {"label": "All advances", "url_name": "loans:list"},
            {"label": "Request advance", "url_name": "loans:create"},
        ],
        "tips": [
            "Installments = number of payroll months to spread recovery",
            "Re-run payroll before lock if you need to refresh ADV amounts",
        ],
    },
    {
        "slug": "payroll",
        "title": "Payroll",
        "icon": "wallet",
        "summary": "Salary components, templates, employee structures, pay periods, payslips (PDF), statutory rules, and gratuity estimates.",
        "audience": "Payroll · HR · Admin",
        "prerequisites": [
            "Employees exist",
            "Company currency/logo for PDFs",
            "Components defined before structures/templates",
        ],
        "workflows": [
            "Define earning/deduction components",
            "Build templates → apply to employees as structures (or edit structures directly)",
            "Open a pay period → Run → review payslips → Lock",
            "Configure statutory deduction rules; review gratuity list",
            "Customize payslip PDF layout under Payslip template",
        ],
        "screens": [
            {"label": "Payroll home", "url_name": "payroll:home"},
            {"label": "Components", "url_name": "payroll:component_list"},
            {"label": "Templates", "url_name": "payroll:template_list"},
            {"label": "Structures", "url_name": "payroll:structure_list"},
            {"label": "Periods", "url_name": "payroll:period_list"},
            {"label": "Statutory", "url_name": "payroll:statutory_list"},
            {"label": "Gratuity", "url_name": "payroll:gratuity_list"},
        ],
        "tips": [
            "Lock periods after finance sign-off so they are not re-run accidentally",
            "Bank payment MIS report uses employee bank masters",
        ],
    },
    {
        "slug": "expenses",
        "title": "Reimbursements",
        "icon": "receipt",
        "summary": "Multi-line expense/reimbursement claims with receipts, approval, and mark-paid.",
        "audience": "Employees · Managers · HR / Finance",
        "prerequisites": [
            "Expense categories active",
            "User linked to employee for self-service claims",
        ],
        "workflows": [
            "Create a claim with one or more lines and optional attachments",
            "Submit → manager/HR approve or reject",
            "Finance marks approved claims as paid",
            "HR manages categories under Reimbursements → Categories",
        ],
        "screens": [
            {"label": "Claims", "url_name": "expenses:list"},
            {"label": "New claim", "url_name": "expenses:create"},
            {"label": "Categories", "url_name": "expenses:category_list"},
        ],
        "tips": [
            "UI label is Reimbursements; URL path remains /expenses/",
        ],
    },
    {
        "slug": "performance",
        "title": "Performance",
        "icon": "chart",
        "summary": "Review cycles, competencies, self-review and manager review, HR completion.",
        "audience": "HR · Managers · Employees",
        "prerequisites": [
            "Active employees with managers set",
            "Competencies defined (recommended)",
        ],
        "workflows": [
            "HR creates a cycle → Open → Generate reviews for active staff",
            "Employee submits self-assessment",
            "Manager submits manager ratings",
            "HR completes / closes the cycle",
        ],
        "screens": [
            {"label": "My reviews", "url_name": "performance:list"},
            {"label": "Cycles", "url_name": "performance:cycle_list"},
            {"label": "Competencies", "url_name": "performance:competency_list"},
        ],
        "tips": [
            "Reviews also appear on the employee Performance tab",
        ],
    },
    {
        "slug": "reports",
        "title": "Reports (MIS)",
        "icon": "file",
        "summary": "Filterable management reports with Excel and PDF export (payroll, attendance, leave, headcount, gratuity, banks).",
        "audience": "HR · Payroll · Admin",
        "prerequisites": [
            "Source data in People / Attendance / Leave / Payroll",
            "reports.view permission",
        ],
        "workflows": [
            "Open Reports home and pick a report",
            "Set filters (period, department, etc.)",
            "Preview on screen; export Excel or PDF",
        ],
        "screens": [
            {"label": "Reports home", "url_name": "reports:home"},
        ],
        "tips": [
            "Includes payroll register, payslip lines, bank payment, statutory summary, attendance month/detail, OT, leave balances/utilization, headcount, gratuity, salary structures",
        ],
    },
    {
        "slug": "notifications",
        "title": "Notifications",
        "icon": "file",
        "summary": "In-app inbox for approvals and system messages; mark as read from the bell or inbox.",
        "audience": "All signed-in users",
        "prerequisites": [
            "Other modules creating notifications (leave, expenses, etc.)",
        ],
        "workflows": [
            "Click the bell for unread count → open inbox",
            "Open a notification and mark it read",
        ],
        "screens": [
            {"label": "Inbox", "url_name": "notifications:inbox"},
        ],
        "tips": [
            "You only see your own notifications",
        ],
    },
    {
        "slug": "audit",
        "title": "Activity log",
        "icon": "file",
        "summary": "Searchable audit trail of who created, updated, approved, signed in, or failed login — with time, module, path, and IP.",
        "audience": "HR · Admin",
        "prerequisites": [
            "audit.view permission",
        ],
        "workflows": [
            "Open Activity log under Settings → Access control",
            "Search by person, action, path, or IP",
            "Filter by module, action type, user, date range",
            "Open a row for full detail",
        ],
        "screens": [
            {"label": "Activity log", "url_name": "audit:log_list"},
        ],
        "tips": [
            "Mutating POSTs are logged automatically; passwords are never stored",
            "Device heartbeats (/iclock, /api) are excluded to reduce noise",
        ],
    },
]

MODULE_BY_SLUG = {m["slug"]: m for m in MODULES}


def get_module(slug: str) -> dict | None:
    return MODULE_BY_SLUG.get(slug)
