"""Supported payroll currencies — UAE / GCC first (Dubai-focused)."""

from django.conf import settings

# (code, label, symbol) — amounts always print as "CODE 1,234.56" (PDF-safe)
CURRENCY_META = (
    ("AED", "UAE Dirham (AED)", "AED"),
    ("SAR", "Saudi Riyal (SAR)", "SAR"),
    ("QAR", "Qatari Riyal (QAR)", "QAR"),
    ("OMR", "Omani Rial (OMR)", "OMR"),
    ("BHD", "Bahraini Dinar (BHD)", "BHD"),
    ("KWD", "Kuwaiti Dinar (KWD)", "KWD"),
    ("INR", "Indian Rupee (INR)", "INR"),
    ("USD", "US Dollar (USD)", "USD"),
    ("EUR", "Euro (EUR)", "EUR"),
    ("GBP", "British Pound (GBP)", "GBP"),
)

CURRENCY_CHOICES = tuple((code, label) for code, label, _ in CURRENCY_META)
CURRENCY_CODES = {code for code, _, _ in CURRENCY_META}
CURRENCY_SYMBOLS = {code: symbol for code, _, symbol in CURRENCY_META}
CURRENCY_LABELS = {code: label for code, label, _ in CURRENCY_META}

FALLBACK_DEFAULT = "AED"


def default_currency_code() -> str:
    """Org default → Django setting → AED."""
    try:
        from setup.models import OrganizationSettings

        org = OrganizationSettings.load()
        if org and org.default_currency in CURRENCY_CODES:
            return org.default_currency
    except Exception:
        pass
    code = getattr(settings, "HRMS_DEFAULT_CURRENCY", FALLBACK_DEFAULT) or FALLBACK_DEFAULT
    return code if code in CURRENCY_CODES else FALLBACK_DEFAULT


def currency_symbol(code: str) -> str:
    """Display prefix for amounts — ISO code (PDF/UI safe)."""
    return CURRENCY_SYMBOLS.get(code, code or "")


def currency_label(code: str) -> str:
    return CURRENCY_LABELS.get(code, code or "")


def format_money(amount, code: str | None = None) -> str:
    """
    Human-readable amount with ISO currency code.
    Example: AED 12,500.00 — avoids broken Unicode glyphs in PDF (₹, د.إ, €).
    """
    code = (code or default_currency_code() or FALLBACK_DEFAULT).upper()
    if code not in CURRENCY_CODES:
        code = code or FALLBACK_DEFAULT
    try:
        value = f"{amount:,.2f}"
    except (TypeError, ValueError):
        value = str(amount)
    return f"{code} {value}"
