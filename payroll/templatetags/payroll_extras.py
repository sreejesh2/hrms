from django import template

from payroll.currencies import currency_label, format_money

register = template.Library()


@register.filter(name="money")
def money_filter(amount, currency_code="AED"):
    return format_money(amount, currency_code)


@register.filter(name="currency_name")
def currency_name_filter(code):
    return currency_label(code or "")
