#!/usr/bin/env bash
# Day Pay HRMS — install a new version (run from the NEW code folder).
#
#   sudo bash deploy/update.sh
#
# Takes a backup first; keeps .env, uploads and the database.
set -euo pipefail

APP_USER=daypay
BASE=/opt/daypay
APP_DIR=$BASE/app
VENV=$BASE/venv
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run with sudo: sudo bash deploy/update.sh"
[[ -f "$APP_DIR/.env" ]] || die "Day Pay is not installed yet. Run deploy/install.sh first."
[[ "$SRC_DIR" != "$APP_DIR" ]] || die "Run this from the new code folder, not from $APP_DIR."

say "Backing up before update"
/usr/local/sbin/daypay-backup

say "Copying new code"
rsync -a --delete \
    --exclude '.git' --exclude '.venv' --exclude 'venv' --exclude '__pycache__' \
    --exclude '.env' --exclude 'media/' --exclude 'staticfiles/' \
    --exclude 'db.sqlite3' --exclude '.DS_Store' \
    "$SRC_DIR/" "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

manage() { sudo -u "$APP_USER" -H bash -c "cd '$APP_DIR' && '$VENV/bin/python' manage.py $*"; }

say "Updating packages, database and static files"
"$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
manage migrate --noinput
manage collectstatic --noinput -v 0
manage check --deploy --fail-level ERROR

install -m 644 "$APP_DIR/deploy/daypay.service" /etc/systemd/system/daypay.service
install -m 644 "$APP_DIR/deploy/nginx-daypay.conf" /etc/nginx/sites-available/daypay
install -m 755 "$APP_DIR/deploy/backup.sh" /usr/local/sbin/daypay-backup
nginx -t
systemctl daemon-reload
systemctl restart daypay
systemctl reload nginx

say "Updated. Check: sudo systemctl status daypay"
