"""
Day Pay server for Windows (started at boot by the "DayPay Server" scheduled task).

- Serves the app with waitress on DAYPAY_LISTEN (default 0.0.0.0:80).
- Waits for PostgreSQL after a reboot before accepting requests.
- Restarts waitress if it ever stops; logs to <logs>/daypay.log (rotated).

Run by hand for troubleshooting:  C:\\DayPay\\venv\\Scripts\\python.exe deploy\\windows\\serve.py
"""

import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(APP_DIR / ".env")

LOG_DIR = Path(os.getenv("DAYPAY_LOG_DIR") or APP_DIR.parent / "logs")
LISTEN = os.getenv("DAYPAY_LISTEN", "0.0.0.0:80")
THREADS = int(os.getenv("DAYPAY_THREADS", "8"))


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "daypay.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)  # keeps Django's WARNING level for app noise
    for name in ("daypay.serve", "waitress"):
        logging.getLogger(name).setLevel(logging.INFO)
    return logging.getLogger("daypay.serve")


def wait_for_database(log: logging.Logger, timeout: int = 300) -> None:
    """After a reboot PostgreSQL may start later than this task."""
    from django.db import connection

    deadline = time.time() + timeout
    while True:
        try:
            connection.ensure_connection()
            connection.close()
            return
        except Exception as exc:  # noqa: BLE001 — keep retrying until timeout
            if time.time() > deadline:
                log.error("Database still not reachable after %ss: %s", timeout, exc)
                return
            log.info("Waiting for database: %s", exc)
            time.sleep(5)


def main() -> None:
    from django.core.wsgi import get_wsgi_application
    from waitress import serve

    # Runs django.setup(), which applies settings.LOGGING — add the file log after it
    application = get_wsgi_application()
    log = setup_logging()
    wait_for_database(log)
    while True:
        log.info("Starting Day Pay on %s (%s threads)", LISTEN, THREADS)
        try:
            serve(application, listen=LISTEN, threads=THREADS, ident="DayPay")
            log.warning("Server stopped; restarting in 5 seconds")
        except Exception:  # noqa: BLE001 — never exit; the scheduled task also restarts us
            log.exception("Server crashed; restarting in 5 seconds")
        time.sleep(5)


if __name__ == "__main__":
    main()
