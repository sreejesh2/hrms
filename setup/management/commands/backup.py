from django.core.management.base import BaseCommand, CommandError

from setup.backups import DEFAULT_KEEP_DAYS, BackupError, backup_dir, create_backup


class Command(BaseCommand):
    help = "Back up the database and uploaded files to HRMS_BACKUP_DIR (run nightly by cron)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-days",
            type=int,
            default=DEFAULT_KEEP_DAYS,
            help=f"Delete backups older than this many days (default {DEFAULT_KEEP_DAYS}; 0 = keep all).",
        )
        parser.add_argument(
            "--copy-to",
            default="",
            help="Also copy the new files to this folder (e.g. a mounted USB disk or NAS).",
        )

    def handle(self, *args, **options):
        try:
            files = create_backup(
                keep_days=options["keep_days"] or None, copy_to=options["copy_to"] or None
            )
        except (BackupError, OSError) as exc:
            raise CommandError(f"Backup failed: {exc}") from exc
        names = ", ".join(f.name for f in files)
        self.stdout.write(self.style.SUCCESS(f"Backup ok in {backup_dir()}: {names}"))
