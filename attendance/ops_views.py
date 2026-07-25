"""Holidays, punch devices, punches, daily attendance UI."""

from datetime import datetime

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.permissions import permission_required, request_has_perm
from core.pagination import paginate

from .engine import generate_attendance_for_date, generate_daily_attendance
from .forms import (
    DailyAttendanceEditForm,
    DayPunchEditForm,
    DayPunchForm,
    DeviceEnrollForm,
    GenerateAttendanceForm,
    HolidayForm,
    ManualPunchForm,
    PunchDeviceForm,
    PunchImportForm,
)
from .models import DailyAttendance, DeviceCommand, Holiday, PunchDevice, PunchLog
from . import day_punches as punch_ops
from .punch_issues import analyze_punches
from . import zkteco as zk


# —— Holidays ——


@permission_required("attendance.manage_calendars")
def holiday_list(request):
    qs = Holiday.objects.select_related("location")
    year = request.GET.get("year", "").strip()
    q = request.GET.get("q", "").strip()
    if year.isdigit():
        qs = qs.filter(date__year=int(year))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return render(
        request,
        "attendance/holiday_list.html",
        {
            "page_title": "Holidays",
            "page_obj": paginate(request, qs),
            "q": q,
            "year": year,
            "years": list(range(timezone.localdate().year + 1, timezone.localdate().year - 5, -1)),
        },
    )


@permission_required("attendance.manage_calendars")
@require_http_methods(["GET", "POST"])
def holiday_create(request):
    form = HolidayForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Holiday created.")
        return redirect("attendance:holiday_list")
    return render(
        request,
        "attendance/holiday_form.html",
        {"page_title": "New holiday", "form": form},
    )


@permission_required("attendance.manage_calendars")
@require_http_methods(["GET", "POST"])
def holiday_edit(request, pk):
    obj = get_object_or_404(Holiday, pk=pk)
    form = HolidayForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Holiday updated.")
        return redirect("attendance:holiday_list")
    return render(
        request,
        "attendance/holiday_form.html",
        {"page_title": f"Edit {obj.name}", "form": form, "object": obj},
    )


@permission_required("attendance.manage_calendars")
@require_http_methods(["POST"])
def holiday_delete(request, pk):
    obj = get_object_or_404(Holiday, pk=pk)
    obj.delete()
    messages.success(request, "Holiday deleted.")
    return redirect("attendance:holiday_list")


# —— Punch devices ——


@permission_required("attendance.manage_devices")
def device_list(request):
    qs = PunchDevice.objects.select_related("location")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(lan_host__icontains=q)
        )
    return render(
        request,
        "attendance/device_list.html",
        {"page_title": "Punch devices", "page_obj": paginate(request, qs), "q": q},
    )


@permission_required("attendance.manage_devices")
@require_http_methods(["GET", "POST"])
def device_create(request):
    form = PunchDeviceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        device = form.save()
        if device.vendor == PunchDevice.Vendor.ZKTECO:
            messages.success(
                request,
                f"Device {device.code} created. Point the iFace ADMS server to Day Pay "
                f"and set SN to {device.serial_number or 'the machine serial'}.",
            )
        else:
            messages.success(
                request,
                f"Device {device.code} created. Copy the API token now — machines use it to push punches.",
            )
        return redirect("attendance:device_detail", pk=device.pk)
    return render(
        request,
        "attendance/device_form.html",
        {"page_title": "New punch device", "form": form},
    )


@permission_required("attendance.manage_devices")
def device_detail(request, pk):
    device = get_object_or_404(PunchDevice.objects.select_related("location"), pk=pk)
    recent = PunchLog.objects.filter(device=device).select_related("employee")[:20]
    commands = DeviceCommand.objects.filter(device=device).order_by("-created_at")[:15]
    adms_base = request.build_absolute_uri("/iclock/").rstrip("/")
    enroll_form = DeviceEnrollForm() if device.vendor == PunchDevice.Vendor.ZKTECO else None
    return render(
        request,
        "attendance/device_detail.html",
        {
            "page_title": f"Device · {device.code}",
            "device": device,
            "recent": recent,
            "commands": commands,
            "ingest_url": request.build_absolute_uri("/api/attendance/punches/"),
            "adms_base_url": adms_base,
            "adms_cdata_url": f"{adms_base}/cdata",
            "enroll_form": enroll_form,
        },
    )


@permission_required("attendance.manage_devices")
@require_http_methods(["GET", "POST"])
def device_edit(request, pk):
    device = get_object_or_404(PunchDevice, pk=pk)
    form = PunchDeviceForm(request.POST or None, instance=device)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Device updated.")
        return redirect("attendance:device_detail", pk=device.pk)
    return render(
        request,
        "attendance/device_form.html",
        {"page_title": f"Edit {device.code}", "form": form, "object": device},
    )


@permission_required("attendance.manage_devices")
@require_http_methods(["POST"])
def device_rotate_token(request, pk):
    import secrets

    device = get_object_or_404(PunchDevice, pk=pk)
    device.api_token = secrets.token_urlsafe(32)
    device.save(update_fields=["api_token", "updated_at"])
    messages.success(request, "API token rotated. Update the machine config.")
    return redirect("attendance:device_detail", pk=device.pk)


@permission_required("attendance.manage_devices")
@require_http_methods(["POST"])
def device_sync_time(request, pk):
    device = get_object_or_404(PunchDevice, pk=pk)
    if device.vendor != PunchDevice.Vendor.ZKTECO:
        messages.error(request, "Time sync is for ZKTeco ADMS devices.")
        return redirect("attendance:device_detail", pk=device.pk)
    if not device.serial_number:
        messages.error(request, "Set the device serial number (SN) before syncing time.")
        return redirect("attendance:device_detail", pk=device.pk)
    cmd = zk.queue_time_sync(device)
    messages.success(
        request,
        f"Time sync queued ({cmd.command}). The machine applies it on the next ADMS poll.",
    )
    return redirect("attendance:device_detail", pk=device.pk)


@permission_required("attendance.manage_devices")
@require_http_methods(["POST"])
def device_check(request, pk):
    device = get_object_or_404(PunchDevice, pk=pk)
    if device.vendor != PunchDevice.Vendor.ZKTECO or not device.serial_number:
        messages.error(request, "CHECK requires a ZKTeco device with serial number.")
        return redirect("attendance:device_detail", pk=device.pk)
    zk.queue_check(device)
    messages.success(request, "CHECK queued — device will report on next poll.")
    return redirect("attendance:device_detail", pk=device.pk)


@permission_required("attendance.manage_devices")
@require_http_methods(["POST"])
def device_enroll(request, pk):
    """Push user / trigger face or finger enroll on ZKTeco ADMS device."""
    device = get_object_or_404(PunchDevice, pk=pk)
    if device.vendor != PunchDevice.Vendor.ZKTECO:
        messages.error(request, "Enrollment is only for ZKTeco ADMS devices.")
        return redirect("attendance:device_detail", pk=device.pk)
    form = DeviceEnrollForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            "Select an employee with a biometric / device ID, then choose an action.",
        )
        return redirect("attendance:device_detail", pk=device.pk)

    employee = form.cleaned_data["employee"]
    action = form.cleaned_data["action"]
    try:
        if action == DeviceEnrollForm.ACTION_ADD:
            zk.queue_user_upsert(device, employee)
            messages.success(
                request,
                f"User {employee.full_name} (PIN {zk.employee_device_pin(employee)}) "
                "queued for the machine.",
            )
        elif action == DeviceEnrollForm.ACTION_FINGER:
            zk.queue_enroll_finger(device, employee)
            messages.success(
                request,
                f"Fingerprint enroll queued for {employee.full_name}. "
                "Ask them to stand at the iFace when it prompts.",
            )
        elif action == DeviceEnrollForm.ACTION_FACE:
            zk.queue_enroll_face(device, employee)
            messages.success(
                request,
                f"Face enroll queued for {employee.full_name}. "
                "Ask them to face the iFace when it prompts.",
            )
        elif action == DeviceEnrollForm.ACTION_REMOVE:
            zk.queue_user_delete(device, employee)
            messages.success(
                request,
                f"Remove user queued for {employee.full_name} on this machine.",
            )
        elif action == "sync_bio":
            templates = employee.bio_templates.count()
            if not templates:
                messages.error(
                    request,
                    "No stored face/finger templates for this employee yet. "
                    "Enroll on a device first so templates sync to Day Pay.",
                )
            else:
                zk.queue_push_bio_templates(device, employee)
                messages.success(
                    request,
                    f"Pushed {templates} bio template(s) for {employee.full_name} to {device.code}.",
                )
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("attendance:device_detail", pk=device.pk)


@permission_required("attendance.manage_devices")
@require_http_methods(["POST"])
def device_delete(request, pk):
    device = get_object_or_404(PunchDevice, pk=pk)
    code = device.code
    device.delete()
    messages.success(request, f"Device {code} deleted.")
    return redirect("attendance:device_list")


# —— Punches ——


@permission_required("attendance.view")
def punch_list(request):
    qs = PunchLog.objects.select_related("employee", "device")
    q = request.GET.get("q", "").strip()
    day = request.GET.get("date", "").strip()
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(device__code__icontains=q)
        )
    if day:
        try:
            d = datetime.strptime(day, "%Y-%m-%d").date()
            qs = qs.filter(punched_at__date=d)
        except ValueError:
            pass
    return render(
        request,
        "attendance/punch_list.html",
        {
            "page_title": "Punches",
            "page_obj": paginate(request, qs, per_page=50),
            "q": q,
            "day": day,
        },
    )


@permission_required("attendance.manage")
@require_http_methods(["GET", "POST"])
def punch_create(request):
    form = ManualPunchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        punch = form.save(commit=False)
        punch.source = PunchLog.Source.MANUAL
        punch.created_by = request.user
        punch.save()
        generate_daily_attendance(punch.employee, timezone.localtime(punch.punched_at).date())
        messages.success(request, "Punch recorded.")
        return redirect("attendance_ops:punch_list")
    return render(
        request,
        "attendance/punch_form.html",
        {"page_title": "Add punch", "form": form},
    )


@permission_required("attendance.manage")
@require_http_methods(["POST"])
def punch_delete(request, pk):
    punch = get_object_or_404(PunchLog.objects.select_related("employee"), pk=pk)
    day = timezone.localtime(punch.punched_at).date()
    emp = punch.employee
    punch.delete()
    generate_daily_attendance(emp, day, force=True)
    messages.success(request, "Punch deleted and attendance refreshed.")
    return redirect("attendance_ops:punch_list")


@permission_required("attendance.manage")
@require_http_methods(["GET", "POST"])
def punch_import(request):
    import csv
    import io

    from .adapters import (
        VENDOR_FORMATS,
        map_punch_type,
        parse_datetime,
        parse_vendor_csv_rows,
        resolve_employee,
    )

    form = PunchImportForm(request.POST or None, request.FILES or None)
    results = None
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["file"].read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            messages.error(request, "CSV has no data rows.")
            return redirect("attendance_ops:punch_import")

        fmt = form.cleaned_data["format"]
        normalized = parse_vendor_csv_rows(rows, fmt)
        default_device = form.cleaned_data.get("device")
        ok, errors = 0, []
        touched = set()

        for i, item in enumerate(normalized, start=2):
            employee = resolve_employee(
                employee_code=item.get("employee_code") or "",
                biometric_id=item.get("biometric_id") or "",
            )
            if not employee:
                errors.append(
                    f"Row {i}: unknown employee "
                    f"(code={item.get('employee_code')!r} bio={item.get('biometric_id')!r})"
                )
                continue
            try:
                punched_at = parse_datetime(item.get("punched_at"))
            except ValueError as exc:
                errors.append(f"Row {i}: {exc}")
                continue
            ptype = map_punch_type(item.get("punch_type"))
            PunchLog.objects.create(
                employee=employee,
                punched_at=punched_at,
                punch_type=ptype,
                device=default_device,
                source=PunchLog.Source.IMPORT,
                external_id=item.get("external_id") or "",
                created_by=request.user,
            )
            touched.add((employee.pk, timezone.localtime(punched_at).date()))
            ok += 1

        from people.models import Employee as Emp

        for emp_id, day in touched:
            generate_daily_attendance(Emp.objects.get(pk=emp_id), day, force=True)

        results = {"ok": ok, "errors": errors[:40], "error_count": len(errors)}
        if ok:
            messages.success(request, f"Imported {ok} punch(es).")
        if errors:
            messages.warning(request, f"{len(errors)} row(s) failed.")

    return render(
        request,
        "attendance/punch_import.html",
        {
            "page_title": "Import punches",
            "form": form,
            "results": results,
            "formats": VENDOR_FORMATS,
        },
    )


@permission_required("attendance.manage")
def punch_import_sample(request, format_key):
    import csv

    from django.http import Http404, HttpResponse

    from .adapters import VENDOR_FORMATS

    cfg = VENDOR_FORMATS.get(format_key)
    if not cfg:
        raise Http404("Unknown format")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="punches_{format_key}_sample.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(cfg["sample_headers"])
    for row in cfg["sample_rows"]:
        writer.writerow(row)
    return response


# —— Daily attendance ——


@permission_required("attendance.view")
def daily_list(request):
    from people.models import Department

    qs = DailyAttendance.objects.select_related(
        "employee", "employee__department", "shift", "holiday"
    )
    day = request.GET.get("date", "").strip() or str(timezone.localdate())
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    department_id = request.GET.get("department", "").strip()
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
        qs = qs.filter(date=d)
    except ValueError:
        d = timezone.localdate()
        qs = qs.filter(date=d)
        day = str(d)

    day_qs = qs
    counts = day_qs.aggregate(
        present=Count("id", filter=Q(status=DailyAttendance.Status.PRESENT)),
        absent=Count("id", filter=Q(status=DailyAttendance.Status.ABSENT)),
        half=Count("id", filter=Q(status=DailyAttendance.Status.HALF_DAY)),
        missing=Count("id", filter=Q(status=DailyAttendance.Status.MISSING_PUNCH)),
        leave=Count("id", filter=Q(status=DailyAttendance.Status.ON_LEAVE)),
        off=Count(
            "id",
            filter=Q(
                status__in=[
                    DailyAttendance.Status.WEEKLY_OFF,
                    DailyAttendance.Status.HOLIDAY,
                ]
            ),
        ),
        locked=Count("id", filter=Q(is_locked=True)),
        total=Count("id"),
    )
    status_counts = {k: counts[k] or 0 for k in counts}

    if department_id.isdigit():
        qs = qs.filter(employee__department_id=int(department_id))
    if q:
        qs = qs.filter(
            Q(employee__employee_code__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(employee__department__description__icontains=q)
            | Q(employee__department__code__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by("employee__employee_code", "employee__first_name")
    prev_day = d.fromordinal(d.toordinal() - 1)
    next_day = d.fromordinal(d.toordinal() + 1)

    return render(
        request,
        "attendance/daily_list.html",
        {
            "page_title": "Daily attendance",
            "page_obj": paginate(request, qs, per_page=50),
            "day": day,
            "day_date": d,
            "prev_day": prev_day,
            "next_day": next_day,
            "q": q,
            "status": status,
            "department_id": department_id,
            "departments": Department.objects.filter(is_active=True).order_by("code"),
            "statuses": DailyAttendance.Status.choices,
            "status_counts": status_counts,
            "can_manage": request_has_perm(request, "attendance.manage"),
            "gen_form": GenerateAttendanceForm(initial={"date": day}),
        },
    )


@permission_required("attendance.manage")
@require_http_methods(["POST"])
def daily_generate(request):
    form = GenerateAttendanceForm(request.POST)
    if form.is_valid():
        on_date = form.cleaned_data["date"]
        force = form.cleaned_data.get("force", False)
        rows = generate_attendance_for_date(on_date, force=force)
        messages.success(request, f"Generated attendance for {len(rows)} employee(s) on {on_date}.")
        return redirect(f"{reverse('attendance_ops:daily_list')}?date={on_date}")
    messages.error(request, "Invalid generate form.")
    return redirect("attendance_ops:daily_list")


@permission_required("attendance.view")
@require_http_methods(["GET", "POST"])
def daily_detail(request, pk):
    row = get_object_or_404(
        DailyAttendance.objects.select_related(
            "employee", "shift", "calendar", "holiday"
        ),
        pk=pk,
    )
    can_manage = request_has_perm(request, "attendance.manage")
    punches = punch_ops.day_punches(row.employee, row.date)
    punch_issues = analyze_punches(punches)
    form = DailyAttendanceEditForm(instance=row)
    punch_form = DayPunchForm(
        initial={"punch_type": PunchLog.PunchType.OUT}, prefix="punch"
    )
    editing_punch = None
    edit_punch_form = None

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "You cannot edit attendance.")
            return redirect("attendance_ops:daily_detail", pk=pk)

        action = request.POST.get("action") or "save"

        if action == "lock":
            row.is_locked = True
            row.save(update_fields=["is_locked", "updated_at"])
            messages.success(request, "Day locked.")
            return redirect("attendance_ops:daily_detail", pk=pk)

        if action == "unlock":
            row.is_locked = False
            row.save(update_fields=["is_locked", "updated_at"])
            messages.success(request, "Day unlocked.")
            return redirect("attendance_ops:daily_detail", pk=pk)

        if action == "regen":
            if row.is_locked:
                messages.error(request, "Unlock before recalculating.")
            else:
                generate_daily_attendance(row.employee, row.date, force=True)
                messages.success(request, "Attendance recalculated from punches.")
            return redirect("attendance_ops:daily_detail", pk=pk)

        if row.is_locked and action in (
            "save",
            "add_punch",
            "edit_punch",
            "start_edit_punch",
            "delete_punch",
            "fix_missing_out",
            "fix_missing_break_in",
        ):
            messages.error(request, "Day is locked. Unlock before editing.")
            return redirect("attendance_ops:daily_detail", pk=pk)

        if action == "save":
            form = DailyAttendanceEditForm(request.POST, instance=row)
            if form.is_valid():
                form.save()
                messages.success(request, "Attendance updated.")
                return redirect("attendance_ops:daily_detail", pk=pk)

        elif action == "add_punch":
            punch_form = DayPunchForm(request.POST, prefix="punch")
            if punch_form.is_valid():
                punch_ops.add_day_punch(
                    row.employee,
                    row.date,
                    punch_time=punch_form.cleaned_data["punch_time"],
                    punch_type=punch_form.cleaned_data["punch_type"],
                    user=request.user,
                    notes=punch_form.cleaned_data.get("notes") or "",
                )
                messages.success(request, "Punch added and attendance recalculated.")
                return redirect("attendance_ops:daily_detail", pk=pk)
            messages.error(request, "Could not add punch — check time and type.")

        elif action == "start_edit_punch":
            editing_punch = get_object_or_404(
                PunchLog, pk=request.POST.get("punch_id"), employee=row.employee
            )
            local = timezone.localtime(editing_punch.punched_at)
            edit_punch_form = DayPunchEditForm(
                initial={
                    "punch_id": editing_punch.pk,
                    "punch_time": local.time().replace(microsecond=0),
                    "punch_type": editing_punch.punch_type,
                    "notes": editing_punch.notes,
                },
                prefix="edit",
            )

        elif action == "edit_punch":
            edit_punch_form = DayPunchEditForm(request.POST, prefix="edit")
            if edit_punch_form.is_valid():
                punch = get_object_or_404(
                    PunchLog,
                    pk=edit_punch_form.cleaned_data["punch_id"],
                    employee=row.employee,
                )
                punch_ops.update_day_punch(
                    punch,
                    punch_time=edit_punch_form.cleaned_data["punch_time"],
                    punch_type=edit_punch_form.cleaned_data["punch_type"],
                    notes=edit_punch_form.cleaned_data.get("notes") or "",
                )
                messages.success(request, "Punch updated and attendance recalculated.")
                return redirect("attendance_ops:daily_detail", pk=pk)
            editing_punch = get_object_or_404(
                PunchLog,
                pk=request.POST.get("edit-punch_id") or request.POST.get("punch_id"),
                employee=row.employee,
            )
            messages.error(request, "Could not update punch — check time and type.")

        elif action == "delete_punch":
            punch = get_object_or_404(
                PunchLog, pk=request.POST.get("punch_id"), employee=row.employee
            )
            punch_ops.delete_day_punch(punch)
            messages.success(request, "Punch deleted.")
            return redirect("attendance_ops:daily_detail", pk=pk)

        elif action == "fix_missing_out":
            _, msg = punch_ops.quick_fix_missing_out(
                row.employee, row.date, user=request.user
            )
            messages.success(request, msg)
            return redirect("attendance_ops:daily_detail", pk=pk)

        elif action == "fix_missing_break_in":
            _, msg = punch_ops.quick_fix_missing_break_in(
                row.employee, row.date, user=request.user
            )
            messages.success(request, msg)
            return redirect("attendance_ops:daily_detail", pk=pk)

    row.refresh_from_db()
    punches = punch_ops.day_punches(row.employee, row.date)
    punch_issues = analyze_punches(punches)
    issue_codes = {i.code for i in punch_issues}

    # Re-bind attendance form only when save validation failed
    if not (request.method == "POST" and request.POST.get("action") == "save" and form.errors):
        form = DailyAttendanceEditForm(instance=row)

    return render(
        request,
        "attendance/daily_detail.html",
        {
            "page_title": f"Attendance · {row.employee.employee_code}",
            "row": row,
            "form": form,
            "punches": punches,
            "punch_form": punch_form,
            "edit_punch_form": edit_punch_form,
            "editing_punch": editing_punch,
            "punch_issues": punch_issues,
            "can_manage": can_manage,
            "can_fix_out": bool(
                issue_codes & {"missing_out", "single_punch", "open_segment"}
            ),
            "can_fix_break": "missing_break_in" in issue_codes,
            "list_href": reverse("attendance_ops:daily_list")
            + f"?date={row.date.isoformat()}",
            "register_href": reverse(
                "attendance_ops:register_day",
                args=[row.employee_id, row.date.isoformat()],
            ),
        },
    )


@permission_required("attendance.manage")
@require_http_methods(["POST"])
def daily_regen(request, pk):
    row = get_object_or_404(DailyAttendance, pk=pk)
    if row.is_locked:
        messages.error(request, "Unlock the day before recalculating.")
        return redirect("attendance_ops:daily_detail", pk=pk)
    generate_daily_attendance(row.employee, row.date, force=True)
    messages.success(request, "Attendance recalculated from punches.")
    return redirect("attendance_ops:daily_detail", pk=pk)
