"""Role-aware dashboard metrics for HRMS home."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts.permissions import request_has_perm


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def employee_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "employee_profile", None)


def build_dashboard(request) -> dict:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    me = employee_for_user(request.user)

    can_people = request_has_perm(request, "people.view_employees")
    can_leave = any(
        request_has_perm(request, p)
        for p in ("leave.view", "leave.request", "leave.approve", "leave.manage")
    )
    can_leave_manage = request_has_perm(request, "leave.manage")
    can_leave_approve = request_has_perm(request, "leave.approve") or can_leave_manage
    can_att = any(
        request_has_perm(request, p)
        for p in ("attendance.view", "attendance.manage", "attendance.approve_regularization")
    )
    can_att_manage = request_has_perm(request, "attendance.manage")
    can_att_approve = (
        request_has_perm(request, "attendance.approve_regularization") or can_att_manage
    )
    can_exp = any(
        request_has_perm(request, p)
        for p in ("expenses.view", "expenses.request", "expenses.approve", "expenses.manage")
    )
    can_exp_manage = request_has_perm(request, "expenses.manage")
    can_exp_approve = request_has_perm(request, "expenses.approve") or can_exp_manage
    can_exp_pay = can_exp_manage or request_has_perm(request, "expenses.pay")
    can_payroll = request_has_perm(request, "payroll.view")
    can_reports = request_has_perm(request, "reports.view")

    is_ops = can_people or can_leave_manage or can_att_manage or can_exp_manage or can_payroll
    is_managerish = can_leave_approve or can_att_approve or can_exp_approve

    ctx = {
        "today": today,
        "greeting": _greeting(request.user, today),
        "role_mode": "ops" if is_ops else ("manager" if is_managerish else "self"),
        "kpis": [],
        "queues": [],
        "quick_actions": [],
        "attendance_today": None,
        "attendance_issues": [],
        "dept_chart": None,
        "attendance_chart": None,
        "attendance_trend": None,
        "leave_type_chart": None,
        "expense_category_chart": None,
        "my_balances": [],
        "my_attendance": [],
        "recent_approvals": [],
        "payroll_snapshot": None,
        "can_people": can_people,
        "can_reports": can_reports,
    }

    # —— People KPIs ——
    if can_people:
        from people.models import Employee

        by_status = {
            row["status"]: row["c"]
            for row in Employee.objects.values("status").annotate(c=Count("id"))
        }
        active = by_status.get(Employee.Status.ACTIVE, 0)
        on_leave = by_status.get(Employee.Status.ON_LEAVE, 0)
        onboarding = by_status.get(Employee.Status.DRAFT, 0)
        total = sum(by_status.values())
        ctx["kpis"].extend(
            [
                {
                    "label": "Headcount",
                    "value": total,
                    "hint": f"{active} active",
                    "tone": "neutral",
                    "href": reverse("people:employee_list"),
                },
                {
                    "label": "On vacation",
                    "value": on_leave,
                    "hint": "Employee status",
                    "tone": "warn" if on_leave else "neutral",
                    "href": reverse("people:employee_list") + "?status=on_leave",
                },
                {
                    "label": "Onboarding",
                    "value": onboarding,
                    "hint": "Draft profiles",
                    "tone": "accent" if onboarding else "neutral",
                    "href": reverse("people:employee_list") + "?status=draft",
                },
            ]
        )
        # New joiners this month
        joined = Employee.objects.filter(
            date_of_joining__gte=month_start, date_of_joining__lte=today
        ).count()
        ctx["kpis"].append(
            {
                "label": "Joined this month",
                "value": joined,
                "hint": today.strftime("%b %Y"),
                "tone": "ok" if joined else "neutral",
                "href": reverse("people:employee_list"),
            }
        )
        # Department chart (top 8)
        dept_rows = list(
            Employee.objects.filter(
                status__in=[Employee.Status.ACTIVE, Employee.Status.ON_LEAVE]
            )
            .values("department__description", "department__code")
            .annotate(c=Count("id"))
            .order_by("-c")[:8]
        )
        if dept_rows:
            ctx["dept_chart"] = {
                "labels": [
                    (r["department__description"] or r["department__code"] or "Unassigned")
                    for r in dept_rows
                ],
                "values": [r["c"] for r in dept_rows],
            }

    # —— Attendance today ——
    if can_att:
        from datetime import datetime, time as dt_time

        from attendance.models import DailyAttendance, PunchLog
        from attendance.punch_issues import analyze_punches

        qs = DailyAttendance.objects.filter(date=today)
        if not can_att_manage and me:
            qs = qs.filter(Q(employee__manager=me) | Q(employee=me))
        elif not can_att_manage and not me:
            qs = qs.none()

        day_agg = qs.aggregate(
            present=Count(
                "id", filter=Q(status=DailyAttendance.Status.PRESENT)
            ),
            absent=Count("id", filter=Q(status=DailyAttendance.Status.ABSENT)),
            missing=Count(
                "id", filter=Q(status=DailyAttendance.Status.MISSING_PUNCH)
            ),
            on_leave=Count(
                "id", filter=Q(status=DailyAttendance.Status.ON_LEAVE)
            ),
            half=Count("id", filter=Q(status=DailyAttendance.Status.HALF_DAY)),
            late=Count("id", filter=Q(late_minutes__gt=0)),
            total=Count("id"),
        )
        present = day_agg["present"] or 0
        absent = day_agg["absent"] or 0
        missing = day_agg["missing"] or 0
        on_leave_d = day_agg["on_leave"] or 0
        half = day_agg["half"] or 0
        late = day_agg["late"] or 0
        total_day = day_agg["total"] or 0

        ctx["attendance_today"] = {
            "date": today,
            "total": total_day,
            "present": present,
            "absent": absent,
            "missing": missing,
            "on_leave": on_leave_d,
            "half_day": half,
            "late": late,
            "href": reverse("attendance_ops:daily_list") + f"?date={today.isoformat()}",
        }
        ctx["attendance_chart"] = {
            "labels": ["Present", "Absent", "Leave", "Half day", "Missing", "Other"],
            "values": [
                present,
                absent,
                on_leave_d,
                half,
                missing,
                max(0, total_day - present - absent - on_leave_d - half - missing),
            ],
        }
        if can_att_manage or can_att_approve:
            ctx["kpis"].append(
                {
                    "label": "Present today",
                    "value": present,
                    "hint": f"{absent} absent · {missing} missing punch",
                    "tone": "ok" if present else "neutral",
                    "href": ctx["attendance_today"]["href"],
                }
            )
            if missing:
                ctx["kpis"].append(
                    {
                        "label": "Missing punches",
                        "value": missing,
                        "hint": "Needs Out / fix today",
                        "tone": "warn",
                        "href": reverse("attendance_ops:daily_list")
                        + f"?date={today.isoformat()}&status=missing_punch",
                    }
                )

        # Recent incomplete punch days — one punch query for the window (not N+1)
        issue_start = today - timedelta(days=6)
        issue_qs = (
            DailyAttendance.objects.filter(
                date__gte=issue_start,
                date__lte=today,
                is_locked=False,
            )
            .exclude(
                status__in=[
                    DailyAttendance.Status.WEEKLY_OFF,
                    DailyAttendance.Status.HOLIDAY,
                    DailyAttendance.Status.ON_LEAVE,
                ]
            )
            .select_related("employee", "employee__department")
            .order_by("-date", "employee__employee_code")
        )
        if not can_att_manage and me:
            issue_qs = issue_qs.filter(Q(employee__manager=me) | Q(employee=me))
        elif not can_att_manage and not me:
            issue_qs = issue_qs.none()

        candidates = list(issue_qs[:80])
        punches_by_day: dict[tuple[int, object], list] = {}
        if candidates:
            emp_ids = {r.employee_id for r in candidates}
            tz = timezone.get_current_timezone()
            range_start = timezone.make_aware(
                datetime.combine(issue_start, dt_time.min), tz
            )
            range_end = timezone.make_aware(
                datetime.combine(today + timedelta(days=1), dt_time.min), tz
            )
            punch_rows = (
                PunchLog.objects.filter(
                    employee_id__in=emp_ids,
                    punched_at__gte=range_start,
                    punched_at__lt=range_end,
                )
                .order_by("punched_at")
                .only("id", "employee_id", "punched_at", "punch_type")
            )
            for p in punch_rows:
                d = timezone.localtime(p.punched_at).date()
                punches_by_day.setdefault((p.employee_id, d), []).append(p)

        interesting = {
            "missing_out",
            "single_punch",
            "missing_break_in",
            "open_segment",
            "no_punches",
        }
        issues_out = []
        for row in candidates:
            punches = punches_by_day.get((row.employee_id, row.date), [])
            found = analyze_punches(punches)
            labels = [i.label for i in found]
            if row.status == DailyAttendance.Status.MISSING_PUNCH and not labels:
                labels = ["Missing punch"]
            if row.status == DailyAttendance.Status.ABSENT and not punches:
                continue
            if (
                not any(i.code in interesting for i in found)
                and row.status != DailyAttendance.Status.MISSING_PUNCH
            ):
                continue
            if not labels:
                continue
            issues_out.append(
                {
                    "employee": row.employee,
                    "date": row.date,
                    "status": row.get_status_display(),
                    "status_code": row.status,
                    "issues": labels[:2],
                    "href": reverse(
                        "attendance_ops:register_day",
                        args=[row.employee_id, row.date.isoformat()],
                    ),
                }
            )
            if len(issues_out) >= 12:
                break
        ctx["attendance_issues"] = issues_out
        if issues_out and (can_att_manage or can_att_approve):
            ctx["queues"].insert(
                0,
                {
                    "label": "Punch issues (7 days)",
                    "count": len(issues_out),
                    "hint": "Missing Out / open break / incomplete",
                    "href": reverse("attendance_ops:daily_list")
                    + f"?date={today.isoformat()}&status=missing_punch",
                    "tone": "warn",
                },
            )

        # 14-day attendance trend (Present / Absent / On leave)
        trend_start = today - timedelta(days=13)
        trend_qs = DailyAttendance.objects.filter(date__gte=trend_start, date__lte=today)
        if not can_att_manage and me:
            trend_qs = trend_qs.filter(Q(employee__manager=me) | Q(employee=me))
        elif not can_att_manage and not me:
            trend_qs = trend_qs.none()
        trend_rows = (
            trend_qs.values("date", "status")
            .annotate(c=Count("id"))
            .order_by("date")
        )
        by_day = {}
        for row in trend_rows:
            d = row["date"]
            by_day.setdefault(d, {})[row["status"]] = row["c"]
        labels, present_s, absent_s, leave_s = [], [], [], []
        for i in range(13, -1, -1):
            d = today - timedelta(days=i)
            bucket = by_day.get(d, {})
            labels.append(d.strftime("%d %b"))
            present_s.append(bucket.get(DailyAttendance.Status.PRESENT, 0))
            absent_s.append(bucket.get(DailyAttendance.Status.ABSENT, 0))
            leave_s.append(bucket.get(DailyAttendance.Status.ON_LEAVE, 0))
        if any(present_s) or any(absent_s) or any(leave_s):
            ctx["attendance_trend"] = {
                "labels": labels,
                "present": present_s,
                "absent": absent_s,
                "on_leave": leave_s,
            }

    # —— Leave by type (approved days, YTD) ——
    if can_leave and (can_leave_manage or can_leave_approve or me):
        from leave.models import LeaveRequest

        lqs = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.APPROVED,
            start_date__year=today.year,
        )
        if can_leave_manage:
            pass
        elif can_leave_approve and me:
            lqs = lqs.filter(Q(employee__manager=me) | Q(employee=me))
        elif me:
            lqs = lqs.filter(employee=me)
        else:
            lqs = lqs.none()
        leave_rows = list(
            lqs.values("leave_type__code", "leave_type__name")
            .annotate(days=Sum("days"))
            .order_by("-days")[:6]
        )
        if leave_rows:
            ctx["leave_type_chart"] = {
                "labels": [
                    (r["leave_type__code"] or r["leave_type__name"] or "Other")
                    for r in leave_rows
                ],
                "values": [float(r["days"] or 0) for r in leave_rows],
                "hint": f"Approved days · {today.year}",
            }

    # —— Reimbursements by category (YTD, approved + paid) ——
    if can_exp and (can_exp_manage or can_exp_approve or can_exp_pay or me):
        from expenses.models import ExpenseClaim, ExpenseLine

        claim_filter = Q(
            claim__status__in=[
                ExpenseClaim.Status.APPROVED,
                ExpenseClaim.Status.PAID,
            ],
            claim__created_at__year=today.year,
        )
        if can_exp_manage or can_exp_pay:
            pass
        elif can_exp_approve and me:
            claim_filter &= Q(claim__employee__manager=me) | Q(claim__employee=me)
        elif me:
            claim_filter &= Q(claim__employee=me)
        else:
            claim_filter &= Q(pk__in=[])
        exp_rows = list(
            ExpenseLine.objects.filter(claim_filter)
            .values("category__name", "category__code")
            .annotate(total=Sum("amount"))
            .order_by("-total")[:6]
        )
        if exp_rows:
            ctx["expense_category_chart"] = {
                "labels": [
                    (r["category__name"] or r["category__code"] or "Other")
                    for r in exp_rows
                ],
                "values": [float(r["total"] or 0) for r in exp_rows],
                "hint": f"AED · {today.year}",
            }

    # —— Action queues ——
    if can_leave and can_leave_approve:
        from leave.models import LeaveRequest

        lqs = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING)
        if not can_leave_manage and me:
            lqs = lqs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        elif not can_leave_manage:
            lqs = lqs.filter(approval__assignee=request.user)
        n = lqs.count()
        ctx["queues"].append(
            {
                "label": "Leave approvals",
                "count": n,
                "href": reverse("leave:list") + "?scope=pending",
                "tone": "warn" if n else "neutral",
            }
        )

    if can_att and can_att_approve:
        from attendance.models import AttendanceRegularization

        rqs = AttendanceRegularization.objects.filter(
            status=AttendanceRegularization.Status.PENDING
        )
        if not can_att_manage and me:
            rqs = rqs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        elif not can_att_manage:
            rqs = rqs.filter(approval__assignee=request.user)
        n = rqs.count()
        ctx["queues"].append(
            {
                "label": "Attendance corrections",
                "count": n,
                "href": reverse("attendance_ops:regularization_list") + "?scope=pending",
                "tone": "warn" if n else "neutral",
            }
        )

    if can_exp and can_exp_approve:
        from expenses.models import ExpenseClaim

        eqs = ExpenseClaim.objects.filter(status=ExpenseClaim.Status.PENDING)
        if not can_exp_manage and me:
            eqs = eqs.filter(Q(employee__manager=me) | Q(approval__assignee=request.user))
        elif not can_exp_manage:
            eqs = eqs.filter(approval__assignee=request.user)
        n = eqs.count()
        ctx["queues"].append(
            {
                "label": "Reimbursement approvals",
                "count": n,
                "href": reverse("expenses:list") + "?scope=pending",
                "tone": "warn" if n else "neutral",
            }
        )

    if can_exp and can_exp_pay:
        from expenses.models import ExpenseClaim

        pay_agg = ExpenseClaim.objects.filter(
            status=ExpenseClaim.Status.APPROVED
        ).aggregate(n=Count("id"), s=Sum("total_amount"))
        n = pay_agg["n"] or 0
        amt = pay_agg["s"] or Decimal("0")
        ctx["queues"].append(
            {
                "label": "Reimbursements to pay",
                "count": n,
                "hint": f"AED {amt:,.2f}" if n else "",
                "href": reverse("expenses:list") + "?scope=to_pay",
                "tone": "accent" if n else "neutral",
            }
        )

    pending_total = sum(q["count"] for q in ctx["queues"])
    if pending_total or is_ops or is_managerish:
        # Don't duplicate if already have people KPIs covering approvals
        if not any(k["label"] == "Action queue" for k in ctx["kpis"]):
            ctx["kpis"].insert(
                0,
                {
                    "label": "Needs action",
                    "value": pending_total,
                    "hint": "Pending queues",
                    "tone": "warn" if pending_total else "ok",
                    "href": None,
                },
            )

    # —— Payroll snapshot ——
    if can_payroll:
        from payroll.currencies import format_money
        from payroll.models import PayrollPeriod, Payslip

        period = PayrollPeriod.objects.order_by("-year", "-month").first()
        if period:
            slip_agg = Payslip.objects.filter(period=period).aggregate(
                n=Count("id"), s=Sum("net_pay")
            )
            net = slip_agg["s"] or Decimal("0")
            ctx["payroll_snapshot"] = {
                "label": period.label,
                "status": period.get_status_display(),
                "status_code": period.status,
                "payslips": slip_agg["n"] or 0,
                "net_fmt": format_money(net, period.currency),
                "href": reverse("payroll:period_detail", args=[period.pk]),
            }
            ctx["kpis"].append(
                {
                    "label": "Payroll period",
                    "value": period.get_status_display(),
                    "hint": period.label,
                    "tone": "accent",
                    "href": ctx["payroll_snapshot"]["href"],
                    "is_text": True,
                }
            )

    # —— Self-service widgets ——
    if me:
        if can_leave or request_has_perm(request, "leave.request"):
            from leave.models import LeaveBalance

            ctx["my_balances"] = list(
                LeaveBalance.objects.filter(employee=me, year=today.year)
                .select_related("leave_type")
                .order_by("leave_type__code")[:8]
            )
        if can_att or True:
            from attendance.models import DailyAttendance

            start = today - timedelta(days=6)
            rows = (
                DailyAttendance.objects.filter(employee=me, date__gte=start, date__lte=today)
                .order_by("date")
            )
            by_date = {r.date: r for r in rows}
            trail = []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                rec = by_date.get(d)
                trail.append(
                    {
                        "date": d,
                        "label": d.strftime("%a"),
                        "status": rec.get_status_display() if rec else "—",
                        "code": rec.status if rec else "none",
                    }
                )
            ctx["my_attendance"] = trail

    # —— Recent pending approvals assigned to me ——
    ctx["recent_approvals"] = _safe(
        lambda: list(
            __import__("workflows.models", fromlist=["ApprovalRequest"])
            .ApprovalRequest.objects.filter(
                status="pending", assignee=request.user
            )
            .order_by("-created_at")[:6]
        ),
        [],
    )

    # —— Quick actions ——
    ctx["quick_actions"] = _quick_actions(request, me)

    return ctx


def _greeting(user, today):
    hour = timezone.localtime().hour
    if hour < 12:
        part = "Good morning"
    elif hour < 17:
        part = "Good afternoon"
    else:
        part = "Good evening"
    name = ""
    emp = getattr(user, "employee_profile", None)
    if emp:
        name = emp.first_name or emp.full_name
    elif user:
        name = (getattr(user, "email", "") or "").split("@")[0]
    return f"{part}{', ' + name if name else ''}"


def _quick_actions(request, me):
    actions = []
    if request_has_perm(request, "leave.request") or request_has_perm(request, "leave.manage"):
        actions.append(
            {"label": "Apply leave", "href": reverse("leave:create"), "tone": "primary"}
        )
    if request_has_perm(request, "expenses.request") or request_has_perm(
        request, "expenses.manage"
    ):
        actions.append(
            {
                "label": "Submit reimbursement",
                "href": reverse("expenses:create"),
                "tone": "primary",
            }
        )
    if request_has_perm(request, "attendance.request_regularization") or request_has_perm(
        request, "attendance.manage"
    ):
        actions.append(
            {
                "label": "Attendance correction",
                "href": reverse("attendance_ops:regularization_create"),
                "tone": "ghost",
            }
        )
    if request_has_perm(request, "people.view_employees"):
        actions.append(
            {"label": "Employees", "href": reverse("people:employee_list"), "tone": "ghost"}
        )
    if request_has_perm(request, "payroll.view"):
        actions.append(
            {"label": "Payroll", "href": reverse("payroll:home"), "tone": "ghost"}
        )
    if request_has_perm(request, "reports.view"):
        actions.append(
            {"label": "MIS reports", "href": reverse("reports:home"), "tone": "ghost"}
        )
    return actions[:6]
