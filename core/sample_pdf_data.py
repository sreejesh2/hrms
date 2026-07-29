"""
Sample data from A1 Plastic attendance PDFs (period 26/06/2026–25/07/2026).

Employees:
  A1P543 — REGULAR (office), Sundays off, OT ≈ hours − 8
  A1P142 — DAYSHIFT, Sundays often worked (OT × 1.25 → C.OT)
  A1P445 — Annual leave → night/day mix, sick, absent
  A1P249 — DAYSHIFT heavy OT + some late Ded

Idempotent for these codes; does not wipe other employees.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

PERIOD_START = date(2026, 6, 26)
PERIOD_END = date(2026, 7, 25)


def _aware(d: date, t: time):
    tz = timezone.get_current_timezone()
    naive = datetime.combine(d, t)
    return timezone.make_aware(naive, tz) if timezone.is_naive(naive) else naive


def _parse_ampm(s: str) -> time:
    """'9:04 am' / '6:53 pm' → time."""
    s = s.strip().lower().replace(".", "")
    parts = s.replace("  ", " ").split()
    hm = parts[0]
    ampm = parts[1] if len(parts) > 1 else "am"
    h, m = hm.split(":")
    h = int(h)
    m = int(m)
    if ampm.startswith("p") and h != 12:
        h += 12
    if ampm.startswith("a") and h == 12:
        h = 0
    return time(h, m)


def _ensure_foundation():
    from attendance.ot import seed_overtime_sheet_rules
    from leave.services import seed_default_leave_types
    from setup.models import OrganizationSettings

    seed_overtime_sheet_rules(include_std_policy=True)
    seed_default_leave_types()

    org = OrganizationSettings.load()
    changed = []
    if org.company_name != "A1 PLASTIC INDUSTRY":
        org.company_name = "A1 PLASTIC INDUSTRY"
        changed.append("company_name")
    if org.cycle_start_day != 26:
        org.cycle_start_day = 26
        changed.append("cycle_start_day")
    if changed:
        org.save(update_fields=[*changed, "updated_at"])

    # Alias shifts matching PDF names
    from attendance.models import OvertimePolicy, WorkShift, WorkShiftVersion, LatePenaltyPolicy

    late = LatePenaltyPolicy.objects.filter(code="STD-LATE").first()
    fixed8 = OvertimePolicy.objects.filter(code="FIXED-8").first()
    wrk_day = OvertimePolicy.objects.filter(code="WRK-DAY").first()
    wrk_night = OvertimePolicy.objects.filter(code="WRK-NIGHT").first()
    year_start = date(PERIOD_START.year, 1, 1)

    aliases = (
        ("REGULAR", "Regular (office)", fixed8, time(9, 0), time(17, 30), False, time(13, 0), time(13, 30)),
        ("DAYSHIFT", "Day shift (workers)", wrk_day or fixed8, time(7, 0), time(15, 30), False, time(12, 0), time(12, 30)),
        ("NIGHTSHI", "Night shift", wrk_night, time(19, 0), time(3, 30), True, time(23, 0), time(23, 30)),
    )
    for code, name, ot, frm, to, span, bf, bt in aliases:
        shift, _ = WorkShift.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "is_active": True,
                "ot_policy": ot,
                "late_penalty_policy": late,
            },
        )
        ver, _ = WorkShiftVersion.objects.update_or_create(
            shift=shift,
            effective_from=year_start,
            defaults={
                "shift_from": frm,
                "shift_to": to,
                "day_span": span,
                "break_from": bf,
                "break_to": bt,
                "notes": f"PDF sample alias {code}",
            },
        )
        ver.recalculate_hours()
        ver.save()


def _masters():
    from people.models import Department, Division, Location, Position

    division, _ = Division.objects.update_or_create(
        code="OPS",
        defaults={"description": "Operations", "is_active": True},
    )
    location, _ = Location.objects.update_or_create(
        code="DXB",
        defaults={"description": "Dubai", "is_active": True},
    )
    dept, _ = Department.objects.update_or_create(
        code="PROD",
        defaults={
            "description": "Production",
            "division": division,
            "is_active": True,
        },
    )
    positions = {}
    for code, name in (
        ("WORKER", "Factory Worker"),
        ("OFFICE", "Office Staff"),
        ("DRIVER", "Driver"),
    ):
        positions[code], _ = Position.objects.update_or_create(
            code=code,
            defaults={"description": name, "is_active": True},
        )
    return {
        "division": division,
        "location": location,
        "dept": dept,
        "positions": positions,
    }


EMPLOYEES = [
    {
        "code": "A1P543",
        "first_name": "Jibin Thomas",
        "last_name": "George",
        "email": "jibin.george@a1plastic.demo",
        "phone": "501111543",
        "bio": "1543",
        "position": "OFFICE",
        "default_shift": "REGULAR",
    },
    {
        "code": "A1P142",
        "first_name": "Poll Krishna",
        "last_name": "Kanesal",
        "email": "poll.kanesal@a1plastic.demo",
        "phone": "501111142",
        "bio": "1142",
        "position": "WORKER",
        "default_shift": "DAYSHIFT",
    },
    {
        "code": "A1P445",
        "first_name": "Akash Singh",
        "last_name": "Shesh Bahadur",
        "email": "akash.singh@a1plastic.demo",
        "phone": "501111445",
        "bio": "1445",
        "position": "WORKER",
        "default_shift": "DAYSHIFT",
    },
    {
        "code": "A1P249",
        "first_name": "Nilojan Samithambi",
        "last_name": "Pakkiyarsa",
        "email": "nilojan.pakkiyarsa@a1plastic.demo",
        "phone": "501111249",
        "bio": "1249",
        "position": "WORKER",
        "default_shift": "DAYSHIFT",
    },
]


# Punch rows: (date, in_str|None, out_str|None, kind)
# kind: work | off | leave_annual | leave_sick | absent
# From A1P 543 / 142 / 445 / 249 PDFs (Jun 26 – Jul 25 2026)

PUNCHES_543 = [
    (date(2026, 6, 26), "9:04 am", "6:53 pm", "work"),
    (date(2026, 6, 27), "8:58 am", "6:52 pm", "work"),
    (date(2026, 6, 28), None, None, "off"),
    (date(2026, 6, 29), "9:00 am", "6:39 pm", "work"),
    (date(2026, 6, 30), "9:01 am", "5:57 pm", "work"),
    (date(2026, 7, 1), "9:02 am", "7:14 pm", "work"),
    (date(2026, 7, 2), "9:00 am", "5:50 pm", "work"),
    (date(2026, 7, 3), "9:02 am", "6:27 pm", "work"),
    (date(2026, 7, 4), "9:02 am", "6:47 pm", "work"),
    (date(2026, 7, 5), None, None, "off"),
    (date(2026, 7, 6), "9:05 am", "6:49 pm", "work"),
    (date(2026, 7, 7), "8:58 am", "6:30 pm", "work"),
    (date(2026, 7, 8), "8:58 am", "6:52 pm", "work"),
    (date(2026, 7, 9), "9:03 am", "6:30 pm", "work"),
    (date(2026, 7, 10), "8:58 am", "6:36 pm", "work"),
    (date(2026, 7, 11), "8:57 am", "6:22 pm", "work"),
    (date(2026, 7, 12), None, None, "off"),
    (date(2026, 7, 13), "9:02 am", "6:53 pm", "work"),
    (date(2026, 7, 14), "8:59 am", "6:34 pm", "work"),
    (date(2026, 7, 15), "9:03 am", "6:48 pm", "work"),
    (date(2026, 7, 16), "9:01 am", "6:48 pm", "work"),
    (date(2026, 7, 17), "8:58 am", "6:17 pm", "work"),
    (date(2026, 7, 18), "9:04 am", "6:34 pm", "work"),
    (date(2026, 7, 19), None, None, "off"),
    (date(2026, 7, 20), "9:03 am", "5:57 pm", "work"),
    (date(2026, 7, 21), "9:03 am", "6:45 pm", "work"),
    (date(2026, 7, 22), "9:03 am", "6:39 pm", "work"),
    (date(2026, 7, 23), "9:05 am", "6:35 pm", "work"),
    (date(2026, 7, 24), "9:03 am", "5:48 pm", "work"),
    (date(2026, 7, 25), "9:03 am", "6:18 pm", "work"),
]

PUNCHES_142 = [
    (date(2026, 6, 26), "6:54 am", "7:32 pm", "work"),
    (date(2026, 6, 27), "6:55 am", "7:38 pm", "work"),
    (date(2026, 6, 28), "6:56 am", "4:27 pm", "work"),  # Sunday worked
    (date(2026, 6, 29), "6:53 am", "7:42 pm", "work"),
    (date(2026, 6, 30), "6:50 am", "7:33 pm", "work"),
    (date(2026, 7, 1), "6:53 am", "7:24 pm", "work"),
    (date(2026, 7, 2), "6:55 am", "7:29 pm", "work"),
    (date(2026, 7, 3), "6:46 am", "7:27 pm", "work"),
    (date(2026, 7, 4), "6:52 am", "8:01 pm", "work"),
    (date(2026, 7, 5), "6:58 am", "7:09 pm", "work"),  # Sunday worked
    (date(2026, 7, 6), "6:51 am", "7:22 pm", "work"),
    (date(2026, 7, 7), "6:48 am", "7:06 pm", "work"),
    (date(2026, 7, 8), "6:50 am", "7:13 pm", "work"),
    (date(2026, 7, 9), "7:00 am", "7:23 pm", "work"),
    (date(2026, 7, 10), "6:53 am", "7:25 pm", "work"),
    (date(2026, 7, 11), "6:51 am", "7:14 pm", "work"),
    (date(2026, 7, 12), "6:58 am", "7:20 pm", "work"),  # Sunday worked
    (date(2026, 7, 13), "6:48 am", "7:07 pm", "work"),
    (date(2026, 7, 14), "6:52 am", "7:23 pm", "work"),
    (date(2026, 7, 15), "7:00 am", "7:30 pm", "work"),
    (date(2026, 7, 16), "6:51 am", "7:14 pm", "work"),
    (date(2026, 7, 17), "6:53 am", "7:22 pm", "work"),
    (date(2026, 7, 18), "6:52 am", "7:21 pm", "work"),
    (date(2026, 7, 19), "6:52 am", "4:04 pm", "work"),  # Sunday worked
    (date(2026, 7, 20), "6:53 am", "7:08 pm", "work"),
    (date(2026, 7, 21), "6:53 am", "7:21 pm", "work"),
    (date(2026, 7, 22), "6:52 am", "7:12 pm", "work"),
    (date(2026, 7, 23), "6:50 am", "7:11 pm", "work"),
    (date(2026, 7, 24), "6:51 am", "7:15 pm", "work"),
    (date(2026, 7, 25), "6:49 am", "7:13 pm", "work"),
]

# A1P445: leave then night/day mix — punches only on work days
PUNCHES_445 = [
    *[(PERIOD_START + timedelta(days=i), None, None, "leave_annual") for i in range(0, 8)],  # 26 Jun–3 Jul
    (date(2026, 7, 4), "6:47 am", "7:01 pm", "work"),  # REGULAR day
    (date(2026, 7, 5), None, None, "off"),
    (date(2026, 7, 6), "6:51 pm", "7:00 am", "work_night"),
    (date(2026, 7, 7), "6:46 pm", "7:00 am", "work_night"),
    (date(2026, 7, 8), "6:46 pm", "7:01 am", "work_night"),
    (date(2026, 7, 9), "6:52 pm", "7:00 am", "work_night"),
    (date(2026, 7, 10), None, None, "leave_sick"),
    (date(2026, 7, 11), None, None, "absent"),
    (date(2026, 7, 12), None, None, "off"),
    (date(2026, 7, 13), "6:46 am", "7:02 pm", "work"),
    (date(2026, 7, 14), "6:45 am", "7:00 pm", "work"),
    (date(2026, 7, 15), "6:46 am", "7:03 pm", "work"),
    (date(2026, 7, 16), "6:45 am", "7:04 pm", "work"),
    (date(2026, 7, 17), "6:45 am", "7:05 pm", "work"),
    (date(2026, 7, 18), "6:48 am", "7:03 pm", "work"),
    (date(2026, 7, 19), "6:49 am", "3:29 pm", "work"),  # Sunday worked
    (date(2026, 7, 20), "6:50 pm", "7:02 am", "work_night"),
    (date(2026, 7, 21), "6:48 pm", "7:03 am", "work_night"),
    (date(2026, 7, 22), "6:46 pm", "7:03 am", "work_night"),
    (date(2026, 7, 23), "6:48 pm", "7:03 am", "work_night"),
    (date(2026, 7, 24), "6:49 pm", "7:02 am", "work_night"),
    (date(2026, 7, 25), "6:48 pm", "7:05 am", "work_night"),
]

PUNCHES_249 = [
    (date(2026, 6, 26), "6:58 am", "8:10 pm", "work"),
    (date(2026, 6, 27), "6:51 am", "9:50 pm", "work"),
    (date(2026, 6, 28), "7:37 am", "1:50 pm", "work"),
    (date(2026, 6, 29), "6:43 am", "7:42 pm", "work"),
    (date(2026, 6, 30), "6:59 am", "7:03 pm", "work"),
    (date(2026, 7, 1), "6:57 am", "7:18 pm", "work"),
    (date(2026, 7, 2), "7:00 am", "8:47 pm", "work"),
    (date(2026, 7, 3), "6:54 am", "8:00 pm", "work"),
    (date(2026, 7, 4), "6:56 am", "10:16 pm", "work"),
    (date(2026, 7, 5), "8:01 am", "6:42 pm", "work"),
    (date(2026, 7, 6), "6:56 am", "7:27 pm", "work"),
    (date(2026, 7, 7), "6:09 am", "7:50 pm", "work"),
    (date(2026, 7, 8), "6:45 am", "10:59 pm", "work"),
    (date(2026, 7, 9), "7:05 am", "7:11 pm", "work"),
    (date(2026, 7, 10), "6:52 am", "7:56 pm", "work"),
    (date(2026, 7, 11), "7:06 am", "8:53 pm", "work"),  # Ded 0.50 on sheet
    (date(2026, 7, 12), None, None, "off"),
    (date(2026, 7, 13), "6:38 am", "7:40 pm", "work"),
    (date(2026, 7, 14), "6:52 am", "8:59 pm", "work"),
    (date(2026, 7, 15), "7:07 am", "9:38 pm", "work"),  # Ded 0.50 on sheet
    (date(2026, 7, 16), "7:01 am", "10:11 pm", "work"),
    (date(2026, 7, 17), "6:57 am", "8:46 pm", "work"),
    (date(2026, 7, 18), "6:59 am", "7:05 pm", "work"),
    (date(2026, 7, 19), None, None, "off"),
    (date(2026, 7, 20), "6:12 am", "7:17 pm", "work"),
    (date(2026, 7, 21), "7:01 am", "8:08 pm", "work"),
    (date(2026, 7, 22), "7:01 am", "9:24 pm", "work"),
    (date(2026, 7, 23), "7:00 am", "7:04 pm", "work"),
    (date(2026, 7, 24), "7:03 am", "7:14 pm", "work"),
    (date(2026, 7, 25), "6:48 am", "9:10 pm", "work"),
]

PUNCH_MAP = {
    "A1P543": PUNCHES_543,
    "A1P142": PUNCHES_142,
    "A1P445": PUNCHES_445,
    "A1P249": PUNCHES_249,
}


def _create_employees(masters) -> dict:
    from people.models import Employee, OnboardingChecklist

    created = {}
    for spec in EMPLOYEES:
        emp, _ = Employee.objects.update_or_create(
            employee_code=spec["code"],
            defaults={
                "biometric_id": spec["bio"],
                "first_name": spec["first_name"],
                "last_name": spec["last_name"],
                "email": spec["email"],
                "phone_country_code": "+971",
                "phone": spec["phone"],
                "date_of_joining": date(2024, 1, 15),
                "status": Employee.Status.ACTIVE,
                "department": masters["dept"],
                "division": masters["division"],
                "location": masters["location"],
                "position": masters["positions"][spec["position"]],
            },
        )
        OnboardingChecklist.objects.get_or_create(
            employee=emp,
            defaults={
                "personal_info_done": True,
                "documents_done": True,
                "bank_done": True,
            },
        )
        created[spec["code"]] = emp
    return created


def _assign_shifts(employees: dict):
    from attendance.models import ShiftAssignment, WorkCalendar, WorkShift

    calendar = WorkCalendar.objects.get(code="UAE-STD")
    shifts = {s.code: s for s in WorkShift.objects.filter(code__in=["REGULAR", "DAYSHIFT", "NIGHTSHI", "DAY", "NIGHT", "GEN"])}

    # Clear prior sample assignments for these employees
    ShiftAssignment.objects.filter(employee__in=employees.values()).delete()

    def add(emp, shift_code, start, end=None):
        ShiftAssignment.objects.create(
            employee=emp,
            shift=shifts[shift_code],
            calendar=calendar,
            effective_from=start,
            effective_to=end,
            is_active=True,
        )

    # 543 / 142 / 249 — single shift whole period
    add(employees["A1P543"], "REGULAR", PERIOD_START, PERIOD_END)
    add(employees["A1P142"], "DAYSHIFT", PERIOD_START, PERIOD_END)
    add(employees["A1P249"], "DAYSHIFT", PERIOD_START, PERIOD_END)

    # 445 — leave period still assigned REGULAR, then night, day, night
    add(employees["A1P445"], "REGULAR", PERIOD_START, date(2026, 7, 5))
    add(employees["A1P445"], "NIGHTSHI", date(2026, 7, 6), date(2026, 7, 12))
    add(employees["A1P445"], "DAYSHIFT", date(2026, 7, 13), date(2026, 7, 19))
    add(employees["A1P445"], "NIGHTSHI", date(2026, 7, 20), PERIOD_END)


def _seed_leave(employees: dict):
    from leave.models import LeaveRequest, LeaveType
    from leave.services import approve_leave, get_or_create_balance

    annual = LeaveType.objects.filter(code="EL").first()
    sick = LeaveType.objects.filter(code="SL").first()
    if not annual or not sick:
        return 0

    from accounts.models import User

    reviewer = User.objects.filter(is_superuser=True).first()
    if not reviewer:
        return 0

    for emp in employees.values():
        for lt in (annual, sick):
            bal = get_or_create_balance(emp, lt, 2026)
            if bal.entitled < 30:
                bal.entitled = Decimal("30.0")
                bal.save(update_fields=["entitled", "updated_at"])

    created = 0
    LeaveRequest.objects.filter(
        employee__in=employees.values(),
        start_date__lte=PERIOD_END,
        end_date__gte=PERIOD_START,
        reason="PDF sample seed",
    ).delete()
    # Reset balances so re-seeding stays idempotent after deleting approved leave
    for emp in employees.values():
        for lt in (annual, sick):
            bal = get_or_create_balance(emp, lt, 2026)
            bal.pending = Decimal("0.0")
            bal.used = Decimal("0.0")
            if bal.entitled < 30:
                bal.entitled = Decimal("30.0")
            bal.save(update_fields=["pending", "used", "entitled", "updated_at"])

    def make(emp, lt, start, end):
        nonlocal created
        days = Decimal(str((end - start).days + 1))
        bal = get_or_create_balance(emp, lt, start.year)
        bal.pending = bal.pending + days
        bal.save(update_fields=["pending", "updated_at"])
        req = LeaveRequest.objects.create(
            employee=emp,
            leave_type=lt,
            start_date=start,
            end_date=end,
            days=days,
            status=LeaveRequest.Status.PENDING,
            apply_to_attendance=True,
            requested_by=reviewer,
            reason="PDF sample seed",
        )
        approve_leave(req, reviewer=reviewer, notes="Sample PDF seed")
        created += 1

    make(employees["A1P445"], annual, date(2026, 6, 26), date(2026, 7, 3))
    make(employees["A1P445"], sick, date(2026, 7, 10), date(2026, 7, 10))
    return created


def _ensure_salary(employees: dict):
    """Minimal salary structure so payroll OT can be demoed."""
    try:
        from payroll.models import SalaryComponent, SalaryStructure, SalaryStructureLine
        from payroll.services import seed_default_components
    except Exception:
        return 0

    seed_default_components()
    basic = SalaryComponent.objects.filter(code="BASIC").first()
    if not basic:
        return 0
    n = 0
    for emp in employees.values():
        st, created = SalaryStructure.objects.update_or_create(
            employee=emp,
            effective_from=date(2024, 1, 1),
            defaults={"currency": "AED", "notes": "PDF sample seed"},
        )
        SalaryStructureLine.objects.update_or_create(
            structure=st,
            component=basic,
            defaults={"amount": Decimal("2400.00")},
        )
        n += int(created)
    return n


def _clear_period_ops(employees: dict):
    from attendance.models import DailyAttendance, PunchLog

    emp_ids = [e.pk for e in employees.values()]
    PunchLog.objects.filter(
        employee_id__in=emp_ids,
        punched_at__date__gte=PERIOD_START,
        punched_at__date__lte=PERIOD_END + timedelta(days=1),
    ).delete()
    DailyAttendance.objects.filter(
        employee_id__in=emp_ids,
        date__gte=PERIOD_START,
        date__lte=PERIOD_END,
    ).delete()


def _seed_punches(employees: dict) -> int:
    from attendance.models import PunchLog

    count = 0
    for code, rows in PUNCH_MAP.items():
        emp = employees[code]
        for d, inn, out, kind in rows:
            if kind in ("off", "leave_annual", "leave_sick", "absent"):
                continue
            if not inn or not out:
                continue
            tin = _parse_ampm(inn)
            tout = _parse_ampm(out)
            PunchLog.objects.create(
                employee=emp,
                punched_at=_aware(d, tin),
                punch_type=PunchLog.PunchType.IN,
                source=PunchLog.Source.MANUAL,
            )
            count += 1
            out_date = d
            if kind == "work_night" or tout < tin:
                out_date = d + timedelta(days=1)
            PunchLog.objects.create(
                employee=emp,
                punched_at=_aware(out_date, tout),
                punch_type=PunchLog.PunchType.OUT,
                source=PunchLog.Source.MANUAL,
            )
            count += 1
    return count


def _generate_attendance(employees: dict) -> int:
    from attendance.engine import generate_daily_attendance
    from attendance.models import DailyAttendance

    rows = 0
    cur = PERIOD_START
    while cur <= PERIOD_END:
        for emp in employees.values():
            generate_daily_attendance(emp, cur, force=True)
            rows += 1
        cur += timedelta(days=1)

    emp445 = employees["A1P445"]
    DailyAttendance.objects.filter(employee=emp445, date=date(2026, 7, 11)).update(
        status=DailyAttendance.Status.ABSENT,
        worked_hours=Decimal("0"),
        payable_hours=Decimal("0"),
        overtime_hours=Decimal("0"),
        notes="Absent/",
    )
    return rows


@transaction.atomic
def seed_sample_pdf_people() -> dict:
    """
    Seed A1 PDF sample employees + punches + attendance for Jun26–Jul25 2026.
    """
    _ensure_foundation()
    masters = _masters()
    employees = _create_employees(masters)
    _assign_shifts(employees)
    _clear_period_ops(employees)
    punches = _seed_punches(employees)
    att_rows = _generate_attendance(employees)
    # Leave last so approve locks days as On leave (engine does not read LeaveRequest)
    leave_n = _seed_leave(employees)
    salary_n = _ensure_salary(employees)

    return {
        "sample_employees": len(employees),
        "sample_employee_codes": list(employees.keys()),
        "sample_period": f"{PERIOD_START.isoformat()} → {PERIOD_END.isoformat()}",
        "sample_punches": punches,
        "sample_attendance_rows": att_rows,
        "sample_leave_requests": leave_n,
        "sample_salary_structures": salary_n,
        "sample_company": "A1 PLASTIC INDUSTRY",
        "sample_cycle_start_day": 26,
    }
