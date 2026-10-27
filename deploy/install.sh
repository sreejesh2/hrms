#!/usr/bin/env bash
# Day Pay HRMS — one-time install on Ubuntu 24.04 LTS (factory LAN server).
#
#   sudo bash deploy/install.sh              # run from the project folder
#   sudo bash deploy/install.sh --firewall   # also enable ufw (SSH + HTTP only)
#
# Unattended admin creation (otherwise you are asked):
#   sudo DAYPAY_ADMIN_EMAIL=hr@company.com DAYPAY_ADMIN_PASSWORD='...' bash deploy/install.sh
#
# Safe to re-run: existing database, .env, uploads and admin users are kept.
set -euo pipefail

APP_USER=daypay
BASE=/opt/daypay
APP_DIR=$BASE/app
VENV=$BASE/venv
BACKUP_DIR=/var/backups/daypay
DB_NAME=daypay
DB_USER=daypay
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENABLE_FIREWALL=0
[[ "${1:-}" == "--firewall" ]] && ENABLE_FIREWALL=1

wait_for_app() {
    for _ in $(seq 1 30); do
        [[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/accounts/login/)" == 200 ]] && return 0
        sleep 1
    done
    die "Day Pay is not responding. Check: sudo journalctl -u daypay -n 50"
}
say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run with sudo: sudo bash deploy/install.sh"
[[ -f "$SRC_DIR/manage.py" ]] || die "Run this from inside the Day Pay project folder."

say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-dev build-essential libpq-dev \
    postgresql postgresql-contrib nginx rsync curl

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
    || die "Python 3.12+ is required (Django 6). Use Ubuntu 24.04 LTS or newer."

say "Setting time zone to Asia/Dubai and enabling network time"
timedatectl set-timezone Asia/Dubai || true
timedatectl set-ntp true || true

say "Creating service user and folders"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$BASE" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$BACKUP_DIR"

say "Copying application code to $APP_DIR"
rsync -a --delete \
    --exclude '.git' --exclude '.venv' --exclude 'venv' --exclude '__pycache__' \
    --exclude '.env' --exclude 'media/' --exclude 'staticfiles/' \
    --exclude 'db.sqlite3' --exclude '.DS_Store' --exclude 'backups/' \
    "$SRC_DIR/" "$APP_DIR/"
mkdir -p "$APP_DIR/media"

say "Starting PostgreSQL and nginx (and enabling them on boot)"
systemctl enable --now postgresql nginx
for _ in $(seq 1 30); do
    pg_isready -q && break
    sleep 1
done
pg_isready -q || die "PostgreSQL did not start. Check: sudo journalctl -u postgresql"

say "Creating PostgreSQL database"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    DB_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    sudo -u postgres psql -q -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';"
    NEW_DB_PASS="$DB_PASS"
fi
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 \
    || sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"

say "Writing settings (.env)"
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    [[ -n "${NEW_DB_PASS:-}" ]] || die "Database user exists but $ENV_FILE is missing. Restore the old .env (it holds the DB password)."
    SERVER_IPS="$(hostname -I | xargs | tr ' ' ',')"
    HOST="$(hostname)"
    ORIGINS="$(for h in ${SERVER_IPS//,/ } "$HOST" "$HOST.local"; do printf 'http://%s,' "$h"; done)"
    SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
    FIRST_IP="${SERVER_IPS%%,*}"
    cat > "$ENV_FILE" <<EOF
DJANGO_SECRET_KEY=$SECRET
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,$SERVER_IPS,$HOST,$HOST.local
DJANGO_CSRF_TRUSTED_ORIGINS=${ORIGINS%,}
DJANGO_HTTPS=False
DJANGO_TIME_ZONE=Asia/Dubai
DATABASE_URL=postgres://$DB_USER:$NEW_DB_PASS@localhost:5432/$DB_NAME
SITE_URL=http://$FIRST_IP
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
HRMS_EMAIL_NOTIFICATIONS=false
HRMS_BACKUP_DIR=$BACKUP_DIR
EOF
    echo "Created $ENV_FILE (server addresses: $SERVER_IPS, $HOST)"
else
    echo "Keeping existing $ENV_FILE"
fi
grep -q '^HRMS_BACKUP_DIR=' "$ENV_FILE" || echo "HRMS_BACKUP_DIR=$BACKUP_DIR" >> "$ENV_FILE"
chmod 600 "$ENV_FILE"

say "Installing Python packages"
[[ -d "$VENV" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"

chown -R "$APP_USER:$APP_USER" "$BASE"
# App user writes backups (nightly job + Settings → Backups); nobody else can read them
chown -R "$APP_USER:$APP_USER" "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"

manage() { sudo -u "$APP_USER" -H bash -c "cd '$APP_DIR' && '$VENV/bin/python' manage.py $*"; }

say "Preparing database and static files"
manage migrate --noinput
manage collectstatic --noinput -v 0
# Explicit groups: never the dev admin (admin@example.com / admin123) or demo data
manage seed --only rbac org leave expenses payroll attendance ot_rules performance

say "Installing services (app, web server, nightly backup)"
install -m 644 "$APP_DIR/deploy/daypay.service" /etc/systemd/system/daypay.service
install -m 644 "$APP_DIR/deploy/nginx-daypay.conf" /etc/nginx/sites-available/daypay
ln -sf /etc/nginx/sites-available/daypay /etc/nginx/sites-enabled/daypay
rm -f /etc/nginx/sites-enabled/default
install -m 755 "$APP_DIR/deploy/backup.sh" /usr/local/sbin/daypay-backup
cat > /etc/cron.d/daypay-backup <<'EOF'
# Nightly Day Pay backup (database + uploaded files), keeps 30 days
30 1 * * * root /usr/local/sbin/daypay-backup >> /var/log/daypay-backup.log 2>&1
EOF

nginx -t
systemctl daemon-reload
systemctl enable --now daypay cron
systemctl restart daypay
systemctl restart nginx
wait_for_app

if [[ $ENABLE_FIREWALL -eq 1 ]]; then
    say "Enabling firewall (SSH + HTTP only)"
    apt-get install -y -q ufw
    ufw allow OpenSSH
    ufw allow 80/tcp
    ufw --force enable
fi

has_superuser() {
    # Exit code, not printed text (Django's shell prints an import banner)
    (cd "$APP_DIR" && sudo -u "$APP_USER" -H "$VENV/bin/python" manage.py shell --no-imports \
        -c "import sys; from accounts.models import User; sys.exit(0 if User.objects.filter(is_superuser=True).exists() else 1)")
}

if ! has_superuser; then
    say "Create the first admin login (email + password)"
    if [[ -n "${DAYPAY_ADMIN_EMAIL:-}" && -n "${DAYPAY_ADMIN_PASSWORD:-}" ]]; then
        sudo -u "$APP_USER" -H env \
            DJANGO_SUPERUSER_EMAIL="$DAYPAY_ADMIN_EMAIL" \
            DJANGO_SUPERUSER_PASSWORD="$DAYPAY_ADMIN_PASSWORD" \
            bash -c "cd '$APP_DIR' && '$VENV/bin/python' manage.py createsuperuser --noinput"
    else
        manage createsuperuser
    fi
    has_superuser || die "No admin login was created. Run: cd $APP_DIR && sudo -u $APP_USER $VENV/bin/python manage.py createsuperuser"
fi

FIRST_IP="$(hostname -I | awk '{print $1}')"
say "Done!"
cat <<EOF

  Open in a browser:   http://$FIRST_IP/
  ZKTeco devices:      set Cloud Server / ADMS address to $FIRST_IP, port 80
                       then approve each device in Settings -> Devices (tick Active)
  Backups:             $BACKUP_DIR (nightly at 01:30, 30 days kept)
  Logs:                sudo journalctl -u daypay -f
  Update later:        sudo bash deploy/update.sh   (from the new code folder)

EOF
