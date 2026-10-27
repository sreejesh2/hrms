def ui_chrome(request):
    """Shared chrome for sidebar / theme / unread notifications."""
    unread = 0
    view_name = ""
    if getattr(request, "user", None) and request.user.is_authenticated:
        from notifications.models import Notification

        unread = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
    match = getattr(request, "resolver_match", None)
    if match:
        view_name = match.view_name or ""

    from core.breadcrumbs import resolve_page_nav

    nav = resolve_page_nav(
        view_name,
        kwargs=getattr(match, "kwargs", None) if match else None,
    )

    perms = getattr(request, "hrms_perms", set()) or set()

    def can(codename: str | None) -> bool:
        if not codename:
            return True
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_superuser", False):
            return True
        return codename in perms

    # Ordered: Main → People → Operations → Settings (admin)
    nav_tree = [
        {
            "kind": "section",
            "name": "Main",
            "children": [
                {
                    "kind": "link",
                    "name": "Dashboard",
                    "url_name": "core:dashboard",
                    "perm": "core.view_dashboard",
                    "icon": "home",
                },
            ],
        },
        {
            "kind": "section",
            "name": "People",
            "children": [
                {
                    "kind": "dropdown",
                    "name": "Employees",
                    "id": "people-employees",
                    "icon": "users",
                    "children": [
                        {
                            "kind": "link",
                            "name": "All employees",
                            "url_name": "people:employee_list",
                            "perm": "people.view_employees",
                        },
                        {
                            "kind": "link",
                            "name": "Active",
                            "url_name": "people:active_list",
                            "perm": "people.view_employees",
                        },
                        {
                            "kind": "link",
                            "name": "On vacation",
                            "url_name": "people:vacation_list",
                            "perm": "people.view_employees",
                        },
                        {
                            "kind": "link",
                            "name": "Onboarding",
                            "url_name": "people:onboarding_list",
                            "perm": "people.view_onboarding",
                        },
                    ],
                },
            ],
        },
        {
            "kind": "section",
            "name": "Operations",
            "children": [
                {
                    "kind": "dropdown",
                    "name": "Attendance",
                    "id": "ops-attendance",
                    "icon": "clock",
                    "perm": "attendance.view",
                    "children": [
                        {
                            "kind": "link",
                            "name": "Monthly register",
                            "url_name": "attendance_ops:register_month",
                            "perm": "attendance.view",
                        },
                        {
                            "kind": "link",
                            "name": "Daily attendance",
                            "url_name": "attendance_ops:daily_list",
                            "perm": "attendance.view",
                        },
                        {
                            "kind": "link",
                            "name": "Regularization",
                            "url_name": "attendance_ops:regularization_list",
                            "perm": "attendance.view",
                        },
                        {
                            "kind": "link",
                            "name": "Punches",
                            "url_name": "attendance_ops:punch_list",
                            "perm": "attendance.view",
                        },
                    ],
                },
                {
                    "kind": "dropdown",
                    "name": "Leave",
                    "id": "ops-leave",
                    "icon": "calendar",
                    "perm": "leave.view",
                    "children": [
                        {
                            "kind": "link",
                            "name": "Requests",
                            "url_name": "leave:list",
                            "perm": "leave.view",
                        },
                        {
                            "kind": "link",
                            "name": "Apply",
                            "url_name": "leave:create",
                            "perm": "leave.request",
                        },
                        {
                            "kind": "link",
                            "name": "Balances",
                            "url_name": "leave:balance_list",
                            "perm": "leave.view",
                        },
                        {
                            "kind": "link",
                            "name": "Leave types",
                            "url_name": "leave:type_list",
                            "perm": "leave.manage",
                        },
                    ],
                },
                {
                    "kind": "dropdown",
                    "name": "Payroll",
                    "id": "ops-payroll",
                    "icon": "wallet",
                    "perm": "payroll.view",
                    "children": [
                        {
                            "kind": "link",
                            "name": "Overview",
                            "url_name": "payroll:home",
                            "perm": "payroll.view",
                        },
                        {
                            "kind": "link",
                            "name": "Periods",
                            "url_name": "payroll:period_list",
                            "perm": "payroll.view",
                        },
                        {
                            "kind": "link",
                            "name": "Payslip template",
                            "url_name": "payroll:payslip_template_edit",
                            "perm": "payroll.manage",
                        },
                        {
                            "kind": "link",
                            "name": "Statutory & deductions",
                            "url_name": "payroll:statutory_list",
                            "perm": "payroll.manage",
                        },
                        {
                            "kind": "link",
                            "name": "Incentive plans",
                            "url_name": "payroll:incentive_plan_list",
                            "perm": "payroll.manage",
                        },
                        {
                            "kind": "link",
                            "name": "Incentive awards",
                            "url_name": "payroll:incentive_award_list",
                            "perm": "payroll.manage",
                        },
                        {
                            "kind": "link",
                            "name": "Gratuity estimates",
                            "url_name": "payroll:gratuity_list",
                            "perm": "payroll.view",
                        },
                        {
                            "kind": "link",
                            "name": "Salary structures",
                            "url_name": "payroll:structure_list",
                            "perm": "payroll.view",
                        },
                        {
                            "kind": "link",
                            "name": "Components",
                            "url_name": "payroll:component_list",
                            "perm": "payroll.manage",
                        },
                        {
                            "kind": "link",
                            "name": "Templates",
                            "url_name": "payroll:template_list",
                            "perm": "payroll.manage",
                        },
                    ],
                },
                {
                    "kind": "dropdown",
                    "name": "Performance",
                    "id": "ops-performance",
                    "icon": "chart",
                    "perm": "performance.view",
                    "children": [
                        {
                            "kind": "link",
                            "name": "Reviews",
                            "url_name": "performance:list",
                            "perm": "performance.view",
                        },
                        {
                            "kind": "link",
                            "name": "Review cycles",
                            "url_name": "performance:cycle_list",
                            "perm": "performance.manage",
                        },
                        {
                            "kind": "link",
                            "name": "Competencies",
                            "url_name": "performance:competency_list",
                            "perm": "performance.manage",
                        },
                    ],
                },
                {
                    "kind": "dropdown",
                    "name": "Reimbursements",
                    "id": "ops-expenses",
                    "icon": "receipt",
                    "perm": "expenses.view",
                    "children": [
                        {
                            "kind": "link",
                            "name": "Claims",
                            "url_name": "expenses:list",
                            "perm": "expenses.view",
                        },
                        {
                            "kind": "link",
                            "name": "Submit claim",
                            "url_name": "expenses:create",
                            "perm": "expenses.request",
                        },
                        {
                            "kind": "link",
                            "name": "Categories",
                            "url_name": "expenses:category_list",
                            "perm": "expenses.manage",
                        },
                    ],
                },
                {
                    "kind": "dropdown",
                    "name": "Salary advances",
                    "id": "ops-loans",
                    "icon": "wallet",
                    "perm": "loans.view",
                    "children": [
                        {
                            "kind": "link",
                            "name": "All advances",
                            "url_name": "loans:list",
                            "perm": "loans.view",
                        },
                        {
                            "kind": "link",
                            "name": "Request advance",
                            "url_name": "loans:create",
                            "perm": "loans.request",
                        },
                    ],
                },
                {
                    "kind": "dropdown",
                    "name": "Shift master",
                    "id": "ops-shift-master",
                    "icon": "clock",
                    "perm": "attendance.manage_shifts",
                    "children": [
                        {
                            "kind": "link",
                            "name": "Work shifts",
                            "url_name": "attendance:shift_list",
                            "perm": "attendance.manage_shifts",
                        },
                        {
                            "kind": "link",
                            "name": "Manage shifts",
                            "url_name": "attendance:assignment_list",
                            "perm": "attendance.manage_shifts",
                        },
                        {
                            "kind": "link",
                            "name": "Bulk assign shifts",
                            "url_name": "attendance:assignment_bulk",
                            "perm": "attendance.manage_shifts",
                        },
                        {
                            "kind": "link",
                            "name": "Import shifts (CSV)",
                            "url_name": "attendance:assignment_import",
                            "perm": "attendance.manage_shifts",
                        },
                    ],
                },
                {
                    "kind": "link",
                    "name": "Reports",
                    "icon": "file",
                    "url_name": "reports:home",
                    "perm": "reports.view",
                },
                {
                    "kind": "link",
                    "name": "My corrections",
                    "url_name": "attendance_ops:regularization_list",
                    "perm": "attendance.request_regularization",
                    "icon": "clock",
                },
            ],
        },
        {
            "kind": "section",
            "name": "Administration",
            "children": [
                {
                    "kind": "dropdown",
                    "name": "Settings",
                    "id": "settings",
                    "icon": "gear",
                    "children": [
                        {
                            "kind": "dropdown",
                            "name": "Organization",
                            "id": "settings-org",
                            "children": [
                                {
                                    "kind": "link",
                                    "name": "Company",
                                    "url_name": "setup:organization_settings",
                                    "perm": "setup.manage_company",
                                },
                                {
                                    "kind": "link",
                                    "name": "Departments",
                                    "url_name": "setup:master_list",
                                    "url_kwargs": {"master_key": "departments"},
                                    "perm": "masters.view_departments",
                                },
                                {
                                    "kind": "link",
                                    "name": "Divisions",
                                    "url_name": "setup:master_list",
                                    "url_kwargs": {"master_key": "divisions"},
                                    "perm": "masters.view_divisions",
                                },
                                {
                                    "kind": "link",
                                    "name": "Locations",
                                    "url_name": "setup:master_list",
                                    "url_kwargs": {"master_key": "locations"},
                                    "perm": "masters.view_locations",
                                },
                                {
                                    "kind": "link",
                                    "name": "Positions",
                                    "url_name": "setup:master_list",
                                    "url_kwargs": {"master_key": "positions"},
                                    "perm": "masters.view_positions",
                                },
                                {
                                    "kind": "link",
                                    "name": "Banks",
                                    "url_name": "setup:master_list",
                                    "url_kwargs": {"master_key": "banks"},
                                    "perm": "masters.view_banks",
                                },
                            ],
                        },
                        {
                            "kind": "dropdown",
                            "name": "Employee settings",
                            "id": "settings-employee",
                            "perm": "setup.manage_employee_fields",
                            "children": [
                                {
                                    "kind": "link",
                                    "name": "Custom fields",
                                    "url_name": "setup:employee_fields",
                                    "perm": "setup.manage_employee_fields",
                                },
                            ],
                        },
                        {
                            "kind": "dropdown",
                            "name": "Time settings",
                            "id": "settings-time",
                            "children": [
                                {
                                    "kind": "link",
                                    "name": "Work calendars",
                                    "url_name": "attendance:calendar_list",
                                    "perm": "attendance.manage_calendars",
                                },
                                {
                                    "kind": "link",
                                    "name": "Holidays",
                                    "url_name": "attendance:holiday_list",
                                    "perm": "attendance.manage_calendars",
                                },
                                {
                                    "kind": "link",
                                    "name": "Overtime policies",
                                    "url_name": "attendance:ot_policy_list",
                                    "perm": "attendance.manage_shifts",
                                },
                                {
                                    "kind": "link",
                                    "name": "Late penalties",
                                    "url_name": "attendance:late_penalty_list",
                                    "perm": "attendance.manage_shifts",
                                },
                                {
                                    "kind": "link",
                                    "name": "Punch devices",
                                    "url_name": "attendance:device_list",
                                    "perm": "attendance.manage_devices",
                                },
                            ],
                        },
                        {
                            "kind": "dropdown",
                            "name": "Access control",
                            "id": "settings-access",
                            "children": [
                                {
                                    "kind": "link",
                                    "name": "Roles",
                                    "url_name": "setup:role_list",
                                    "perm": "access.manage_roles",
                                },
                                {
                                    "kind": "link",
                                    "name": "Permissions",
                                    "url_name": "setup:permission_list",
                                    "perm": "access.manage_permissions",
                                },
                                {
                                    "kind": "link",
                                    "name": "User roles",
                                    "url_name": "setup:user_role_list",
                                    "perm": "access.assign_user_roles",
                                },
                                {
                                    "kind": "link",
                                    "name": "Activity log",
                                    "url_name": "audit:log_list",
                                    "perm": "audit.view",
                                },
                                {
                                    "kind": "link",
                                    "name": "Backups",
                                    "url_name": "setup:backup_list",
                                    "perm": "setup.manage_backups",
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    ]

    def filter_nodes(nodes):
        visible = []
        for node in nodes:
            if not can(node.get("perm")):
                continue
            child_list = node.get("children")
            if child_list is not None:
                filtered = filter_nodes(child_list)
                if node["kind"] in ("dropdown", "section", "group"):
                    if not filtered:
                        continue
                    node = {**node, "children": filtered}
            visible.append(node)
        return visible

    nav_tree = filter_nodes(nav_tree)

    match_kwargs = {}
    if getattr(request, "resolver_match", None):
        match_kwargs = request.resolver_match.kwargs or {}

    # Satellite pages highlight their parent *list* nav item only — never siblings
    # like assignment_bulk / assignment_import (those are their own menu entries).
    _SATELLITE_SUFFIXES = (
        "_approve_selected",
        "_create",
        "_edit",
        "_detail",
        "_delete",
        "_approve",
        "_cancel",
        "_run",
        "_lock",
        "_pdf",
        "_sample_pdf",
    )
    _VIEW_PARENT = {
        "payslip_detail": "period_list",
        "payslip_pdf": "period_list",
        "period_create": "period_list",
        "apply_template": "structure_list",
        "employee_field_create": "employee_fields",
        "employee_field_edit": "employee_fields",
        "employee_field_delete": "employee_fields",
        "user_role_edit": "user_role_list",
        "incentive_award_import": "incentive_award_list",
        "assignment_apply_defaults": "assignment_list",
    }

    def _parent_nav_local(view: str) -> str | None:
        local = (view or "").split(":")[-1]
        if local in _VIEW_PARENT:
            return _VIEW_PARENT[local]
        for suffix in _SATELLITE_SUFFIXES:
            if local.endswith(suffix):
                stem = local[: -len(suffix)]
                if stem:
                    return f"{stem}_list"
        return None

    def _link_matches(node: dict) -> bool:
        url_name = node.get("url_name") or ""
        if not url_name or not view_name:
            return False
        want = node.get("url_kwargs") or {}
        if want and not all(match_kwargs.get(k) == v for k, v in want.items()):
            return False
        if url_name == view_name:
            return True
        if ":" not in url_name or ":" not in view_name:
            return False
        if url_name.split(":", 1)[0] != view_name.split(":", 1)[0]:
            return False
        parent = _parent_nav_local(view_name)
        return bool(parent) and url_name.split(":", 1)[1] == parent

    def mark_active(nodes, ancestors_open=None):
        ancestors_open = ancestors_open or []
        any_active = False
        for node in nodes:
            node["active"] = False
            node["open"] = False
            if node["kind"] == "link" and _link_matches(node):
                node["active"] = True
                any_active = True
                for a in ancestors_open:
                    a["open"] = True
            elif node["kind"] in ("dropdown", "section", "group") and node.get("children"):
                if mark_active(node["children"], ancestors_open + [node]):
                    any_active = True
                    node["open"] = True
        return any_active

    mark_active(nav_tree)

    chrome_user = {
        "display_name": "",
        "role_label": "Account",
        "initials": "?",
        "email": "",
        "has_employee": False,
    }
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        employee = getattr(user, "employee_profile", None)
        display = ""
        if employee:
            display = employee.full_name
        if not display:
            display = (user.get_full_name() or "").strip()
        if not display:
            display = user.email
        roles = list(user.roles.filter(is_active=True).order_by("name")[:1])
        if user.is_superuser and not roles:
            role_label = "Admin"
        elif roles:
            role_label = roles[0].name
        else:
            role_label = "Account"
        if employee:
            parts = f"{employee.first_name} {employee.last_name}".strip().split()
            initials = "".join(p[0] for p in parts[:2]).upper() if parts else user.email[:1].upper()
        elif user.get_full_name():
            parts = user.get_full_name().split()
            initials = "".join(p[0] for p in parts[:2]).upper()
        else:
            initials = (user.email or "?")[:1].upper()
        chrome_user = {
            "display_name": display,
            "role_label": role_label,
            "initials": initials,
            "email": user.email,
            "has_employee": bool(employee),
        }

    return {
        "theme": getattr(request, "theme", "light"),
        "nav_tree": nav_tree,
        "unread_notifications": unread,
        "app_name": "Day Pay",
        "current_view": view_name,
        "hrms_perms": perms,
        "page_breadcrumbs": nav["crumbs"],
        "page_back_url": nav["back_url"],
        "chrome_user": chrome_user,
    }
