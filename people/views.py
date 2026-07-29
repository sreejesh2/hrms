from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.permissions import permission_required, request_has_perm
from core.pagination import paginate

from .forms import (
    EmployeeCreateLoginForm,
    EmployeeDocumentForm,
    EmployeeDynamicAttributesForm,
    EmployeeForm,
    EmployeeResetPasswordForm,
)
from .models import (
    Department,
    Employee,
    EmployeeAttributeDefinition,
    EmployeeDocument,
    Location,
    OnboardingChecklist,
    Position,
)
from .services import (
    LoginProvisionError,
    provision_employee_login,
    reset_employee_login_password,
    unlink_employee_login,
)

VALID_TABS = (
    "overview",
    "documents",
    "attributes",
    "salary",
    "attendance",
    "leave",
    "performance",
    "onboarding",
)


def _can_manage(request):
    return request_has_perm(request, "people.manage_employees")


def _profile_period(request):
    """Return a valid attendance cycle selected from profile query parameters."""
    from setup.cycles import period_bounds, period_for_date

    today = timezone.localdate()
    default_year, default_month, _, _ = period_for_date(today)
    try:
        year = int(request.GET.get("year", default_year))
        month = int(request.GET.get("month", default_month))
        if not 2000 <= year <= 2100 or not 1 <= month <= 12:
            raise ValueError
    except (TypeError, ValueError):
        year, month = default_year, default_month
    start, end = period_bounds(year, month)
    return year, month, start, end


def _shift_month(year, month, delta):
    month += delta
    while month < 1:
        year -= 1
        month += 12
    while month > 12:
        year += 1
        month -= 12
    return year, month


def _apply_employee_filters(qs, request):
    """Search + department / location / position filters from GET."""
    q = request.GET.get("q", "").strip()
    department_id = request.GET.get("department", "").strip()
    location_id = request.GET.get("location", "").strip()
    position_id = request.GET.get("position", "").strip()

    if q:
        qs = qs.filter(
            Q(employee_code__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(biometric_id__icontains=q)
        )
    if department_id.isdigit():
        qs = qs.filter(department_id=int(department_id))
    if location_id.isdigit():
        qs = qs.filter(location_id=int(location_id))
    if position_id.isdigit():
        qs = qs.filter(position_id=int(position_id))

    return qs, {
        "q": q,
        "department_id": department_id,
        "location_id": location_id,
        "position_id": position_id,
        "departments": Department.objects.filter(is_active=True).order_by("code"),
        "locations": Location.objects.filter(is_active=True).order_by("code"),
        "positions": Position.objects.filter(is_active=True).order_by("code"),
    }


def _list_context(request, page_obj, page_title, list_kind, filters=None):
    ctx = {
        "page_title": page_title,
        "page_obj": page_obj,
        "list_kind": list_kind,
        "can_manage": _can_manage(request),
        "q": "",
        "department_id": "",
        "location_id": "",
        "position_id": "",
        "departments": [],
        "locations": [],
        "positions": [],
    }
    if filters:
        ctx.update(filters)
    return ctx


@permission_required("people.view_employees")
def employee_list(request):
    qs, filters = _apply_employee_filters(Employee.objects.for_list(), request)
    page_obj = paginate(request, qs)
    return render(
        request,
        "people/employee_list.html",
        _list_context(request, page_obj, "Employees", "all", filters),
    )


@permission_required("people.view_employees")
def active_list(request):
    qs, filters = _apply_employee_filters(Employee.objects.active(), request)
    page_obj = paginate(request, qs)
    return render(
        request,
        "people/employee_list.html",
        _list_context(request, page_obj, "Active employees", "active", filters),
    )


@permission_required("people.view_employees")
def vacation_list(request):
    qs, filters = _apply_employee_filters(Employee.objects.on_vacation(), request)
    page_obj = paginate(request, qs)
    return render(
        request,
        "people/employee_list.html",
        _list_context(request, page_obj, "Employees on vacation", "vacation", filters),
    )


@permission_required("people.view_onboarding")
def onboarding_list(request):
    qs = Employee.objects.for_list().filter(status=Employee.Status.DRAFT)
    qs, filters = _apply_employee_filters(qs, request)
    page_obj = paginate(request, qs)
    return render(
        request,
        "people/employee_list.html",
        _list_context(request, page_obj, "Onboarding", "onboarding", filters),
    )


@permission_required("people.manage_employees")
@require_http_methods(["GET", "POST"])
def employee_create(request):
    form = EmployeeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        employee = form.save()
        OnboardingChecklist.objects.get_or_create(employee=employee)
        from attendance.services import apply_department_defaults

        if apply_department_defaults(employee, only_if_missing=True):
            messages.success(
                request,
                f"Employee {employee.employee_code} created with department default shift.",
            )
        else:
            messages.success(request, f"Employee {employee.employee_code} created.")
        return redirect("people:employee_detail", pk=employee.pk)
    return render(
        request,
        "people/employee_form.html",
        {"page_title": "Add employee", "form": form, "is_create": True},
    )


@permission_required("people.manage_employees")
@require_http_methods(["GET", "POST"])
def employee_edit(request, pk):
    employee = get_object_or_404(Employee.objects.for_detail(), pk=pk)
    form = EmployeeForm(request.POST or None, instance=employee)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Employee updated.")
        return redirect("people:employee_detail", pk=employee.pk)
    return render(
        request,
        "people/employee_form.html",
        {
            "page_title": f"Edit {employee.full_name}",
            "form": form,
            "employee": employee,
            "is_create": False,
        },
    )


@permission_required("people.view_employees")
@require_http_methods(["GET", "POST"])
def employee_detail(request, pk):
    employee = get_object_or_404(Employee.objects.for_detail(), pk=pk)
    tab = request.GET.get("tab", "overview")
    if tab not in VALID_TABS:
        tab = "overview"

    can_edit = _can_manage(request)
    definitions = EmployeeAttributeDefinition.objects.filter(is_active=True)
    onboarding, _ = OnboardingChecklist.objects.get_or_create(employee=employee)

    attr_form = None
    doc_form = None

    if tab == "attributes" and can_edit:
        attr_form = EmployeeDynamicAttributesForm(
            employee, definitions, request.POST or None
        )
        if request.method == "POST" and request.POST.get("form_kind") == "attributes":
            if attr_form.is_valid():
                attr_form.save()
                messages.success(request, "Additional attributes saved.")
                return redirect(f"{request.path}?tab=attributes")
            messages.error(request, "Please fix the errors below.")

    if tab == "documents" and can_edit:
        doc_form = EmployeeDocumentForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and request.POST.get("form_kind") == "document":
            if doc_form.is_valid():
                doc = doc_form.save(commit=False)
                doc.employee = employee
                doc.save()
                if not onboarding.documents_done:
                    onboarding.documents_done = True
                    onboarding.save(update_fields=["documents_done", "updated_at"])
                messages.success(request, "Document uploaded.")
                return redirect(f"{request.path}?tab=documents")
            messages.error(request, "Could not upload document. Check the form.")

    if tab == "onboarding" and can_edit and request.method == "POST":
        if request.POST.get("form_kind") == "onboarding":
            onboarding.personal_info_done = bool(request.POST.get("personal_info_done"))
            onboarding.documents_done = bool(request.POST.get("documents_done"))
            onboarding.bank_done = bool(request.POST.get("bank_done"))
            onboarding.shift_assigned = bool(request.POST.get("shift_assigned"))
            onboarding.save()
            messages.success(request, "Onboarding checklist updated.")
            step = (request.POST.get("wizard_step") or "1").strip()
            try:
                nxt = min(4, max(1, int(step) + 1))
            except ValueError:
                nxt = 1
            if onboarding.progress_pct >= 100:
                return redirect(f"{request.path}?tab=onboarding&step=4")
            return redirect(f"{request.path}?tab=onboarding&step={nxt}")

    value_map = {v.definition_id: v.value for v in employee.attribute_values.all()}
    custom_rows = [
        {
            "label": d.label,
            "value": value_map.get(d.pk, ""),
            "type": d.field_type,
        }
        for d in definitions
    ]

    tabs = [
        {"key": "overview", "label": "Overview"},
        {"key": "documents", "label": "Documents", "count": len(employee.documents.all())},
        {"key": "attributes", "label": "Custom fields", "count": len(custom_rows)},
        {"key": "salary", "label": "Salary"},
        {"key": "attendance", "label": "Attendance"},
        {"key": "leave", "label": "Leave"},
        {"key": "performance", "label": "Performance"},
        {"key": "onboarding", "label": "Onboarding", "count": f"{onboarding.progress_pct}%"},
    ]

    current_salary = None
    gratuity = None
    payslips = []
    can_manage_payroll = request_has_perm(request, "payroll.manage")
    can_view_payroll = request_has_perm(request, "payroll.view")
    attendance_rows = []
    attendance_summary = {}
    attendance_year = None
    attendance_month = None
    attendance_period_start = None
    attendance_period_end = None
    attendance_prev = None
    attendance_next = None
    can_view_attendance = request_has_perm(request, "attendance.view")
    can_manage_attendance = request_has_perm(request, "attendance.manage")
    performance_reviews = []
    can_manage_performance = request_has_perm(request, "performance.manage")
    leave_balances = []
    leave_requests = []
    leave_year = timezone.localdate().year
    leave_available = None
    performance_count = 0

    if tab == "salary":
        from payroll.gratuity import estimate_gratuity
        from payroll.models import Payslip
        from payroll.services import current_structure

        struct = current_structure(employee)
        gratuity = estimate_gratuity(employee)
        payslips = list(
            Payslip.objects.filter(employee=employee)
            .select_related("period")
            .order_by("-period__year", "-period__month")[:24]
        )
        if struct:
            current_salary = {
                "pk": struct.pk,
                "basic": struct.basic_amount(),
                "gross": struct.earnings_total(),
                "net": struct.net_preview(),
                "from": struct.effective_from,
                "currency": struct.currency,
                "lines": struct.resolved_lines(),
            }

    if tab == "attendance" and can_view_attendance:
        from attendance.models import DailyAttendance

        (
            attendance_year,
            attendance_month,
            attendance_period_start,
            attendance_period_end,
        ) = _profile_period(request)
        attendance_prev = _shift_month(attendance_year, attendance_month, -1)
        attendance_next = _shift_month(attendance_year, attendance_month, 1)
        records = list(
            DailyAttendance.objects.filter(
                employee=employee,
                date__gte=attendance_period_start,
                date__lte=attendance_period_end,
            )
            .select_related("shift")
            .order_by("date")
        )
        totals = {
            row["status"]: row["count"]
            for row in DailyAttendance.objects.filter(
                employee=employee,
                date__gte=attendance_period_start,
                date__lte=attendance_period_end,
            )
            .values("status")
            .annotate(count=Count("id"))
        }
        attendance_rows = records
        attendance_summary = {
            "present": totals.get(DailyAttendance.Status.PRESENT, 0),
            "absent": totals.get(DailyAttendance.Status.ABSENT, 0),
            "half_day": totals.get(DailyAttendance.Status.HALF_DAY, 0),
            "leave": totals.get(DailyAttendance.Status.ON_LEAVE, 0),
            "off": totals.get(DailyAttendance.Status.WEEKLY_OFF, 0)
            + totals.get(DailyAttendance.Status.HOLIDAY, 0),
            "missing": totals.get(DailyAttendance.Status.MISSING_PUNCH, 0),
            "worked_hours": sum((row.worked_hours for row in records), start=0),
            "overtime_hours": sum((row.overtime_hours for row in records), start=0),
        }

    if tab in ("leave", "overview"):
        from leave.models import LeaveBalance, LeaveRequest

        leave_balances = list(
            LeaveBalance.objects.filter(employee=employee, year=leave_year)
            .select_related("leave_type")
            .order_by("leave_type__name")
        )
        leave_requests = list(
            LeaveRequest.objects.filter(employee=employee)
            .select_related("leave_type")
            .order_by("-created_at")[:15]
        )
        leave_available = sum((b.available for b in leave_balances), start=0)
        try:
            leave_available = round(float(leave_available), 2)
        except (TypeError, ValueError):
            leave_available = leave_available


    if tab == "performance" or tab == "overview":
        from performance.models import PerformanceReview

        perf_qs = PerformanceReview.objects.filter(employee=employee)
        performance_count = perf_qs.count()
        if tab == "performance":
            performance_reviews = list(
                perf_qs.select_related("cycle", "manager").order_by(
                    "-cycle__start_date", "-created_at"
                )[:20]
            )

    can_manage_devices = request_has_perm(request, "attendance.manage_devices")
    zk_devices = []
    if tab == "overview" and can_manage_devices:
        from attendance.models import PunchDevice

        zk_devices = list(
            PunchDevice.objects.filter(
                vendor=PunchDevice.Vendor.ZKTECO, is_active=True
            ).order_by("code")
        )

    onboard_step = (request.GET.get("step") or "1").strip()
    if onboard_step not in ("1", "2", "3", "4"):
        onboard_step = "1"

    return render(
        request,
        "people/employee_detail.html",
        {
            "page_title": employee.full_name,
            "employee": employee,
            "tab": tab,
            "tabs": tabs,
            "can_edit": can_edit,
            "attr_form": attr_form,
            "doc_form": doc_form,
            "custom_rows": custom_rows,
            "documents": employee.documents.all(),
            "onboarding": onboarding,
            "onboard_step": onboard_step,
            "current_salary": current_salary,
            "gratuity": gratuity,
            "payslips": payslips,
            "can_manage_payroll": can_manage_payroll,
            "can_view_payroll": can_view_payroll,
            "attendance_rows": attendance_rows,
            "attendance_summary": attendance_summary,
            "attendance_year": attendance_year,
            "attendance_month": attendance_month,
            "attendance_period_start": attendance_period_start,
            "attendance_period_end": attendance_period_end,
            "attendance_prev": attendance_prev,
            "attendance_next": attendance_next,
            "can_view_attendance": can_view_attendance,
            "can_manage_attendance": can_manage_attendance,
            "performance_reviews": performance_reviews,
            "can_manage_performance": can_manage_performance,
            "can_manage_devices": can_manage_devices,
            "zk_devices": zk_devices,
            "leave_balances": leave_balances,
            "leave_requests": leave_requests,
            "leave_year": leave_year,
            "leave_available": leave_available,
            "performance_count": performance_count,
        },
    )


@permission_required("attendance.view")
def employee_attendance_export(request, pk, fmt):
    """Download the selected employee attendance cycle from the profile."""
    from types import SimpleNamespace

    from reports.builders.attendance import build_employee_attendance_sheet
    from reports.export import export_response

    employee = get_object_or_404(Employee, pk=pk)
    year, month, start, end = _profile_period(request)
    form = SimpleNamespace(
        cleaned_data={"employee": employee, "year": year, "month": month},
        period_bounds=(start, end),
    )
    try:
        return export_response(build_employee_attendance_sheet(form), fmt)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        url = reverse("people:employee_detail", args=[employee.pk])
        return redirect(f"{url}?tab=attendance&year={year}&month={month}")


@permission_required("payroll.view")
def employee_payroll_export(request, pk, fmt):
    """Download an employee's payroll history as Excel or PDF."""
    from reports.document import ReportDocument, ReportSheet
    from reports.export import export_response

    employee = get_object_or_404(Employee, pk=pk)
    rows = [
        [
            slip.period.short_label,
            slip.get_status_display(),
            slip.paid_days,
            slip.unpaid_days,
            slip.ot_hours,
            slip.ot_amount,
            slip.earnings_total,
            slip.deductions_total,
            slip.net_pay,
            slip.currency,
        ]
        for slip in employee.payslips.select_related("period").order_by(
            "-period__year", "-period__month"
        )
    ]
    doc = ReportDocument(
        title="Employee payroll history",
        subtitle=f"{employee.employee_code} · {employee.full_name}",
        filename=f"payroll_{employee.employee_code}",
        sheets=[
            ReportSheet(
                "Payroll",
                [
                    "Period",
                    "Status",
                    "Paid days",
                    "Unpaid days",
                    "OT hours",
                    "OT amount",
                    "Earnings",
                    "Deductions",
                    "Net pay",
                    "Currency",
                ],
                rows,
                money_cols=(6, 7, 8, 9),
            )
        ],
    )
    try:
        return export_response(doc, fmt)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        url = reverse("people:employee_detail", args=[employee.pk])
        return redirect(f"{url}?tab=salary")


@permission_required("attendance.manage_devices")
@require_http_methods(["POST"])
def employee_device_enroll(request, pk):
    """Queue add / face / finger enroll for this employee on a ZKTeco device."""
    from attendance import zkteco as zk
    from attendance.models import PunchDevice

    employee = get_object_or_404(Employee, pk=pk)
    device = get_object_or_404(
        PunchDevice,
        pk=request.POST.get("device_id"),
        vendor=PunchDevice.Vendor.ZKTECO,
        is_active=True,
    )
    action = (request.POST.get("action") or "add").strip()
    try:
        if action == "add":
            zk.queue_user_upsert(device, employee)
            messages.success(
                request,
                f"User queued on {device.code} (PIN {zk.employee_device_pin(employee)}).",
            )
        elif action == "finger":
            zk.queue_enroll_finger(device, employee)
            messages.success(
                request,
                f"Fingerprint enroll queued on {device.code}. Capture happens on the machine.",
            )
        elif action == "face":
            zk.queue_enroll_face(device, employee)
            messages.success(
                request,
                f"Face enroll queued on {device.code}. Capture happens on the machine.",
            )
        elif action == "sync_bio":
            n = employee.bio_templates.count()
            if not n:
                messages.error(
                    request,
                    "No stored templates yet — enroll face/finger on a device first.",
                )
            else:
                zk.queue_push_bio_templates(device, employee)
                messages.success(
                    request,
                    f"Pushed {n} template(s) to {device.code}.",
                )
        elif action == "remove":
            zk.queue_user_delete(device, employee)
            messages.success(request, f"Remove user queued on {device.code}.")
        else:
            messages.error(request, "Unknown action.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("people:employee_detail", pk=employee.pk)


@permission_required("people.manage_employees")
@require_http_methods(["POST"])
def document_delete(request, pk, doc_id):
    employee = get_object_or_404(Employee, pk=pk)
    doc = get_object_or_404(EmployeeDocument, pk=doc_id, employee=employee)
    doc.file.delete(save=False)
    doc.delete()
    messages.success(request, "Document deleted.")
    return redirect(
        f"{reverse('people:employee_detail', args=[employee.pk])}?tab=documents"
    )


@permission_required("people.manage_employees")
@require_http_methods(["GET", "POST"])
def employee_login(request, pk):
    employee = get_object_or_404(
        Employee.objects.select_related("user"), pk=pk
    )
    create_form = EmployeeCreateLoginForm(employee=employee)
    reset_form = EmployeeResetPasswordForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create" and not employee.user_id:
            create_form = EmployeeCreateLoginForm(request.POST, employee=employee)
            if create_form.is_valid():
                try:
                    user = provision_employee_login(
                        employee,
                        email=create_form.cleaned_data["email"],
                        password=create_form.cleaned_data["password1"],
                        role_name=create_form.cleaned_data["role"],
                    )
                except LoginProvisionError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(
                        request,
                        f"Login created for {user.email}. They can sign in at the Day Pay login page.",
                    )
                    return redirect("people:employee_login", pk=employee.pk)
            else:
                messages.error(request, "Fix the login form errors.")
        elif action == "reset" and employee.user_id:
            reset_form = EmployeeResetPasswordForm(request.POST)
            if reset_form.is_valid():
                try:
                    reset_employee_login_password(
                        employee, password=reset_form.cleaned_data["password1"]
                    )
                except LoginProvisionError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Password updated.")
                    return redirect("people:employee_login", pk=employee.pk)
            else:
                messages.error(request, "Fix the password form errors.")
        elif action == "unlink" and employee.user_id:
            try:
                unlink_employee_login(employee)
            except LoginProvisionError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Login unlinked from this employee.")
                return redirect("people:employee_login", pk=employee.pk)

    roles = []
    if employee.user_id:
        roles = list(employee.user.roles.filter(is_active=True).order_by("name"))

    return render(
        request,
        "people/employee_login.html",
        {
            "page_title": f"Login · {employee.full_name}",
            "employee": employee,
            "create_form": create_form,
            "reset_form": reset_form,
            "roles": roles,
        },
    )

