"""Statutory rule helpers + seeding."""

from decimal import Decimal

from .models import StatutoryRule


def active_payroll_rules():
    return StatutoryRule.objects.filter(is_active=True, apply_in_payroll=True)


def seed_default_statutory_rules():
    """
    Dubai-oriented catalog. Most start inactive so companies opt-in.
    GPSSA rates are illustrative for UAE nationals — enable only when applicable.
    """
    specs = [
        {
            "code": "GPSSA_EE",
            "name": "GPSSA employee contribution",
            "kind": StatutoryRule.Kind.DEDUCTION,
            "calc_method": StatutoryRule.CalcMethod.PERCENT_BASIC,
            "percent": Decimal("5.00"),
            "amount": Decimal("0.00"),
            "sort_order": 310,
            "is_active": False,
            "apply_in_payroll": True,
            "notes": "UAE nationals pension (illustrative 5% of basic). Enable per policy.",
        },
        {
            "code": "MEDICAL_EE",
            "name": "Medical insurance (employee)",
            "kind": StatutoryRule.Kind.DEDUCTION,
            "calc_method": StatutoryRule.CalcMethod.FIXED,
            "amount": Decimal("0.00"),
            "percent": None,
            "sort_order": 320,
            "is_active": False,
            "apply_in_payroll": True,
            "notes": "Set fixed monthly employee medical share if deducted from salary.",
        },
        {
            "code": "LOAN_EMI",
            "name": "Loan / advance EMI",
            "kind": StatutoryRule.Kind.DEDUCTION,
            "calc_method": StatutoryRule.CalcMethod.FIXED,
            "amount": Decimal("0.00"),
            "percent": None,
            "sort_order": 330,
            "is_active": False,
            "apply_in_payroll": True,
            "notes": "Company loan recovery. Prefer per-employee overrides later; use as template.",
        },
        {
            "code": "OTHER_DED",
            "name": "Other deduction",
            "kind": StatutoryRule.Kind.DEDUCTION,
            "calc_method": StatutoryRule.CalcMethod.FIXED,
            "amount": Decimal("0.00"),
            "percent": None,
            "sort_order": 340,
            "is_active": False,
            "apply_in_payroll": True,
            "notes": "Generic monthly deduction policy line.",
        },
    ]
    for row in specs:
        StatutoryRule.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "kind": row["kind"],
                "calc_method": row["calc_method"],
                "amount": row["amount"],
                "percent": row.get("percent"),
                "country": "United Arab Emirates",
                "notes": row["notes"],
                "sort_order": row["sort_order"],
                "is_active": row["is_active"],
                "apply_in_payroll": row["apply_in_payroll"],
            },
        )
