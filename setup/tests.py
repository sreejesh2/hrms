from django.contrib.auth import get_user_model
from django.test import TestCase


class SettingsHomeLinksTests(TestCase):
    """Settings home only shows cards the user is allowed to open."""

    def setUp(self):
        from accounts.rbac import seed_rbac

        seed_rbac()

    def login_as(self, role_name):
        from accounts.models import Role

        user = get_user_model().objects.create_user(email=f"{role_name}@example.com", password="x")
        user.roles.set([Role.objects.get(name=role_name)])
        self.client.force_login(user)

    def test_employee_sees_no_admin_cards(self):
        self.login_as("Employee")

        html = self.client.get("/settings/").content.decode()

        for href in ("/settings/access/roles/", "/settings/employee-fields/", "/settings/time/shifts/"):
            self.assertNotIn(href, html)
        self.assertIn("/docs/", html)

    def test_admin_sees_all_cards(self):
        self.login_as("Admin")

        html = self.client.get("/settings/").content.decode()

        for href in ("/settings/access/roles/", "/settings/employee-fields/", "/settings/time/shifts/"):
            self.assertIn(href, html)


import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path

from django.test import TransactionTestCase, override_settings


class BackupTestBase(TransactionTestCase):
    """No wrapping transaction: SQLite's backup API needs the DB idle (like production)."""

    def setUp(self):
        from accounts.rbac import seed_rbac

        seed_rbac()
        self.tmp = Path(tempfile.mkdtemp(prefix="daypay-backup-test-"))
        self.backup_dir = self.tmp / "backups"
        self.media_dir = self.tmp / "media"
        (self.media_dir / "employee_docs").mkdir(parents=True)
        (self.media_dir / "employee_docs" / "passport.pdf").write_bytes(b"%PDF-1")
        self.override = override_settings(
            HRMS_BACKUP_DIR=str(self.backup_dir), MEDIA_ROOT=str(self.media_dir)
        )
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login_as(self, role_name):
        from accounts.models import Role

        user = get_user_model().objects.create_user(email=f"{role_name}-bk@example.com", password="x")
        user.roles.set([Role.objects.get(name=role_name)])
        self.client.force_login(user)
        return user


class CreateBackupTests(BackupTestBase):
    def test_creates_database_copy_and_media_archive(self):
        from setup.backups import create_backup

        files = create_backup()

        names = sorted(p.name for p in files)
        self.assertEqual(len(names), 2)
        db_file = next(p for p in files if p.name.startswith("db-"))
        tables = sqlite3.connect(db_file).execute(
            "SELECT name FROM sqlite_master WHERE name='people_employee'"
        ).fetchall()
        self.assertEqual(tables, [("people_employee",)])
        media_file = next(p for p in files if p.name.startswith("media-"))
        with tarfile.open(media_file) as tar:
            self.assertIn("media/employee_docs/passport.pdf", tar.getnames())

    def test_old_backups_are_removed_but_other_files_kept(self):
        from setup.backups import create_backup

        self.backup_dir.mkdir(parents=True)
        old = self.backup_dir / "db-20200101-010101.sqlite3"
        old.write_bytes(b"old")
        os.utime(old, (time.time() - 40 * 86400,) * 2)
        unrelated = self.backup_dir / "notes.txt"
        unrelated.write_text("keep me")
        os.utime(unrelated, (time.time() - 40 * 86400,) * 2)

        create_backup(keep_days=30)

        self.assertFalse(old.exists())
        self.assertTrue(unrelated.exists())

    def test_copy_to_second_folder(self):
        from setup.backups import create_backup

        offsite = self.tmp / "usb"
        offsite.mkdir()

        create_backup(copy_to=offsite)

        self.assertEqual(len(list(offsite.iterdir())), 2)

    def test_postgres_dump_uses_pg_dump_with_password(self):
        from setup.backups import _dump_postgres

        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "pg_dump"
        fake.write_text(
            "#!/bin/sh\n"
            'echo "$@" > "$(dirname "$0")/args.txt"\n'
            'echo "$PGPASSWORD" > "$(dirname "$0")/pw.txt"\n'
            'while [ "$1" != "-f" ]; do shift; done; echo dump > "$2"\n'
        )
        fake.chmod(0o755)
        dest = self.tmp / "out.dump"
        db = {"NAME": "daypay", "USER": "daypay", "PASSWORD": "s3cret", "HOST": "localhost", "PORT": "5432"}

        with override_settings():
            old_path = os.environ["PATH"]
            os.environ["PATH"] = f"{bin_dir}:{old_path}"
            try:
                _dump_postgres(db, dest)
            finally:
                os.environ["PATH"] = old_path

        self.assertEqual(dest.read_text().strip(), "dump")
        args = (bin_dir / "args.txt").read_text()
        self.assertIn("-Fc", args)
        self.assertIn("daypay", args)
        self.assertNotIn("s3cret", args)  # password via env, never on the command line
        self.assertEqual((bin_dir / "pw.txt").read_text().strip(), "s3cret")

    def test_pg_dump_path_from_setting_is_used(self):
        """Windows: pg_dump is not on PATH, so HRMS_PG_DUMP points at it."""
        from setup.backups import _dump_postgres

        tool_dir = self.tmp / "PostgreSQL" / "16" / "bin"
        tool_dir.mkdir(parents=True)
        fake = tool_dir / "pg_dump"
        fake.write_text('#!/bin/sh\nwhile [ "$1" != "-f" ]; do shift; done; echo from-setting > "$2"\n')
        fake.chmod(0o755)
        dest = self.tmp / "out.dump"

        with override_settings(HRMS_PG_DUMP=str(fake)):
            _dump_postgres({"NAME": "daypay"}, dest)

        self.assertEqual(dest.read_text().strip(), "from-setting")

    def test_management_command(self):
        from django.core.management import call_command

        call_command("backup", stdout=open(os.devnull, "w"))

        self.assertEqual(len(list(self.backup_dir.glob("*-*"))), 2)


class BackupPageTests(BackupTestBase):
    def test_admin_sees_backups_and_can_download(self):
        from setup.backups import create_backup

        files = create_backup()
        self.login_as("Admin")

        page = self.client.get("/settings/backups/")
        self.assertEqual(page.status_code, 200)
        name = files[0].name
        self.assertContains(page, name)
        download = self.client.get(f"/settings/backups/download/{name}")
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(b"".join(download.streaming_content), files[0].read_bytes())

    def test_admin_can_create_backup_from_page(self):
        self.login_as("Admin")

        response = self.client.post("/settings/backups/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(list(self.backup_dir.glob("db-*"))), 1)

    def test_download_is_recorded_in_activity_log(self):
        from audit.models import ActivityLog
        from setup.backups import create_backup

        name = create_backup()[0].name
        self.login_as("Admin")

        self.client.get(f"/settings/backups/download/{name}")

        self.assertTrue(ActivityLog.objects.filter(summary__icontains=name).exists())

    def test_hr_and_employee_cannot_see_or_download(self):
        from setup.backups import create_backup

        name = create_backup()[0].name
        for role in ("HR", "Employee"):
            with self.subTest(role=role):
                self.login_as(role)
                self.assertNotEqual(self.client.get("/settings/backups/").status_code, 200)
                self.assertNotEqual(
                    self.client.get(f"/settings/backups/download/{name}").status_code, 200
                )
                self.client.post("/settings/backups/")
        self.assertEqual(len(list(self.backup_dir.glob("db-*"))), 1)

    def test_unknown_or_unsafe_names_are_404(self):
        self.backup_dir.mkdir(parents=True)
        (self.backup_dir / "notes.txt").write_text("x")
        self.login_as("Admin")

        for name in ("notes.txt", "db-20260101-010101.sqlite3", "..%2Fsettings.py"):
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(f"/settings/backups/download/{name}").status_code, 404
                )
