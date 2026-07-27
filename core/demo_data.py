"""
Replace mock people/attendance with a clean 5-employee demo for the current month.

Destructive for operational people data (employees, punches, daily attendance,
shift assignments). Keeps Admin user, RBAC, and catalog seeds.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone


DEMO_EMPLOYEES = [
    {
        "code": "EMP001",
        "first_name": "Sara",
        "last_name": "Al Hashimi",
        "email": "sara.alhashimi@daypay.demo",
        "phone": "501234567",
        "dept": "HR",
        "position": "HRMGR",
        "bio": "1001",
        "is_manager": True,
    },
    {
        "code": "EMP002",
        "first_name": "Ahmed",
        "last_name": "Hassan",
        "email": "ahmed.hassan@daypay.demo",
        "phone": "502345678",
        "dept": "IT",
        "position": "SWE",
        "bio": "1002",
    },
    {
        "code": "EMP003",
        "first_name": "Priya",
        "last_name": "Nair",
        "email": "priya.nair@daypay.demo",
        "phone": "503456789",
        "dept": "FIN",
        "position": "ACCT",
        "bio": "1003",
    },
    {
        "code": "EMP004",
        "first_name": "James",
        "last_name": "Okonkwo",
        "email": "james.okonkwo@daypay.demo",
        "phone": "504567890",
        "dept": "OPS",
        "position": "OPSEX",
        "bio": "1004",
    },
    {
        "code": "EMP005",
        "first_name": "Fatima",
        "last_name": "Rahman",
        "email": "fatima.rahman@daypay.demo",
        "phone": "505678901",
        "dept": "HR",
        "position": "HREX",
        "bio": "1005",
    },
]


def _clear_people_ops():
    """Remove employees and related attendance/time ops (not RBAC/catalogs)."""
    from accounts.models import User
    from attendance.models import DailyAttendance, PunchLog, ShiftAssignment
    from people.models import Employee

    PunchLog.objects.all().delete()
    DailyAttendance.objects.all().delete()
    ShiftAssignment.objects.all().delete()

    # Collect linked logins before employee delete (SET_NULL on user)
    linked_ids = list(
        Employee.objects.exclude(user_id=None).values_list("user_id", flat=True)
    )
    Employee.objects.all().delete()

    # Drop orphaned demo logins; keep staff/superusers (admin)
    if linked_ids:
        User.objects.filter(pk__in=linked_ids, is_superuser=False, is_staff=False).delete()


def _ensure_masters():
    from attendance.ot import seed_overtime_sheet_rules
    from people.models import Department, Division, Location, Position

    # OVERTIME.xlsx policies + late tiers + DAY/NIGHT/OFFICE/DRIVER/GEN shifts
    seed_overtime_sheet_rules(include_std_policy=True)

    from attendance.models import WorkCalendar, WorkShift

    division, _ = Division.objects.update_or_create(
        code="CORP",
        defaults={"description": "Corporate", "is_active": True},
    )
    location, _ = Location.objects.update_or_create(
        code="DXB",
        defaults={"description": "Dubai Office", "is_active": True},
    )

    depts = {}
    for code, name in (
        ("HR", "Human Resources"),
        ("IT", "Information Technology"),
        ("FIN", "Finance"),
        ("OPS", "Operations"),
    ):
        depts[code], _ = Department.objects.update_or_create(
            code=code,
            defaults={
                "description": name,
                "division": division,
                "is_active": True,
            },
        )

    positions = {}
    for code, name in (
        ("HRMGR", "HR Manager"),
        ("HREX", "HR Executive"),
        ("SWE", "Software Engineer"),
        ("ACCT", "Accountant"),
        ("OPSEX", "Operations Executive"),
    ):
        positions[code], _ = Position.objects.update_or_create(
            code=code,
            defaults={"description": name, "is_active": True},
        )

    calendar = WorkCalendar.objects.get(code="UAE-STD")
    shift = WorkShift.objects.get(code="GEN")

    for dept in depts.values():
        changed = False
        if dept.default_shift_id != shift.pk:
            dept.default_shift = shift
            changed = True
        if dept.default_calendar_id != calendar.pk:
            dept.default_calendar = calendar
            changed = True
        if changed:
            dept.save(update_fields=["default_shift", "default_calendar", "updated_at"])

    return {
        "division": division,
        "location": location,
        "depts": depts,
        "positions": positions,
        "calendar": calendar,
        "shift": shift,
    }


def _create_employees(masters, join_on: date):
    from people.models import Employee, OnboardingChecklist

    created = []
    manager = None
    for spec in DEMO_EMPLOYEES:
        emp = Employee.objects.create(
            employee_code=spec["code"],
            biometric_id=spec["bio"],
            first_name=spec["first_name"],
            last_name=spec["last_name"],
            email=spec["email"],
            phone_country_code="+971",
            phone=spec["phone"],
            date_of_joining=join_on,
            status=Employee.Status.ACTIVE,
            department=masters["depts"][spec["dept"]],
            division=masters["division"],
            location=masters["location"],
            position=masters["positions"][spec["position"]],
        )
        OnboardingChecklist.objects.get_or_create(
            employee=emp,
            defaults={
                "personal_info_done": True,
                "documents_done": True,
                "bank_done": True,
                "shift_assigned": True,
            },
        )
        if spec.get("is_manager"):
            manager = emp
        created.append(emp)

    if manager:
        for emp in created:
            if emp.pk != manager.pk:
                emp.manager = manager
                emp.save(update_fields=["manager", "updated_at"])

    return created


def _assign_shifts(employees, masters, from_date: date):
    from attendance.models import ShiftAssignment

    for emp in employees:
        ShiftAssignment.objects.create(
            employee=emp,
            shift=masters["shift"],
            calendar=masters["calendar"],
            effective_from=from_date,
            is_active=True,
            notes="Demo assignment",
        )


def _seed_month_attendance(employees, month_start: date, through: date):
    """
    Create IN/OUT punches on working days from month_start through `through`,
    then generate DailyAttendance rows for the full month window.
    Includes a few incomplete punch cases for dashboard demos.
    """
    from attendance.engine import generate_daily_attendance
    from attendance.models import PunchLog

    tz = timezone.get_current_timezone()
    punch_count = 0

    last_weekday = through
    while last_weekday.weekday() >= 5:
        last_weekday -= timedelta(days=1)

    day = month_start
    while day <= through:
        if day.weekday() < 5:
            for i, emp in enumerate(employees):
                in_at = timezone.make_aware(
                    datetime.combine(day, time(8, 55 + (i % 5))), tz
                )
                out_at = timezone.make_aware(
                    datetime.combine(day, time(18, 2 + (i % 4))), tz
                )
                if emp.employee_code == "EMP002" and day.weekday() == 2:
                    in_at = timezone.make_aware(
                        datetime.combine(day, time(9, 25)), tz
                    )
                if emp.employee_code == "EMP004" and day.weekday() == 3:
                    out_at = timezone.make_aware(
                        datetime.combine(day, time(14, 30)), tz
                    )

                skip_out = False
                open_break = False
                # Last weekday: EMP003 / EMP005 missing Out
                if day == last_weekday and emp.employee_code in ("EMP003", "EMP005"):
                    skip_out = True
                # Earlier Tuesday: EMP002 break out without break in
                if emp.employee_code == "EMP002" and day.weekday() == 1 and day < last_weekday:
                    open_break = True

                PunchLog.objects.create(
                    employee=emp,
                    punched_at=in_at,
                    punch_type=PunchLog.PunchType.IN,
                    source=PunchLog.Source.MANUAL,
                )
                punch_count += 1

                if open_break:
                    PunchLog.objects.create(
                        employee=emp,
                        punched_at=timezone.make_aware(
                            datetime.combine(day, time(13, 5)), tz
                        ),
                        punch_type=PunchLog.PunchType.BREAK_OUT,
                        source=PunchLog.Source.MANUAL,
                    )
                    punch_count += 1
                    continue

                if not skip_out:
                    PunchLog.objects.create(
                        employee=emp,
                        punched_at=out_at,
                        punch_type=PunchLog.PunchType.OUT,
                        source=PunchLog.Source.MANUAL,
                    )
                    punch_count += 1
        day += timedelta(days=1)

    att_count = 0
    day = month_start
    while day <= through:
        for emp in employees:
            generate_daily_attendance(emp, day, force=True)
            att_count += 1
        day += timedelta(days=1)

    return {"punches": punch_count, "attendance_rows": att_count}


@transaction.atomic
def seed_demo_people(*, through: date | None = None) -> dict:
    """
    Wipe existing employees/attendance and load 5 demo staff + GEN shift +
    this month's attendance (from the 1st through today by default).
    """
    today = timezone.localdate()
    through = through or today
    month_start = date(today.year, today.month, 1)
    if through < month_start:
        through = month_start
    # Join a bit before the month so assignments are valid
    join_on = month_start - timedelta(days=30)

    _clear_people_ops()
    masters = _ensure_masters()
    employees = _create_employees(masters, join_on)
    _assign_shifts(employees, masters, join_on)
    att = _seed_month_attendance(employees, month_start, through)

    return {
        "employees": len(employees),
        "employee_codes": [e.employee_code for e in employees],
        "shift": masters["shift"].code,
        "calendar": masters["calendar"].code,
        "attendance_from": month_start.isoformat(),
        "attendance_through": through.isoformat(),
        **att,
    }
