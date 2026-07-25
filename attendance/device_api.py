"""Device punch ingest API — multiple machines push here with per-device tokens."""

import json

from django.db import IntegrityError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from people.models import Employee

from .adapters import map_punch_type, parse_datetime, resolve_employee_from_item
from .engine import generate_daily_attendance
from .models import PunchDevice, PunchLog


@csrf_exempt
@require_http_methods(["POST"])
def device_punch_ingest(request):
    """
    POST /api/attendance/punches/
    Header: Authorization: Bearer <device_api_token>
         or X-Device-Token: <token>

    Identify employee with either:
      - employee_code (HR code), or
      - biometric_id / pin / AccNo / device_user_id (machine enroll id)

    Body JSON (single or batch):
    {
      "employee_code": "E001",
      "biometric_id": "10023",
      "punched_at": "2026-07-22T09:05:00",
      "punch_type": "in",
      "external_id": "dev-123"
    }
    or { "punches": [ {...}, ... ] }
    """
    token = request.headers.get("X-Device-Token", "").strip()
    auth = request.headers.get("Authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        return JsonResponse({"ok": False, "error": "Missing device token"}, status=401)

    try:
        device = PunchDevice.objects.get(api_token=token, is_active=True)
    except PunchDevice.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Invalid device token"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    items = payload.get("punches")
    if items is None:
        items = [payload]
    if not isinstance(items, list) or not items:
        return JsonResponse({"ok": False, "error": "No punches provided"}, status=400)

    created, skipped, errors = [], [], []
    touched = set()
    valid_types = {c.value for c in PunchLog.PunchType}

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"index": i, "error": "Item must be an object"})
            continue

        employee = resolve_employee_from_item(item)
        if not employee:
            errors.append(
                {
                    "index": i,
                    "error": "Unknown employee — set employee_code or biometric_id (PIN/AccNo)",
                }
            )
            continue

        try:
            punched_at = parse_datetime(
                item.get("punched_at") or item.get("timestamp") or item.get("DateTime")
            )
        except ValueError as exc:
            errors.append({"index": i, "error": str(exc)})
            continue

        raw_type = item.get("punch_type") or item.get("Status") or item.get("status")
        ptype = map_punch_type(raw_type)
        if ptype not in valid_types:
            ptype = PunchLog.PunchType.AUTO

        external_id = str(
            item.get("external_id") or item.get("id") or item.get("log_id") or ""
        ).strip()

        try:
            punch = PunchLog.objects.create(
                employee=employee,
                punched_at=punched_at,
                punch_type=ptype,
                device=device,
                source=PunchLog.Source.DEVICE,
                external_id=external_id,
            )
            created.append(punch.pk)
            touched.add((employee.pk, timezone.localtime(punched_at).date()))
        except IntegrityError:
            skipped.append({"index": i, "external_id": external_id, "reason": "duplicate"})

    PunchDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())

    for emp_id, day in touched:
        generate_daily_attendance(Employee.objects.get(pk=emp_id), day, force=True)

    status = 200 if created or skipped else 400
    return JsonResponse(
        {
            "ok": bool(created) or bool(skipped),
            "device": device.code,
            "created": len(created),
            "skipped": len(skipped),
            "errors": errors,
            "punch_ids": created,
        },
        status=status,
    )
