"""
Punch machine adapters — normalize vendor payloads into HRMS punches.

All physical/software machines should ultimately call the same ingest path
(or use these parsers then POST). Keep vendor quirks here, not in views.
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from people.models import Employee

from .models import PunchLog


def resolve_employee(*, employee_code: str = "", biometric_id: str = "") -> Employee | None:
    """Find employee by HR code or machine biometric / PIN / badge id."""
    code = (employee_code or "").strip()
    bio = (biometric_id or "").strip()
    if code:
        emp = Employee.objects.filter(employee_code__iexact=code).first()
        if emp:
            return emp
    if bio:
        return Employee.objects.filter(biometric_id__iexact=bio).exclude(biometric_id="").first()
    return None


def resolve_employee_from_item(item: dict) -> Employee | None:
    """Accept common vendor key aliases."""
    if not isinstance(item, dict):
        return None
    code = (
        item.get("employee_code")
        or item.get("emp_code")
        or item.get("EmployeeCode")
        or ""
    )
    bio = (
        item.get("biometric_id")
        or item.get("device_user_id")
        or item.get("pin")
        or item.get("PIN")
        or item.get("AccNo")
        or item.get("acc_no")
        or item.get("userid")
        or item.get("user_id")
        or item.get("UserID")
        or item.get("enroll_id")
        or ""
    )
    # Some feeds put only one id field
    if not code and not bio:
        alone = item.get("id") or item.get("emp_id") or ""
        if alone:
            # Try as code first, then biometric
            emp = resolve_employee(employee_code=str(alone), biometric_id="")
            if emp:
                return emp
            return resolve_employee(employee_code="", biometric_id=str(alone))
    return resolve_employee(employee_code=str(code), biometric_id=str(bio))


def map_punch_type(raw) -> str:
    """Map vendor status codes to PunchLog.PunchType values."""
    if raw is None or raw == "":
        return PunchLog.PunchType.AUTO
    text = str(raw).strip().lower()
    mapping = {
        "0": PunchLog.PunchType.IN,
        "i": PunchLog.PunchType.IN,
        "in": PunchLog.PunchType.IN,
        "check-in": PunchLog.PunchType.IN,
        "checkin": PunchLog.PunchType.IN,
        "1": PunchLog.PunchType.OUT,
        "o": PunchLog.PunchType.OUT,
        "out": PunchLog.PunchType.OUT,
        "check-out": PunchLog.PunchType.OUT,
        "checkout": PunchLog.PunchType.OUT,
        "2": PunchLog.PunchType.BREAK_OUT,
        "3": PunchLog.PunchType.BREAK_IN,
        "4": PunchLog.PunchType.BREAK_OUT,
        "5": PunchLog.PunchType.BREAK_IN,
        "break_out": PunchLog.PunchType.BREAK_OUT,
        "break-out": PunchLog.PunchType.BREAK_OUT,
        "breakout": PunchLog.PunchType.BREAK_OUT,
        "break_in": PunchLog.PunchType.BREAK_IN,
        "break-in": PunchLog.PunchType.BREAK_IN,
        "breakin": PunchLog.PunchType.BREAK_IN,
        "auto": PunchLog.PunchType.AUTO,
    }
    return mapping.get(text, PunchLog.PunchType.AUTO)


def parse_datetime(value):
    if value is None or value == "":
        raise ValueError("missing datetime")
    if isinstance(value, datetime):
        dt = value
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.get_current_timezone())

    text = str(value).strip().replace("Z", "+0000")
    formats = (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unrecognized datetime: {value}")


def normalize_row_generic(row: dict) -> dict:
    """HRMS / generic CSV columns."""
    return {
        "employee_code": row.get("employee_code") or row.get("emp_code") or "",
        "biometric_id": row.get("biometric_id") or row.get("device_user_id") or "",
        "punched_at": row.get("punched_at") or row.get("timestamp") or row.get("datetime") or "",
        "punch_type": row.get("punch_type") or row.get("type") or "auto",
        "external_id": row.get("external_id") or row.get("id") or "",
    }


def normalize_row_zkteco(row: dict) -> dict:
    """
    Common ZKTeco / eSSL export style.
    Columns often: AccNo/PIN/UserID, DateTime/Time, Status/InOut
    """
    # case-insensitive key access
    lower = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    bio = (
        lower.get("accno")
        or lower.get("acc_no")
        or lower.get("pin")
        or lower.get("userid")
        or lower.get("user_id")
        or lower.get("enrollnumber")
        or lower.get("enroll_id")
        or ""
    )
    punched = (
        lower.get("datetime")
        or lower.get("date_time")
        or lower.get("time")
        or lower.get("checktime")
        or ""
    )
    # Sometimes date + time split
    if not punched and (lower.get("date") and lower.get("time")):
        punched = f"{lower.get('date')} {lower.get('time')}"
    status = lower.get("status") or lower.get("inout") or lower.get("in_out") or lower.get("punch") or ""
    external = lower.get("id") or lower.get("logid") or ""
    return {
        "employee_code": "",
        "biometric_id": str(bio).strip(),
        "punched_at": punched,
        "punch_type": map_punch_type(status),
        "external_id": str(external).strip(),
    }


VENDOR_FORMATS = {
    "generic": {
        "label": "Generic CSV (employee_code / biometric_id)",
        "normalize": normalize_row_generic,
        "sample_headers": [
            "employee_code",
            "biometric_id",
            "punched_at",
            "punch_type",
            "external_id",
        ],
        "sample_rows": [
            ["E001", "10023", "2026-07-22 09:05:00", "in", "zk-1"],
            ["", "10023", "2026-07-22 13:00:00", "break_out", "zk-2"],
            ["", "10023", "2026-07-22 14:00:00", "break_in", "zk-3"],
            ["E001", "10023", "2026-07-22 18:10:00", "out", "zk-4"],
        ],
    },
    "zkteco": {
        "label": "ZKTeco / eSSL style (AccNo + DateTime + Status)",
        "normalize": normalize_row_zkteco,
        "sample_headers": ["AccNo", "DateTime", "Status"],
        "sample_rows": [
            ["10023", "2026-07-22 09:05:00", "0"],
            ["10023", "2026-07-22 13:00:00", "4"],
            ["10023", "2026-07-22 14:00:00", "5"],
            ["10023", "2026-07-22 18:10:00", "1"],
        ],
    },
}


def parse_vendor_csv_rows(rows: list[dict], format_key: str) -> list[dict]:
    """Return list of normalized punch dicts ready for ingest."""
    cfg = VENDOR_FORMATS.get(format_key) or VENDOR_FORMATS["generic"]
    normalize = cfg["normalize"]
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # skip empty
        if not any(str(v or "").strip() for v in row.values()):
            continue
        out.append(normalize(row))
    return out
