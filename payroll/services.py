"""Salary structure helpers — effective-dated, template-driven for scale."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from .currencies import default_currency_code
from .models import (
    SalaryComponent,
    SalaryStructure,
    SalaryStructureLine,
    SalaryTemplate,
    SalaryTemplateLine,
)


def structure_on(employee, on_date):
    return (
        SalaryStructure.objects.filter(employee=employee, effective_from__lte=on_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .prefetch_related("lines__component")
        .order_by("-effective_from", "-id")
        .first()
    )


def structures_on(employee_ids, on_date) -> dict:
    """{employee_id: structure effective on `on_date`} in two queries (bulk structure_on)."""
    result = {}
    for st in (
        SalaryStructure.objects.filter(employee_id__in=employee_ids, effective_from__lte=on_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .prefetch_related("lines__component")
        .order_by("employee_id", "-effective_from", "-id")
    ):
        result.setdefault(st.employee_id, st)
    return result


def current_structure(employee):
    from django.utils import timezone

    return structure_on(employee, timezone.localdate())


@transaction.atomic
def close_open_structures(employee, day_before):
    """Close any open structure the day before a new one starts."""
    SalaryStructure.objects.filter(employee=employee, effective_to__isnull=True).update(
        effective_to=day_before
    )


@transaction.atomic
def create_structure(
    *,
    employee,
    effective_from,
    lines,
    template=None,
    currency=None,
    notes="",
    created_by=None,
    close_previous=True,
):
    """
    lines: iterable of dicts {component, amount, percent?}
    Must include Basic if you want OT base later.
    """
    if currency is None:
        currency = default_currency_code()
    if close_previous:
        day_before = effective_from - timedelta(days=1)
        # Only close if previous started before this date
        open_qs = SalaryStructure.objects.filter(
            employee=employee, effective_to__isnull=True
        )
        for prev in open_qs:
            if prev.effective_from >= effective_from:
                raise ValueError(
                    "An open structure already starts on/after this effective date. "
                    "Edit or end it first."
                )
            prev.effective_to = day_before
            prev.save(update_fields=["effective_to", "updated_at"])

    structure = SalaryStructure.objects.create(
        employee=employee,
        effective_from=effective_from,
        template=template,
        currency=currency,
        notes=notes,
        created_by=created_by,
    )
    for row in lines:
        component = row["component"]
        SalaryStructureLine.objects.create(
            structure=structure,
            component=component,
            amount=row.get("amount") or Decimal("0.00"),
            percent=row.get("percent"),
        )
    return structure


@transaction.atomic
def apply_template(
    *,
    employee,
    template,
    effective_from,
    created_by=None,
    notes="",
    currency=None,
):
    lines = [
        {
            "component": line.component,
            "amount": line.amount,
            "percent": line.percent,
        }
        for line in template.lines.select_related("component")
    ]
    if not lines:
        raise ValueError("Template has no lines.")
    if currency is None:
        currency = template.currency or default_currency_code()
    return create_structure(
        employee=employee,
        effective_from=effective_from,
        lines=lines,
        template=template,
        currency=currency,
        notes=notes or f"From template {template.code}",
        created_by=created_by,
    )


@transaction.atomic
def update_structure(*, structure, effective_from, currency, notes, lines):
    """
    In-place edit of an open structure's header + lines.
    lines: iterable of dicts {component, amount, percent?}
    """
    if structure.effective_to is not None:
        raise ValueError("Closed (historical) structures cannot be edited. Create a new revision.")
    if not lines:
        raise ValueError("Add at least one salary line.")
    if not any(row["component"].is_basic for row in lines):
        raise ValueError("Include the Basic component in the structure.")

    structure.effective_from = effective_from
    structure.currency = currency or default_currency_code()
    structure.notes = notes or ""
    structure.full_clean()
    structure.save()

    structure.lines.all().delete()
    for row in lines:
        SalaryStructureLine.objects.create(
            structure=structure,
            component=row["component"],
            amount=row.get("amount") or Decimal("0.00"),
            percent=row.get("percent"),
        )
    return structure


def seed_default_components():
    specs = [
        # code, name, kind, is_basic, ot_base, order, prorate
        ("BASIC", "Basic", SalaryComponent.Kind.EARNING, True, True, 10, True),
        ("COL", "Cost of Living", SalaryComponent.Kind.EARNING, False, False, 15, True),
        ("HRA", "House Rent Allowance", SalaryComponent.Kind.EARNING, False, False, 20, True),
        ("FOOD", "Food Allow (Fixed)", SalaryComponent.Kind.EARNING, False, False, 25, False),
        ("CONV", "Conveyance", SalaryComponent.Kind.EARNING, False, False, 30, True),
        ("SPECIAL", "Special Allowance", SalaryComponent.Kind.EARNING, False, False, 40, True),
        ("EXTRA_ALLOW", "Extra Allow Amt", SalaryComponent.Kind.EARNING, False, False, 45, True),
        ("BONUS", "Bonus", SalaryComponent.Kind.EARNING, False, False, 50, False),
        ("INCENTIVE", "Incentive", SalaryComponent.Kind.EARNING, False, False, 55, False),
        ("OTHER_DED", "Other Deduction", SalaryComponent.Kind.DEDUCTION, False, False, 190, True),
        ("PF_EE", "PF Employee", SalaryComponent.Kind.DEDUCTION, False, False, 200, True),
        ("PT", "Professional Tax", SalaryComponent.Kind.DEDUCTION, False, False, 210, True),
    ]
    for code, name, kind, is_basic, ot_base, order, prorate in specs:
        SalaryComponent.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "kind": kind,
                "calc_method": SalaryComponent.CalcMethod.FIXED,
                "is_basic": is_basic,
                "is_taxable": kind == SalaryComponent.Kind.EARNING,
                "affects_ot_base": ot_base and is_basic,
                "prorate_with_attendance": prorate,
                "sort_order": order,
                "is_active": True,
            },
        )
