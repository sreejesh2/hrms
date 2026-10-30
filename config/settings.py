"""
Django settings for HRMS.
SQLite by default; set DATABASE_URL for PostgreSQL.
"""

from pathlib import Path
import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


# Off unless explicitly enabled (set DJANGO_DEBUG=True in .env for development)
DEBUG = _env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(50))\""
        )
    SECRET_KEY = "django-insecure-dev-only-change-me-hrms-2026"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local
    "accounts.apps.AccountsConfig",
    "core",
    "people",
    "attendance.apps.AttendanceConfig",
    "leave.apps.LeaveConfig",
    "payroll.apps.PayrollConfig",
    "reports.apps.ReportsConfig",
    "expenses.apps.ExpensesConfig",
    "loans.apps.LoansConfig",
    "performance.apps.PerformanceConfig",
    "setup",
    "notifications",
    "workflows",
    "audit.apps.AuditConfig",
    "docs_app.apps.DocsAppConfig",
]

if DEBUG:
    INSTALLED_APPS.append("debug_toolbar")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.RBACMiddleware",
    "audit.middleware.ActivityLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.ThemeMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.ui_chrome",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def _database_from_env():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }
    parsed = urlparse(url)
    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or 5432),
        }
    }


DATABASES = _database_from_env()

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Dubai")
USE_I18N = True
USE_TZ = True

# Company / payroll defaults (Dubai-focused)
HRMS_DEFAULT_CURRENCY = os.getenv("HRMS_DEFAULT_CURRENCY", "AED")

# HTML5 date/time inputs need ISO values when editing
DATE_INPUT_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
]
TIME_INPUT_FORMATS = [
    "%H:%M",
    "%H:%M:%S",
]
DATETIME_INPUT_FORMATS = [
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
]

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Settings → Backups and `manage.py backup` write here (server: /var/backups/daypay)
HRMS_BACKUP_DIR = os.getenv("HRMS_BACKUP_DIR", "").strip() or str(BASE_DIR / "backups")
# Full path to pg_dump when it is not on PATH (e.g. C:\Program Files\PostgreSQL\16\bin\pg_dump.exe)
HRMS_PG_DUMP = os.getenv("HRMS_PG_DUMP", "").strip()

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Manifest storage needs collectstatic; keep simple in DEBUG for speed.
if DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# Role group names (created by accounts.management command / migration signal)
HRMS_ROLE_GROUPS = ("Admin", "HR", "Payroll", "Manager", "Employee")

INTERNAL_IPS = ["127.0.0.1", "localhost"]

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587") or "587")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Day Pay <noreply@daypay.local>")
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")
HRMS_EMAIL_NOTIFICATIONS = os.getenv("HRMS_EMAIL_NOTIFICATIONS", "true").lower() in (
    "1",
    "true",
    "yes",
)

# --- Security ---------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Origins allowed to POST forms, e.g. "http://192.168.1.10,http://hrms.local".
# Needed when users reach the app by an address other than the Host header.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Only enable when the site is served over HTTPS (nginx with a certificate).
# On a plain-HTTP factory LAN keep this off, or nobody can log in.
if _env_bool("DJANGO_HTTPS", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0") or "0")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "WARNING")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        # Machine traffic summary (punches saved / unknown machine IDs)
        "daypay.zkteco": {"level": "INFO"},
    },
}
