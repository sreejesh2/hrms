#!/usr/bin/env bash
# Day Pay HRMS — back up database + uploaded files. Installed as
# /usr/local/sbin/daypay-backup and run nightly by /etc/cron.d/daypay-backup.
#
# Restore (example):
#   sudo -u postgres pg_restore --clean --if-exists -d daypay /var/backups/daypay/db-YYYYmmdd-HHMM.dump
#   sudo tar -xzf /var/backups/daypay/media-YYYYmmdd-HHMM.tar.gz -C /opt/daypay/app
set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/var/backups/daypay}
KEEP_DAYS=${KEEP_DAYS:-30}
DB_NAME=daypay
MEDIA_PARENT=/opt/daypay/app
STAMP="$(date +%Y%m%d-%H%M)"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

sudo -u postgres pg_dump -Fc "$DB_NAME" > "$BACKUP_DIR/db-$STAMP.dump"
tar -czf "$BACKUP_DIR/media-$STAMP.tar.gz" -C "$MEDIA_PARENT" media

# Copy to a second disk / NAS if mounted (strongly recommended)
if [[ -n "${OFFSITE_DIR:-}" && -d "$OFFSITE_DIR" ]]; then
    cp "$BACKUP_DIR/db-$STAMP.dump" "$BACKUP_DIR/media-$STAMP.tar.gz" "$OFFSITE_DIR/"
fi

find "$BACKUP_DIR" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'media-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "$(date '+%F %T') backup ok: db-$STAMP.dump media-$STAMP.tar.gz"
