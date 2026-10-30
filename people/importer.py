"""Bulk employee import from an HR system CSV export.

Matching is by employee code: a code already in Day Pay is updated, a new code
is created. Re-importing the same file therefore never creates duplicates.
Division / department / position masters are matched by description (case and
spacing ignored) and created once when missing. Each employee's biometric ID
is the number at the end of the employee code (A1P104 → 104), because that is
the user PIN enrolled on the punch machines.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from .models import Department, Division, Employee, OnboardingChecklist, Position

# Column name in the file → field. First match wins; names compared normalised.
COLUMN_ALIASES = {
    "code": ("code", "employee_code", "emp_code", "empcode"),
    "name": ("empname", "name", "employee_name", "full_name"),
    "division": ("div_desc", "division"),
    "department": ("dep_descr", "dep_desc", "department"),
    "position": ("pos_descr", "pos_desc", "position", "designation"),
    "joined": ("join_date", "date_of_joining", "joining_date", "doj"),
    "active": ("active_stat", "active", "status"),
    "work": ("work_stat", "work_status"),
    "shift": ("shift_stat", "shift", "shift_code"),
}
REQUIRED_COLUMNS = ("code", "name")

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y")


@dataclass
class ImportRow:
    line: int
    code: str
    name: str = ""
    division: str = ""
    department: str = ""
    position: str = ""
    joined: date | None = None
    status: str = Employee.Status.ACTIVE
    shift: str = ""
    biometric_id: str = ""
    action: str = "create"  # create | update | unchanged | error
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportPlan:
    rows: list[ImportRow]
    file_errors: list[str]
    new_masters: dict[str, list[str]]

    def count(self, action):
        return sum(1 for r in self.rows if r.action == action)

    @property
    def counts(self):
        return Counter(r.action for r in self.rows)

    @property
    def warning_rows(self):
        return [r for r in self.rows if r.warnings and r.action != "error"]

    @property
    def error_rows(self):
        return [r for r in self.rows if r.action == "error"]

    @property
    def can_apply(self):
        return not self.file_errors and any(
            r.action in ("create", "update") for r in self.rows
        )


def _clean(value) -> str:
    """Trim and collapse whitespace, including line breaks inside cells."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value) -> str:
    return _clean(value).casefold()


def _header_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _clean(value).lower()).strip("_")


def decode_upload(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _parse_date(value: str) -> date | None:
    text = _clean(value).split(" ")[0]
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Joining date {value!r} is not DD/MM/YYYY")


def _parse_status(active: str, work: str) -> str:
    active, work = _key(active), _key(work)
    if active and active not in ("active", "yes", "y", "1"):
        return Employee.Status.INACTIVE
    if work and work not in ("working", "work"):
        # e.g. "Vacation" / "On leave" — still employed, away right now
        return Employee.Status.ON_LEAVE
    return Employee.Status.ACTIVE


def biometric_from_code(code: str) -> str:
    """Machine PIN for an employee code: trailing digits without leading zeros."""
    match = re.search(r"(\d+)$", code or "")
    if not match:
        return ""
    return str(int(match.group(1)))


def split_name(full: str) -> tuple[str, str]:
    parts = _clean(full).split(" ", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def _master_lookup(model) -> dict[str, object]:
    return {_key(obj.description): obj for obj in model.objects.all()}


def build_plan(text: str) -> ImportPlan:
    """Read the file and decide what would happen to each row. Saves nothing."""
    reader = csv.DictReader(io.StringIO(text))
    headers = {_header_key(h): h for h in (reader.fieldnames or [])}
    columns = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in headers:
                columns[target] = headers[alias]
                break
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        return ImportPlan(
            rows=[],
            file_errors=[
                "Missing column(s): "
                + ", ".join(COLUMN_ALIASES[c][0].upper() for c in missing)
            ],
            new_masters={},
        )

    rows: list[ImportRow] = []
    for line, raw in enumerate(reader, start=2):
        get = lambda k: _clean(raw.get(columns[k], "")) if k in columns else ""  # noqa: E731
        code = get("code").upper()
        if not code and not any(_clean(v) for v in raw.values()):
            continue  # blank line
        row = ImportRow(
            line=line,
            code=code,
            name=get("name"),
            division=get("division"),
            department=get("department"),
            position=get("position"),
            shift=get("shift").upper(),
            status=_parse_status(get("active"), get("work")),
        )
        row.biometric_id = biometric_from_code(row.code)
        if not row.code:
            row.errors.append("Employee code is empty")
        elif len(row.code) > 32:
            row.errors.append("Employee code is longer than 32 characters")
        if not row.name:
            row.errors.append("Name is empty")
        try:
            row.joined = _parse_date(get("joined"))
        except ValueError as exc:
            row.errors.append(str(exc))
        rows.append(row)

    if not rows:
        return ImportPlan(rows=[], file_errors=["The file has no employee rows."], new_masters={})

    # Same code twice in the file: neither row is safe to import.
    code_counts = Counter(r.code for r in rows if r.code)
    for r in rows:
        if code_counts.get(r.code, 0) > 1:
            r.errors.append(f"Code {r.code} appears more than once in the file")
    bio_counts = Counter(r.biometric_id for r in rows if r.biometric_id)
    for r in rows:
        if r.code and not r.biometric_id:
            r.errors.append(f"Code {r.code} has no number at the end to use as machine ID")
        elif bio_counts.get(r.biometric_id, 0) > 1:
            others = sorted(
                x.code for x in rows if x.biometric_id == r.biometric_id and x is not r
            )
            r.errors.append(
                f"Machine ID {r.biometric_id} would also be used by {', '.join(others)}"
            )

    existing = {
        e.employee_code.upper(): e
        for e in Employee.objects.select_related("division", "department", "position")
    }
    bio_owner = {
        e.biometric_id.upper(): e.employee_code.upper()
        for e in existing.values()
        if e.biometric_id
    }
    for r in rows:
        if r.errors:
            continue
        owner = bio_owner.get(r.biometric_id.upper())
        if owner and owner != r.code:
            r.errors.append(
                f"Machine ID {r.biometric_id} is already used by employee {owner}"
            )
            continue
        current = existing.get(r.code)
        if current is None:
            r.action = "create"
        elif _row_matches(r, current):
            r.action = "unchanged"
        else:
            r.action = "update"

    for r in rows:
        if r.errors:
            r.action = "error"

    _flag_odd_divisions(rows)

    new_masters = {}
    for label, model, attr in (
        ("Divisions", Division, "division"),
        ("Departments", Department, "department"),
        ("Positions", Position, "position"),
    ):
        known = _master_lookup(model)
        seen = {}
        for r in rows:
            value = getattr(r, attr)
            if r.action != "error" and value and _key(value) not in known:
                seen.setdefault(_key(value), value)
        if seen:
            new_masters[label] = sorted(seen.values(), key=str.casefold)

    new_shifts = sorted(
        {r.shift for r in rows if r.shift and r.action != "error"} - _known_shift_codes()
    )
    if new_shifts:
        new_masters["Shifts (set their times after import)"] = new_shifts

    return ImportPlan(rows=rows, file_errors=[], new_masters=new_masters)


def _row_matches(row: ImportRow, emp: Employee) -> bool:
    first, last = split_name(row.name)
    return (
        emp.first_name == first
        and emp.last_name == last
        and emp.date_of_joining == row.joined
        and emp.status == row.status
        and emp.biometric_id == row.biometric_id
        and _key(emp.division.description if emp.division else "") == _key(row.division)
        and _key(emp.department.description if emp.department else "") == _key(row.department)
        and _key(emp.position.description if emp.position else "") == _key(row.position)
    )


def _flag_odd_divisions(rows):
    """Warn when a department sits under a division most of its people don't."""
    by_dept = defaultdict(Counter)
    for r in rows:
        if r.department and r.division and r.action != "error":
            by_dept[_key(r.department)][_key(r.division)] += 1
    for r in rows:
        counts = by_dept.get(_key(r.department))
        if not counts or len(counts) < 2 or r.action == "error":
            continue
        usual, usual_n = counts.most_common(1)[0]
        if _key(r.division) != usual and counts[_key(r.division)] < usual_n:
            usual_label = next(
                x.division for x in rows if _key(x.division) == usual
            )
            r.warnings.append(
                f"Department {r.department} is usually under division "
                f"{usual_label}, but this row says {r.division}"
            )


def _known_shift_codes() -> set[str]:
    from attendance.models import WorkShift

    return {c.upper() for c in WorkShift.objects.values_list("code", flat=True)}


def _unique_code(model, description: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "-", description.upper()).strip("-")[:28] or "X"
    code, n = base, 1
    while model.objects.filter(code=code).exists():
        n += 1
        code = f"{base[:28 - len(str(n)) - 1]}-{n}"
    return code


def _get_or_create_master(model, cache, description, **extra):
    if not description:
        return None
    obj = cache.get(_key(description))
    if obj is None:
        obj = model.objects.create(
            code=_unique_code(model, description),
            description=description,
            **extra,
        )
        cache[_key(description)] = obj
    return obj


@transaction.atomic
def apply_plan(plan: ImportPlan) -> dict:
    """Create / update employees from a plan built by build_plan()."""
    from attendance.models import ShiftAssignment, WorkShift
    from attendance.services import assign_employee_shift

    divisions = _master_lookup(Division)
    departments = _master_lookup(Department)
    positions = _master_lookup(Position)
    shifts = {s.code.upper(): s for s in WorkShift.objects.all()}
    today = timezone.localdate()

    created = updated = shifts_set = shifts_created = 0
    for r in plan.rows:
        if r.action not in ("create", "update"):
            continue
        division = _get_or_create_master(Division, divisions, r.division)
        department = _get_or_create_master(
            Department, departments, r.department, division=division
        )
        position = _get_or_create_master(Position, positions, r.position)
        first, last = split_name(r.name)

        emp = Employee.objects.filter(employee_code__iexact=r.code).first()
        is_new = emp is None
        if is_new:
            emp = Employee(employee_code=r.code)
        emp.first_name = first
        emp.last_name = last
        emp.biometric_id = r.biometric_id
        emp.division = division
        emp.department = department
        emp.position = position
        emp.date_of_joining = r.joined
        emp.status = r.status
        emp.save()
        if is_new:
            OnboardingChecklist.objects.get_or_create(employee=emp)
            created += 1
        else:
            updated += 1

        shift = shifts.get(r.shift) if r.shift else None
        if r.shift and shift is None:
            # Created without times: punches still count; late / OT need the
            # times, which HR adds under Settings → Time → Shifts.
            shift = WorkShift.objects.create(
                code=r.shift[:32], name=f"{r.shift} (from import — set times)"
            )
            shifts[r.shift] = shift
            shifts_created += 1
        if shift:
            current = (
                ShiftAssignment.objects.filter(employee=emp, is_active=True)
                .order_by("-effective_from", "-id")
                .first()
            )
            if not current or current.shift_id != shift.pk:
                # New staff: shift from joining date. Existing staff: a changed
                # shift applies from today so past attendance is not rewritten.
                start = (r.joined if is_new else None) or today
                assign_employee_shift(
                    employee=emp,
                    shift=shift,
                    calendar=department.default_calendar if department else None,
                    effective_from=start,
                    notes="Assigned by employee import",
                    replace_overlapping=True,
                    refresh_attendance=False,
                )
                onboarding = OnboardingChecklist.objects.get(employee=emp)
                if not onboarding.shift_assigned:
                    onboarding.shift_assigned = True
                    onboarding.save(update_fields=["shift_assigned", "updated_at"])
                shifts_set += 1

    return {
        "created": created,
        "updated": updated,
        "shifts": shifts_set,
        "shifts_created": shifts_created,
    }
