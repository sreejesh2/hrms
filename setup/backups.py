"""
Full backups: database + uploaded files, written to settings.HRMS_BACKUP_DIR.

One backup = two files with the same timestamp:
    db-YYYYmmdd-HHMMSS.dump      (PostgreSQL, pg_dump custom format)
    db-YYYYmmdd-HHMMSS.sqlite3   (SQLite, development)
    media-YYYYmmdd-HHMMSS.tar.gz (MEDIA_ROOT as "media/…")

Used by `manage.py backup` (nightly cron) and Settings → Backups.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

BACKUP_NAME_RE = re.compile(r"^(db|media)-(\d{8}-\d{6})\.(dump|sqlite3|tar\.gz)$")
DEFAULT_KEEP_DAYS = 30


class BackupError(Exception):
    pass


@dataclass
class BackupFile:
    name: str
    kind: str  # "db" | "media"
    stamp: str
    size: int
    created: datetime

    @property
    def size_display(self) -> str:
        size = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{self.size} B"


def backup_dir() -> Path:
    return Path(settings.HRMS_BACKUP_DIR)


def _dump_postgres(db: dict, dest: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise BackupError("pg_dump not found — install the PostgreSQL client tools.")
    cmd = [pg_dump, "-Fc", "--no-owner", "-f", str(dest)]
    if db.get("HOST"):
        cmd += ["-h", str(db["HOST"])]
    if db.get("PORT"):
        cmd += ["-p", str(db["PORT"])]
    if db.get("USER"):
        cmd += ["-U", str(db["USER"])]
    cmd.append(str(db["NAME"]))
    env = {**os.environ, "PGPASSWORD": str(db.get("PASSWORD") or "")}
    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True, timeout=1800)
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or b"").decode(errors="replace").strip()
        raise BackupError(f"pg_dump failed: {message or exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError("pg_dump took longer than 30 minutes.") from exc


def _dump_sqlite(dest: Path) -> None:
    if connection.in_atomic_block:
        # SQLite's backup API waits forever for our own open transaction
        raise BackupError("SQLite backup cannot run inside a database transaction.")
    connection.ensure_connection()
    target = sqlite3.connect(dest)
    try:
        connection.connection.backup(target)  # consistent copy, works while in use
    finally:
        target.close()


def _archive_media(dest: Path) -> None:
    media_root = Path(settings.MEDIA_ROOT)
    with tarfile.open(dest, "w:gz") as tar:
        if media_root.exists():
            tar.add(media_root, arcname="media")
        else:
            info = tarfile.TarInfo("media")
            info.type = tarfile.DIRTYPE
            tar.addfile(info)


def create_backup(*, keep_days: int | None = DEFAULT_KEEP_DAYS, copy_to=None) -> list[Path]:
    """Write a new backup set; prune sets older than `keep_days`. Returns the files."""
    folder = backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    db = settings.DATABASES["default"]
    is_postgres = "postgresql" in db["ENGINE"]
    targets = [
        (folder / f"db-{stamp}.{'dump' if is_postgres else 'sqlite3'}",
         (lambda p: _dump_postgres(db, p)) if is_postgres else _dump_sqlite),
        (folder / f"media-{stamp}.tar.gz", _archive_media),
    ]

    written = []
    try:
        for final, writer in targets:
            partial = final.with_name(final.name + ".partial")
            writer(partial)
            os.chmod(partial, 0o600)
            partial.rename(final)  # never list a half-written file
            written.append(final)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        for final, _ in targets:
            final.with_name(final.name + ".partial").unlink(missing_ok=True)
        raise

    if copy_to:
        for path in written:
            shutil.copy2(path, Path(copy_to) / path.name)
    if keep_days:
        prune_backups(keep_days)
    return written


def prune_backups(keep_days: int) -> int:
    """Delete backup files older than `keep_days`; leave any other file alone."""
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for path in backup_dir().glob("*"):
        if BACKUP_NAME_RE.match(path.name) and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed


def list_backups() -> list[BackupFile]:
    folder = backup_dir()
    if not folder.exists():
        return []
    files = []
    for path in folder.iterdir():
        match = BACKUP_NAME_RE.match(path.name)
        if not match or not path.is_file():
            continue
        stat = path.stat()
        files.append(
            BackupFile(
                name=path.name,
                kind=match.group(1),
                stamp=match.group(2),
                size=stat.st_size,
                created=datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
            )
        )
    return sorted(files, key=lambda f: (f.stamp, f.kind), reverse=True)


def backup_path(name: str) -> Path | None:
    """Path of an existing backup file, or None for anything else (no traversal)."""
    if not BACKUP_NAME_RE.match(name or ""):
        return None
    path = backup_dir() / name
    return path if path.is_file() else None
