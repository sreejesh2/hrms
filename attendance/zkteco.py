"""ZKTeco ADMS / Push helpers — attendance ingest, heartbeat, command queue."""

from __future__ import annotations

import re
import secrets
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from people.models import Employee

from .adapters import map_punch_type, parse_datetime, resolve_employee
from .engine import generate_daily_attendance
from .models import DeviceBioTemplate, DeviceCommand, PunchDevice, PunchLog

SN_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


def normalize_sn(raw: str) -> str:
    return (raw or "").strip().upper()


def valid_sn(sn: str) -> bool:
    return bool(SN_RE.match(sn or ""))


def touch_device(
    device: PunchDevice,
    *,
    heartbeat: bool = False,
    firmware: str = "",
    auto_time_sync: bool = True,
):
    """Update last-seen; on ZK heartbeat, auto time-sync after reconnect / every 6h."""
    now = timezone.now()
    old_stamp = device.last_heartbeat_at or device.last_seen_at
    was_online = False
    if old_stamp:
        was_online = (now - old_stamp).total_seconds() <= PunchDevice.ONLINE_SECONDS

    fields = ["last_seen_at", "updated_at"]
    device.last_seen_at = now
    if heartbeat:
        device.last_heartbeat_at = now
        fields.append("last_heartbeat_at")
    if firmware and firmware != device.firmware_info:
        device.firmware_info = firmware[:255]
        fields.append("firmware_info")
    device.save(update_fields=fields)

    if (
        heartbeat
        and auto_time_sync
        and device.vendor == PunchDevice.Vendor.ZKTECO
        and device.is_active
    ):
        maybe_auto_time_sync(device, reconnected=not was_online)
    return device


def maybe_auto_time_sync(device: PunchDevice, *, reconnected: bool = False):
    """Queue SET TIME when device reconnects or sync is older than 6 hours."""
    pending = DeviceCommand.objects.filter(
        device=device,
        status=DeviceCommand.Status.PENDING,
        command__startswith="SET TIME",
    ).exists()
    if pending:
        return None

    need = reconnected or device.last_time_sync_at is None
    if device.last_time_sync_at and not need:
        age = (timezone.now() - device.last_time_sync_at).total_seconds()
        need = age >= 6 * 3600
    if not need:
        return None

    return queue_time_sync(device)


def employee_device_pin(employee: Employee) -> str:
    return (employee.biometric_id or employee.employee_code or "").strip()


def sanitize_adms_text(value: str, *, max_len: int = 40) -> str:
    return re.sub(r"[\t\r\n]+", " ", (value or "").strip())[:max_len]


def queue_user_upsert(device: PunchDevice, employee: Employee) -> DeviceCommand:
    """Create/update PIN + name on the machine (template enroll is separate)."""
    pin = employee_device_pin(employee)
    if not pin:
        raise ValueError("Employee needs biometric ID or employee code as device PIN.")
    name = sanitize_adms_text(employee.full_name)
    cmd = (
        f"DATA UPDATE USERINFO PIN={pin}\tName={name}\tPri=0\t"
        f"Passwd=\tCard=\tGrp=1\tTZ=0000000100000000"
    )
    return queue_command(device, cmd)


def queue_user_delete(device: PunchDevice, employee: Employee) -> DeviceCommand:
    pin = employee_device_pin(employee)
    if not pin:
        raise ValueError("Employee needs biometric ID or employee code as device PIN.")
    return queue_command(device, f"DATA DELETE USERINFO PIN={pin}")


def queue_enroll_finger(
    device: PunchDevice, employee: Employee, *, finger_id: int = 0
) -> list[DeviceCommand]:
    """
    Ensure user exists, then put iFace into fingerprint enroll for that PIN.
    Capture happens on the device screen — not in the browser.
    """
    pin = employee_device_pin(employee)
    if not pin:
        raise ValueError("Employee needs biometric ID or employee code as device PIN.")
    cmds = [queue_user_upsert(device, employee)]
    cmds.append(
        queue_command(
            device,
            f"ENROLL_FP PIN={pin}\tFID={int(finger_id)}\tRETRY=3\tOVERWRITE=1",
        )
    )
    return cmds


def queue_enroll_face(device: PunchDevice, employee: Employee) -> list[DeviceCommand]:
    """Ensure user exists, then trigger multi-face enroll on the device."""
    pin = employee_device_pin(employee)
    if not pin:
        raise ValueError("Employee needs biometric ID or employee code as device PIN.")
    cmds = [queue_user_upsert(device, employee)]
    cmds.append(
        queue_command(device, f"ENROLL_MF PIN={pin}\tRETRY=3\tOVERWRITE=1")
    )
    return cmds


@transaction.atomic
def get_or_register_zk_device(sn: str, *, connection_hint: str = "") -> PunchDevice | None:
    sn = normalize_sn(sn)
    if not valid_sn(sn):
        return None
    device = PunchDevice.objects.filter(serial_number__iexact=sn).first()
    if device:
        return device
    # Auto-register unknown SN as inactive: an admin must approve it (Settings →
    # Devices → Active) before its punches are accepted. Until then anyone on
    # the network could forge attendance with a made-up SN. attlog_stamp stays
    # "0", so after approval the device re-uploads its stored punches.
    code = f"ZK{sn[-8:]}"
    base = code
    n = 1
    while PunchDevice.objects.filter(code=code).exists():
        n += 1
        code = f"{base}-{n}"
    mode = PunchDevice.ConnectionMode.GLOBAL
    if connection_hint == "local":
        mode = PunchDevice.ConnectionMode.LOCAL
    device = PunchDevice(
        code=code,
        name=f"ZKTeco {sn} (pending approval)",
        device_type=PunchDevice.DeviceType.BIOMETRIC,
        vendor=PunchDevice.Vendor.ZKTECO,
        connection_mode=mode,
        serial_number=sn,
        api_token=secrets.token_urlsafe(32),
        is_active=False,
    )
    device.save()
    return device


def queue_command(device: PunchDevice, command: str) -> DeviceCommand:
    return DeviceCommand.objects.create(
        device=device,
        command=command.strip(),
        status=DeviceCommand.Status.PENDING,
    )


def queue_time_sync(device: PunchDevice) -> DeviceCommand:
    """Queue SET TIME so the device applies server clock on next poll."""
    now = timezone.localtime()
    cmd = f"SET TIME {now.strftime('%Y-%m-%d %H:%M:%S')}"
    queued = queue_command(device, cmd)
    PunchDevice.objects.filter(pk=device.pk).update(last_time_sync_at=timezone.now())
    device.last_time_sync_at = timezone.now()
    return queued


def queue_check(device: PunchDevice) -> DeviceCommand:
    return queue_command(device, "CHECK")


def queue_info(device: PunchDevice) -> DeviceCommand:
    return queue_command(device, "INFO")


def pending_commands_payload(device: PunchDevice, *, limit: int = 20) -> str:
    from django.db import connection

    lock_kwargs = {}
    if getattr(connection.features, "has_select_for_update_skip_locked", False):
        lock_kwargs["skip_locked"] = True
    qs = (
        DeviceCommand.objects.select_for_update(**lock_kwargs)
        .filter(device=device, status=DeviceCommand.Status.PENDING)
        .order_by("created_at")[:limit]
    )
    lines = []
    now = timezone.now()
    for cmd in qs:
        lines.append(cmd.adms_line)
        cmd.status = DeviceCommand.Status.SENT
        cmd.sent_at = now
        cmd.save(update_fields=["status", "sent_at"])
    if not lines:
        return "OK"
    return "\n".join(lines)


def ack_command_result(device: PunchDevice, body: str):
    """Parse ID=…&Return=… style acks from /iclock/devicecmd."""
    now = timezone.now()
    for part in (body or "").replace("\r", "\n").split("\n"):
        part = part.strip()
        if not part:
            continue
        data = {}
        for token in part.replace("&", " ").split():
            if "=" in token:
                k, v = token.split("=", 1)
                data[k.strip().lower()] = v.strip()
        cid = data.get("id") or data.get("cmdid")
        if not cid or not str(cid).isdigit():
            continue
        cmd = DeviceCommand.objects.filter(device=device, pk=int(cid)).first()
        if not cmd:
            continue
        ret = data.get("return") or data.get("result") or ""
        ok = ret in ("0", "OK", "ok", "")
        cmd.status = DeviceCommand.Status.ACKED if ok else DeviceCommand.Status.FAILED
        cmd.result = ret[:255]
        cmd.acked_at = now
        cmd.save(update_fields=["status", "result", "acked_at"])


def push_options_response(device: PunchDevice) -> str:
    """Initial ADMS options including time-sync interval."""
    now = timezone.localtime()
    stamp = device.attlog_stamp or "0"
    # SyncTime=300 → device asks server time about every 5 minutes
    lines = [
        f"GET OPTION FROM: {device.serial_number}",
        "ErrorDelay=60",
        "Delay=30",
        "TransTimes=00:00;14:00",
        "TransInterval=1",
        "TransFlag=TransData AttLog\tOpLog\tAttPhoto\tEnrollUser\tChgUser\tEnrollFP\tChgFP\tUserPic",
        "Realtime=1",
        "Encrypt=0",
        "TimeZone=+04:00",  # Asia/Dubai
        "Timeout=60",
        "SyncTime=300",
        f"ServerVer=DayPay 1.0 {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"ATTLOGStamp={stamp}",
        "OPERLOGStamp=0",
        "ATTPHOTOStamp=0",
    ]
    return "\n".join(lines)


def server_time_payload() -> str:
    now = timezone.localtime()
    # PUSH SDK: Time=YYYY-MM-DDThh:mm:ss±hh:mm
    return f"Time={now.strftime('%Y-%m-%dT%H:%M:%S')}+04:00"


def parse_attlog_lines(body: str):
    """Yield dicts from ATTLOG tab-separated lines."""
    for raw in (body or "").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        pin = parts[0].strip()
        punched = parts[1].strip()
        status = parts[2].strip() if len(parts) > 2 else "0"
        yield {
            "pin": pin,
            "punched_at": punched,
            "status": status,
            "verify": parts[3].strip() if len(parts) > 3 else "",
            "raw": line,
        }


@transaction.atomic
def ingest_attlog(device: PunchDevice, body: str) -> dict:
    created, skipped, unknown = 0, 0, 0
    touched = set()
    for row in parse_attlog_lines(body):
        employee = resolve_employee(biometric_id=row["pin"]) or resolve_employee(
            employee_code=row["pin"]
        )
        if not employee:
            unknown += 1
            continue
        try:
            punched_at = parse_datetime(row["punched_at"])
        except ValueError:
            skipped += 1
            continue
        ptype = map_punch_type(row["status"])
        external_id = f"zk-{device.serial_number}-{row['pin']}-{row['punched_at']}-{row['status']}"
        try:
            # Savepoint: a re-sent duplicate must not break the outer transaction
            with transaction.atomic():
                PunchLog.objects.create(
                    employee=employee,
                    punched_at=punched_at,
                    punch_type=ptype,
                    device=device,
                    source=PunchLog.Source.DEVICE,
                    external_id=external_id[:120],
                )
            created += 1
            touched.add((employee.pk, timezone.localtime(punched_at).date()))
        except IntegrityError:
            skipped += 1

    # Update stamp to now for next push options
    device.attlog_stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
    device.save(update_fields=["attlog_stamp", "updated_at"])
    touch_device(device, heartbeat=True)

    for emp_id, day in touched:
        generate_daily_attendance(Employee.objects.get(pk=emp_id), day, force=True)

    return {"created": created, "skipped": skipped, "unknown": unknown}


def _kv_pairs(line: str) -> dict:
    data = {}
    for token in line.replace("\t", " ").split():
        if "=" in token:
            k, v = token.split("=", 1)
            data[k.strip().lower()] = v.strip()
    return data


def _bio_type_from_vendor(type_code: str, table: str) -> str:
    t = (type_code or "").strip()
    if table in ("FACE", "BIOPHOTO") or t in ("2", "9", "15"):
        return DeviceBioTemplate.BioType.FACE
    if table in ("FINGERTMP", "TEMPLATEV10") or t in ("1", "0", ""):
        return DeviceBioTemplate.BioType.FINGER
    if t == "1":
        return DeviceBioTemplate.BioType.FINGER
    return DeviceBioTemplate.BioType.OTHER


@transaction.atomic
def ingest_biodata(device: PunchDevice, body: str, *, table: str = "BIODATA") -> dict:
    """Store face/finger templates pushed from the device after enroll."""
    saved, unknown = 0, 0
    for raw in (body or "").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        data = _kv_pairs(line)
        pin = data.get("pin") or data.get("enrollnumber") or ""
        tmp = data.get("tmp") or data.get("template") or data.get("data") or ""
        if not pin or not tmp:
            # OPERLOG enroll lines without template — skip
            continue
        employee = resolve_employee(biometric_id=pin) or resolve_employee(
            employee_code=pin
        )
        if not employee:
            unknown += 1
            continue
        bio_type = _bio_type_from_vendor(data.get("type") or data.get("bioType"), table)
        try:
            idx = int(data.get("no") or data.get("index") or data.get("fid") or 0)
        except ValueError:
            idx = 0
        DeviceBioTemplate.objects.update_or_create(
            employee=employee,
            bio_type=bio_type,
            finger_index=idx,
            defaults={
                "template_data": tmp[:200000],
                "source_device": device,
                "pin": pin[:64],
            },
        )
        saved += 1
    touch_device(device, heartbeat=True)
    return {"saved": saved, "unknown": unknown}


def queue_push_bio_templates(
    device: PunchDevice, employee: Employee
) -> list[DeviceCommand]:
    """Push stored USERINFO + bio templates to a device (multi-device sync)."""
    cmds = [queue_user_upsert(device, employee)]
    pin = employee_device_pin(employee)
    for tmpl in DeviceBioTemplate.objects.filter(employee=employee).order_by(
        "bio_type", "finger_index"
    ):
        type_code = "1" if tmpl.bio_type == DeviceBioTemplate.BioType.FINGER else "2"
        cmd = (
            f"DATA UPDATE BIODATA Pin={pin}\tNo={tmpl.finger_index}\tIndex=0\t"
            f"Valid=1\tDuress=0\tType={type_code}\tMajorVer=0\tMinorVer=0\t"
            f"Format=ZK\tTmp={tmpl.template_data}"
        )
        cmds.append(queue_command(device, cmd))
    return cmds

