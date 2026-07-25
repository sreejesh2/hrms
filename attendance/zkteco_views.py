"""ZKTeco ADMS / Push HTTP endpoints for iFace990 and similar devices."""

from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import zkteco as zk
from .models import PunchDevice


def _text(body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(body or "OK", content_type="text/plain; charset=utf-8", status=status)


def _sn(request) -> str:
    return zk.normalize_sn(request.GET.get("SN") or request.POST.get("SN") or "")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def iclock_cdata(request):
    """
    Device handshake, options, time sync, and ATTLOG push.
    Path: /iclock/cdata
    """
    sn = _sn(request)
    if not sn or not zk.valid_sn(sn):
        return _text("OK")

    device = zk.get_or_register_zk_device(sn)
    if not device or not device.is_active:
        return _text("OK")

    # Time sync request from device (SyncTime interval)
    if request.GET.get("type") == "time":
        zk.touch_device(device, heartbeat=True, auto_time_sync=False)
        PunchDevice.objects.filter(pk=device.pk).update(last_time_sync_at=timezone.now())
        return _text(zk.server_time_payload())

    table = (request.GET.get("table") or "").strip().upper()

    if request.method == "GET":
        # Initial options / heartbeat-style poll without table
        zk.touch_device(device, heartbeat=True)
        return _text(zk.push_options_response(device))

    # POST body
    body = request.body.decode("utf-8", errors="ignore")
    if table == "ATTLOG" or (not table and "\t" in body and "Pin=" not in body and "PIN=" not in body):
        zk.ingest_attlog(device, body)
        return _text("OK")

    if table in ("BIODATA", "FINGERTMP", "FACE", "OPERLOG", "USERPIC", "BIOPHOTO"):
        zk.ingest_biodata(device, body, table=table or "BIODATA")
        return _text("OK")

    # options / unknown — acknowledge and heartbeat
    zk.touch_device(device, heartbeat=True, firmware=(request.GET.get("PushVersion") or "")[:80])
    return _text("OK")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def iclock_getrequest(request):
    """Heartbeat + deliver queued commands (SET TIME, CHECK, INFO, …)."""
    sn = _sn(request)
    if not sn or not zk.valid_sn(sn):
        return _text("OK")
    device = PunchDevice.objects.filter(serial_number__iexact=sn, is_active=True).first()
    if not device:
        device = zk.get_or_register_zk_device(sn)
    if not device or not device.is_active:
        return _text("OK")
    zk.touch_device(device, heartbeat=True)
    from django.db import transaction

    with transaction.atomic():
        payload = zk.pending_commands_payload(device)
    return _text(payload)


@csrf_exempt
@require_http_methods(["POST", "GET"])
def iclock_devicecmd(request):
    """Command execution results from device."""
    sn = _sn(request)
    device = PunchDevice.objects.filter(serial_number__iexact=sn, is_active=True).first()
    if device:
        body = request.body.decode("utf-8", errors="ignore")
        zk.ack_command_result(device, body)
        zk.touch_device(device, heartbeat=True)
    return _text("OK")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def iclock_registry(request):
    sn = _sn(request)
    if sn and zk.valid_sn(sn):
        device = zk.get_or_register_zk_device(sn)
        if device:
            zk.touch_device(device, heartbeat=True)
    return _text("OK")
