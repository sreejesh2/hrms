from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import permission_required
from core.pagination import paginate

from .forms import (
    ShiftAssignmentForm,
    WorkCalendarForm,
    WorkShiftForm,
    WorkShiftVersionForm,
    OvertimePolicyForm,
)
from .models import ShiftAssignment, WorkCalendar, WorkShift, WorkShiftVersion, OvertimePolicy


# —— Work calendars ——


@permission_required("attendance.manage_calendars")
def calendar_list(request):
    qs = WorkCalendar.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    return render(
        request,
        "attendance/calendar_list.html",
        {
            "page_title": "Work calendars",
            "page_obj": paginate(request, qs),
            "q": q,
        },
    )


@permission_required("attendance.manage_calendars")
@require_http_methods(["GET", "POST"])
def calendar_create(request):
    form = WorkCalendarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Work calendar created.")
        return redirect("attendance:calendar_list")
    return render(
        request,
        "attendance/calendar_form.html",
        {"page_title": "New work calendar", "form": form},
    )


@permission_required("attendance.manage_calendars")
@require_http_methods(["GET", "POST"])
def calendar_edit(request, pk):
    obj = get_object_or_404(WorkCalendar, pk=pk)
    form = WorkCalendarForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Work calendar updated.")
        return redirect("attendance:calendar_list")
    return render(
        request,
        "attendance/calendar_form.html",
        {"page_title": f"Edit {obj.code}", "form": form, "object": obj},
    )


@permission_required("attendance.manage_calendars")
@require_http_methods(["POST"])
def calendar_delete(request, pk):
    obj = get_object_or_404(WorkCalendar, pk=pk)
    obj.delete()
    messages.success(request, "Work calendar deleted.")
    return redirect("attendance:calendar_list")


# —— Work shifts (Shift Master) ——


@permission_required("attendance.manage_shifts")
def shift_list(request):
    qs = WorkShift.objects.prefetch_related(
        Prefetch(
            "versions",
            queryset=WorkShiftVersion.objects.order_by("-effective_from", "-id"),
        )
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    return render(
        request,
        "attendance/shift_list.html",
        {
            "page_title": "Work shifts",
            "page_obj": paginate(request, qs),
            "q": q,
        },
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def shift_create(request):
    shift_form = WorkShiftForm(request.POST or None, prefix="shift")
    version_form = WorkShiftVersionForm(request.POST or None, prefix="ver")
    if request.method == "POST" and shift_form.is_valid() and version_form.is_valid():
        shift = shift_form.save()
        version = version_form.save(commit=False)
        version.shift = shift
        version.created_by = request.user
        version.save()
        messages.success(request, f"Shift {shift.code} created.")
        return redirect("attendance:shift_detail", pk=shift.pk)
    return render(
        request,
        "attendance/shift_form.html",
        {
            "page_title": "New work shift",
            "shift_form": shift_form,
            "version_form": version_form,
            "is_create": True,
        },
    )


@permission_required("attendance.manage_shifts")
def shift_detail(request, pk):
    shift = get_object_or_404(
        WorkShift.objects.select_related("ot_policy").prefetch_related("versions"), pk=pk
    )
    versions = shift.versions.all()
    current = versions.first()
    return render(
        request,
        "attendance/shift_detail.html",
        {
            "page_title": f"Shift · {shift.code}",
            "shift": shift,
            "versions": versions,
            "current": current,
        },
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def shift_edit(request, pk):
    shift = get_object_or_404(WorkShift, pk=pk)
    shift_form = WorkShiftForm(request.POST or None, instance=shift, prefix="shift")
    if request.method == "POST" and shift_form.is_valid():
        shift_form.save()
        messages.success(request, "Shift updated.")
        return redirect("attendance:shift_detail", pk=shift.pk)
    return render(
        request,
        "attendance/shift_edit.html",
        {"page_title": f"Edit {shift.code}", "shift_form": shift_form, "shift": shift},
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def shift_version_add(request, pk):
    shift = get_object_or_404(WorkShift, pk=pk)
    current = shift.current_version()
    initial = {}
    if current and request.method == "GET":
        initial = {
            "shift_from": current.shift_from,
            "shift_to": current.shift_to,
            "day_span": current.day_span,
            "break_from": current.break_from,
            "break_to": current.break_to,
            "notes": current.notes,
            "calc_attendance_by_work_hrs": current.calc_attendance_by_work_hrs,
            "single_punch_at_shift_start": current.single_punch_at_shift_start,
            "punch_shift_and_break_start": current.punch_shift_and_break_start,
            "attendance_by_first_in_last_punch": current.attendance_by_first_in_last_punch,
        }
    form = WorkShiftVersionForm(
        request.POST or None, initial=initial, shift=shift
    )
    if request.method == "POST" and form.is_valid():
        version = form.save(commit=False)
        version.shift = shift
        version.created_by = request.user
        version.save()
        messages.success(request, "Shift version added.")
        return redirect("attendance:shift_detail", pk=shift.pk)
    return render(
        request,
        "attendance/shift_version_form.html",
        {
            "page_title": f"New version · {shift.code}",
            "form": form,
            "shift": shift,
        },
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["POST"])
def shift_delete(request, pk):
    shift = get_object_or_404(WorkShift, pk=pk)
    code = shift.code
    shift.delete()
    messages.success(request, f"Shift {code} deleted.")
    return redirect("attendance:shift_list")


# —— Manage shift assignments ——


@permission_required("attendance.manage_shifts")
def assignment_list(request):
    qs = ShiftAssignment.objects.select_related(
        "employee", "employee__department", "shift", "calendar"
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(shift__code__icontains=q)
        )
    return render(
        request,
        "attendance/assignment_list.html",
        {
            "page_title": "Manage shifts",
            "page_obj": paginate(request, qs),
            "q": q,
        },
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def assignment_create(request):
    form = ShiftAssignmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from .services import assign_employee_shift

        data = form.cleaned_data
        assign_employee_shift(
            employee=data["employee"],
            shift=data["shift"],
            calendar=data.get("calendar"),
            effective_from=data["effective_from"],
            notes=data.get("notes") or "",
            replace_overlapping=True,
        )
        messages.success(request, "Shift assignment created.")
        return redirect("attendance:assignment_list")
    return render(
        request,
        "attendance/assignment_form.html",
        {"page_title": "Assign shift", "form": form},
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def assignment_edit(request, pk):
    obj = get_object_or_404(
        ShiftAssignment.objects.select_related("employee", "shift", "calendar"), pk=pk
    )
    form = ShiftAssignmentForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Shift assignment updated.")
        return redirect("attendance:assignment_list")
    return render(
        request,
        "attendance/assignment_form.html",
        {"page_title": "Edit assignment", "form": form, "object": obj},
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["POST"])
def assignment_delete(request, pk):
    obj = get_object_or_404(ShiftAssignment, pk=pk)
    obj.delete()
    messages.success(request, "Assignment deleted.")
    return redirect("attendance:assignment_list")


def _employee_bulk_queryset(request):
    from people.models import Employee

    qs = Employee.objects.filter(
        status__in=[
            Employee.Status.ACTIVE,
            Employee.Status.DRAFT,
            Employee.Status.ON_LEAVE,
        ]
    ).select_related("department", "location").order_by("employee_code")
    q = request.GET.get("q", "").strip()
    department_id = request.GET.get("department", "").strip()
    location_id = request.GET.get("location", "").strip()
    missing = request.GET.get("missing") == "1"
    if q:
        qs = qs.filter(
            Q(employee_code__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    if department_id.isdigit():
        qs = qs.filter(department_id=int(department_id))
    if location_id.isdigit():
        qs = qs.filter(location_id=int(location_id))
    if missing:
        qs = qs.exclude(shift_assignments__is_active=True).distinct()
    return qs, q, department_id, location_id, missing


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def assignment_bulk(request):
    from django.utils import timezone

    from people.models import Department, Location

    from .forms import BulkShiftAssignForm
    from .services import assign_employee_shift

    employees_qs, q, department_id, location_id, missing = _employee_bulk_queryset(
        request
    )
    matching_count = employees_qs.count()
    page_obj = paginate(request, employees_qs, per_page=50)
    form = BulkShiftAssignForm(
        request.POST or None,
        initial={"effective_from": timezone.localdate(), "replace_overlapping": True},
    )

    if request.method == "POST" and form.is_valid():
        assign_all = form.cleaned_data.get("assign_all_matching")
        if assign_all:
            targets = list(employees_qs)
        else:
            raw_ids = (form.cleaned_data.get("employee_ids") or "").strip()
            ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]
            if not ids:
                messages.error(request, "Select at least one employee, or use Assign all matching.")
                return redirect(
                    request.get_full_path()
                    if request.GET
                    else "attendance:assignment_bulk"
                )
            targets = list(employees_qs.filter(pk__in=ids))

        created = 0
        for emp in targets:
            assign_employee_shift(
                employee=emp,
                shift=form.cleaned_data["shift"],
                calendar=form.cleaned_data.get("calendar"),
                effective_from=form.cleaned_data["effective_from"],
                notes="Bulk assign",
                replace_overlapping=form.cleaned_data.get("replace_overlapping", True),
            )
            created += 1
        messages.success(request, f"Assigned shift to {created} employee(s).")
        return redirect("attendance:assignment_list")

    return render(
        request,
        "attendance/assignment_bulk.html",
        {
            "page_title": "Bulk assign shifts",
            "page_obj": page_obj,
            "form": form,
            "q": q,
            "department_id": department_id,
            "location_id": location_id,
            "missing": missing,
            "matching_count": matching_count,
            "departments": Department.objects.filter(is_active=True).order_by("code"),
            "locations": Location.objects.filter(is_active=True).order_by("code"),
        },
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def assignment_import(request):
    import csv
    import io
    from datetime import datetime

    from people.models import Employee

    from .forms import ShiftAssignmentImportForm
    from .services import assign_employee_shift

    form = ShiftAssignmentImportForm(request.POST or None, request.FILES or None)
    results = None

    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["file"].read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            messages.error(request, "CSV has no header row.")
            return redirect("attendance:assignment_import")

        # normalize headers
        field_map = {h.strip().lower(): h for h in reader.fieldnames if h}
        required = ("employee_code", "shift_code", "effective_from")
        missing_cols = [c for c in required if c not in field_map]
        if missing_cols:
            messages.error(
                request,
                f"Missing columns: {', '.join(missing_cols)}. "
                "Need employee_code, shift_code, effective_from.",
            )
            return redirect("attendance:assignment_import")

        shifts = {s.code.upper(): s for s in WorkShift.objects.filter(is_active=True)}
        calendars = {
            c.code.upper(): c for c in WorkCalendar.objects.filter(is_active=True)
        }
        ok, errors = 0, []
        replace = form.cleaned_data.get("replace_overlapping", True)

        for i, row in enumerate(reader, start=2):
            def cell(key):
                src = field_map.get(key)
                return (row.get(src) or "").strip() if src else ""

            emp_code = cell("employee_code")
            shift_code = cell("shift_code").upper()
            cal_code = cell("calendar_code").upper()
            eff = cell("effective_from")
            notes = cell("notes")

            if not emp_code and not shift_code and not eff:
                continue
            try:
                employee = Employee.objects.get(employee_code__iexact=emp_code)
            except Employee.DoesNotExist:
                errors.append(f"Row {i}: unknown employee_code “{emp_code}”")
                continue
            shift = shifts.get(shift_code)
            if not shift:
                errors.append(f"Row {i}: unknown shift_code “{shift_code}”")
                continue
            calendar = None
            if cal_code:
                calendar = calendars.get(cal_code)
                if not calendar:
                    errors.append(f"Row {i}: unknown calendar_code “{cal_code}”")
                    continue
            try:
                effective_from = datetime.strptime(eff, "%Y-%m-%d").date()
            except ValueError:
                errors.append(f"Row {i}: effective_from must be YYYY-MM-DD (got “{eff}”)")
                continue
            try:
                assign_employee_shift(
                    employee=employee,
                    shift=shift,
                    calendar=calendar,
                    effective_from=effective_from,
                    notes=notes or "CSV import",
                    replace_overlapping=replace,
                )
                ok += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Row {i}: {exc}")

        results = {"ok": ok, "errors": errors[:50], "error_count": len(errors)}
        if ok:
            messages.success(request, f"Imported {ok} assignment(s).")
        if errors:
            messages.warning(request, f"{len(errors)} row(s) failed.")

    return render(
        request,
        "attendance/assignment_import.html",
        {
            "page_title": "Import shift assignments",
            "form": form,
            "results": results,
        },
    )


@permission_required("attendance.manage_shifts")
def assignment_import_sample(request):
    import csv

    from django.http import HttpResponse

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="shift_assignments_sample.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        ["employee_code", "shift_code", "calendar_code", "effective_from", "notes"]
    )
    writer.writerow(["E001", "REG", "STD", "2026-01-01", "Office"])
    return response


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def assignment_apply_defaults(request):
    from people.models import Employee

    from .forms import ApplyDepartmentDefaultsForm
    from .services import apply_department_defaults

    form = ApplyDepartmentDefaultsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dept = form.cleaned_data["department"]
        qs = Employee.objects.filter(
            department=dept,
            status__in=[
                Employee.Status.ACTIVE,
                Employee.Status.DRAFT,
                Employee.Status.ON_LEAVE,
            ],
        )
        only_missing = form.cleaned_data.get("only_without_assignment", True)
        eff = form.cleaned_data.get("effective_from")
        applied = 0
        for emp in qs.select_related("department"):
            result = apply_department_defaults(
                emp, effective_from=eff, only_if_missing=only_missing
            )
            if result:
                applied += 1
        messages.success(
            request,
            f"Applied {dept.code} defaults to {applied} employee(s).",
        )
        return redirect("attendance:assignment_list")

    return render(
        request,
        "attendance/assignment_apply_defaults.html",
        {"page_title": "Apply department defaults", "form": form},
    )


# —— Overtime policies ——


@permission_required("attendance.manage_shifts")
def ot_policy_list(request):
    qs = OvertimePolicy.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    return render(
        request,
        "attendance/ot_policy_list.html",
        {
            "page_title": "Overtime policies",
            "page_obj": paginate(request, qs),
            "q": q,
        },
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["GET", "POST"])
def ot_policy_edit(request, pk=None):
    obj = get_object_or_404(OvertimePolicy, pk=pk) if pk else None
    form = OvertimePolicyForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Overtime policy saved.")
        return redirect("attendance:ot_policy_list")
    return render(
        request,
        "attendance/ot_policy_form.html",
        {
            "page_title": f"Edit {obj.code}" if obj else "New OT policy",
            "form": form,
            "object": obj,
        },
    )


@permission_required("attendance.manage_shifts")
@require_http_methods(["POST"])
def ot_policy_delete(request, pk):
    obj = get_object_or_404(OvertimePolicy, pk=pk)
    if obj.is_default:
        messages.error(request, "Cannot delete the default OT policy. Set another default first.")
        return redirect("attendance:ot_policy_list")
    obj.delete()
    messages.success(request, "Overtime policy deleted.")
    return redirect("attendance:ot_policy_list")