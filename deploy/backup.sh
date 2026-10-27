#!/usr/bin/env bash
# Day Pay HRMS — back up database + uploaded files. Installed as
# /usr/local/sbin/daypay-backup and run nightly by /etc/cron.d/daypay-backup.
# Same backup as Settings → Backups → "Create backup now" (files appear there).
#
#   sudo daypay-backup                         # keep 30 days
#   sudo daypay-backup --copy-to /mnt/usb      # also copy to a USB disk / NAS
#
# Restore (example):
#   sudo systemctl stop daypay
#   sudo -u postgres pg_restore --clean --if-exists -d daypay /var/backups/daypay/db-YYYYmmdd-HHMMSS.dump
#   sudo tar -xzf /var/backups/daypay/media-YYYYmmdd-HHMMSS.tar.gz -C /opt/daypay/app
#   sudo systemctl start daypay
set -euo pipefail

cd /opt/daypay/app
exec sudo -u daypay -H /opt/daypay/venv/bin/python manage.py backup "$@"
