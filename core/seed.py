"""
Idempotent foundation seeder for Day Pay.

Runs permissions/roles plus default catalogs (leave types, payroll components, …).
Safe to re-run after pulling new permission codenames.
"""

from __future__ import annotations

from typing import Callable

SEED_GROUPS: dict[str, str] = {
    "rbac": "Permission catalog + Admin/HR/Manager/Payroll/Employee roles",
    "org": "Organization settings singleton (Dubai / AED defaults)",
    "leave": "Default leave types (CL, SL, EL, LWP)",
    "expenses": "Default reimbursement categories",
    "payroll": "Salary components + statutory rule catalog",
    "attendance": "Default OT + late policies (lightweight)",
    "ot_rules": "OVERTIME.xlsx rules: OT policies, late tiers, DAY/NIGHT/OFFICE/DRIVER shifts",
    "performance": "Default competencies",
    "admin": "Dev admin user (admin@example.com) with Admin role",
    "demo": "Replace employees with 5 demo staff + GEN shift + this month attendance",
    "sample_pdf": "A1 PDF sample: A1P543/142/445/249 + Jun26–Jul25 2026 punches/OT/leave",
}

# Full defaults: catalogs + OT sheet rules + admin. Opt-in: demo, sample_pdf.
DEFAULT_GROUPS = tuple(
    g for g in SEED_GROUPS if g not in ("demo", "sample_pdf")
)


def _count_before_after(model, key: str, runner: Callable[[], None]) -> dict:
    before = model.objects.count()
    runner()
    after = model.objects.count()
    return {key: after, f"{key}_created": max(0, after - before)}


def seed_rbac_stats() -> dict:
    from accounts.models import AppPermission, Role
    from accounts.rbac import DEFAULT_PERMISSIONS, DEFAULT_ROLES, seed_rbac

    before_p = AppPermission.objects.count()
    before_r = Role.objects.count()
    seed_rbac()
    return {
        "permissions": AppPermission.objects.count(),
        "permissions_catalog": len(DEFAULT_PERMISSIONS),
        "permissions_created": max(0, AppPermission.objects.count() - before_p),
        "roles": Role.objects.count(),
        "roles_catalog": len(DEFAULT_ROLES),
        "roles_created": max(0, Role.objects.count() - before_r),
    }


def seed_org() -> dict:
    from setup.models import OrganizationSettings

    org, created = OrganizationSettings.objects.get_or_create(
        pk=1,
        defaults={
            "company_name": "Day Pay Company",
            "country": "United Arab Emirates",
            "city": "Dubai",
        },
    )
    # Ensure load() path stays consistent even if row already existed empty-ish
    if not org.company_name:
        org.company_name = "Day Pay Company"
        org.save(update_fields=["company_name", "updated_at"])
    return {"organization": 1, "organization_created": int(created)}


def seed_leave() -> dict:
    from leave.models import LeaveType
    from leave.services import seed_default_leave_types

    return _count_before_after(LeaveType, "leave_types", seed_default_leave_types)


def seed_expenses() -> dict:
    from expenses.models import ExpenseCategory
    from expenses.services import seed_default_categories

    return _count_before_after(
        ExpenseCategory, "expense_categories", seed_default_categories
    )


def seed_payroll() -> dict:
    from payroll.incentives import seed_default_incentive_plans
    from payroll.models import IncentivePlan, SalaryComponent, StatutoryRule
    from payroll.services import seed_default_components
    from payroll.statutory import seed_default_statutory_rules

    stats = {}
    stats.update(
        _count_before_after(SalaryComponent, "salary_components", seed_default_components)
    )
    stats.update(
        _count_before_after(
            StatutoryRule, "statutory_rules", seed_default_statutory_rules
        )
    )
    stats.update(
        _count_before_after(
            IncentivePlan, "incentive_plans", seed_default_incentive_plans
        )
    )
    return stats


def seed_attendance() -> dict:
    from attendance.models import LatePenaltyPolicy, OvertimePolicy
    from attendance.ot import (
        seed_company_ot_policies,
        seed_default_late_penalty_policy,
        seed_default_ot_policy,
    )

    def _run():
        seed_default_ot_policy()
        seed_company_ot_policies()
        seed_default_late_penalty_policy()

    stats = _count_before_after(OvertimePolicy, "ot_policies", _run)
    stats["late_penalty_policies"] = LatePenaltyPolicy.objects.count()
    return stats


def seed_ot_rules() -> dict:
    """OVERTIME.xlsx pack: policies + late penalties + linked shifts."""
    from attendance.ot import seed_overtime_sheet_rules

    return seed_overtime_sheet_rules(include_std_policy=True)


def seed_performance() -> dict:
    from performance.models import Competency
    from performance.services import seed_default_competencies

    return _count_before_after(Competency, "competencies", seed_default_competencies)


def seed_admin(
    *,
    email: str = "admin@example.com",
    password: str = "admin123",
    reset_password: bool = False,
) -> dict:
    """Ensure a superuser exists and has the Admin role."""
    from accounts.models import Role, User

    user = User.objects.filter(email__iexact=email).first()
    created = False
    if user is None:
        user = User.objects.create_superuser(email=email, password=password)
        created = True
    else:
        changed = False
        if not user.is_superuser or not user.is_staff or not user.is_active:
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            changed = True
        if reset_password:
            user.set_password(password)
            changed = True
        if changed:
            user.save()

    admin_role = Role.objects.filter(name="Admin").first()
    role_attached = False
    if admin_role and not user.roles.filter(pk=admin_role.pk).exists():
        user.roles.add(admin_role)
        role_attached = True

    return {
        "admin_email": user.email,
        "admin_created": int(created),
        "admin_role_attached": int(role_attached),
        "admin_password_reset": int(reset_password and not created),
    }


_RUNNERS: dict[str, Callable[[], dict]] = {
    "rbac": seed_rbac_stats,
    "org": seed_org,
    "leave": seed_leave,
    "expenses": seed_expenses,
    "payroll": seed_payroll,
    "attendance": seed_attendance,
    "ot_rules": seed_ot_rules,
    "performance": seed_performance,
}


def run_seed(
    groups: list[str] | tuple[str, ...] | None = None,
    *,
    with_admin: bool = False,
    with_demo: bool = False,
    with_sample_pdf: bool = False,
    admin_email: str = "admin@example.com",
    admin_password: str = "admin123",
    reset_admin_password: bool = False,
) -> dict:
    """
    Run selected seed groups. Returns a flat stats dict.

    Default run includes catalogs + OT rules + admin.
    `demo` / `sample_pdf` are opt-in (flags or `--only`).
    """
    selected = list(groups) if groups is not None else list(DEFAULT_GROUPS)
    unknown = [g for g in selected if g not in SEED_GROUPS]
    if unknown:
        raise ValueError(f"Unknown seed group(s): {', '.join(unknown)}")

    want_admin = with_admin or "admin" in selected
    want_demo = with_demo or "demo" in selected
    want_sample = with_sample_pdf or "sample_pdf" in selected

    if want_sample:
        want_admin = True
        for g in ("rbac", "leave", "ot_rules"):
            if g not in selected:
                selected.append(g)

    # Catalog order first; people samples last.
    order = [
        g
        for g in (
            "rbac",
            "org",
            "leave",
            "expenses",
            "payroll",
            "attendance",
            "ot_rules",
            "performance",
        )
        if g in selected
    ]
    if want_admin:
        if "rbac" not in order:
            order.insert(0, "rbac")
        if "admin" not in order:
            order.append("admin")
    if want_demo:
        order.append("demo")
    if want_sample:
        order.append("sample_pdf")

    results: dict = {"groups": order}
    for name in order:
        if name == "admin":
            results.update(
                seed_admin(
                    email=admin_email,
                    password=admin_password,
                    reset_password=reset_admin_password,
                )
            )
        elif name == "demo":
            from core.demo_data import seed_demo_people

            results.update(seed_demo_people())
        elif name == "sample_pdf":
            from core.sample_pdf_data import seed_sample_pdf_people

            results.update(seed_sample_pdf_people())
        else:
            results.update(_RUNNERS[name]())
    return results
