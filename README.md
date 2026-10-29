# Day Pay — HRMS

Day Pay is a Dubai-focused HR / payroll system (AED, Asia/Dubai): people, attendance (including ZKTeco iFace ADMS), leave, payroll, reimbursements, performance, MIS reports, and an activity audit log.

## Factory / production install

See **[deploy/INSTALL.md](deploy/INSTALL.md)** — one script sets up an Ubuntu 24.04
server on the LAN (PostgreSQL, nginx, auto-start service, nightly backups) and
explains how to connect and approve ZKTeco machines.

**Windows server (no Docker):** double-click `deploy\windows\install.bat` — see
**[deploy/windows/INSTALL-WINDOWS.md](deploy/windows/INSTALL-WINDOWS.md)**.

## Quick start (development)

```bash
cd /Users/macbook/Desktop/hrms
source .venv/bin/activate
cp -n .env.example .env   # then set DJANGO_DEBUG=True for local development
python manage.py migrate
python manage.py seed --admin
python manage.py runserver
```

Open http://127.0.0.1:8000/ — sign in with **email**.

**Dev login:** `admin@example.com` / `admin123` (development only — never use `seed --admin` on the factory server)

Foundation data (permissions, roles, leave types, payroll catalogs, …) is also applied on migrate. Re-run anytime:

```bash
python manage.py seed           # catalogs + RBAC
python manage.py seed --admin   # also ensure demo admin
python manage.py seed --demo    # 5 employees + GEN shift + this month attendance
python manage.py seed --list    # show groups
python manage.py seed --only rbac
```

In-app guides: **Documentation** in the sidebar → `/docs/` (one page per module).

## Docker (Postgres)

```bash
docker compose up --build
```

Runs gunicorn with `DEBUG` off, so `.env` must contain `DJANGO_SECRET_KEY` (and optionally `POSTGRES_PASSWORD`). Uses `DATABASE_URL=postgres://hrms:…@db:5432/hrms`. For local Postgres without Docker, set `DATABASE_URL` in `.env` and run migrate.

Email notifications print to the console by default; set SMTP vars in `.env` for real mail (see `.env.example`).

## Modules (product)

| Module | Path | Notes |
|--------|------|--------|
| Dashboard | `/` | KPIs, charts, queues |
| Documentation | `/docs/` | Full per-module guides |
| People | `/people/` | Employees, login, ZK enroll |
| Attendance | `/attendance/` | Punches, daily, register, corrections |
| Time settings | `/settings/time/` | Calendars, shifts, devices |
| ZKTeco ADMS | `/iclock/` | iFace990 push protocol |
| Device JSON API | `/api/attendance/punches/` | HTTP bridge |
| Leave | `/leave/` | Types, balances, approvals |
| Payroll | `/payroll/` | Structures, periods, payslips |
| Reimbursements | `/expenses/` | Claims & payout |
| Performance | `/performance/` | Cycles & reviews |
| Reports | `/reports/` | MIS Excel/PDF |
| Settings | `/settings/` | Company, masters, RBAC |
| Activity log | `/audit/` | Who did what, when |
| Notifications | `/notifications/` | Inbox |
| Profile | `/accounts/profile/` | Self-service |

## Apps (code)

| App | Purpose |
|-----|---------|
| `accounts` | Login, profile, RBAC |
| `core` | Shell, theme, dashboard |
| `people` | Employees & onboarding |
| `attendance` | Time, punches, devices, ZK |
| `leave` | Leave management |
| `payroll` | Payroll & statutory |
| `expenses` | Reimbursements |
| `performance` | Reviews |
| `reports` | MIS exports |
| `setup` | Company, masters, access |
| `notifications` | In-app alerts |
| `workflows` | Generic approvals |
| `audit` | Activity log |
| `docs_app` | In-app documentation |

## Default roles

Admin (all) · HR · Manager · Payroll · Employee — seeded via `python manage.py seed` (also on migrate).

## Recommended setup order

1. Company settings + org masters  
2. Roles / user assignment  
3. Calendars, shifts, holidays, devices  
4. Employees (+ biometric IDs, logins)  
5. Leave types & balances  
6. Payroll components → structures → periods  
7. Connect ZKTeco or JSON punch API  

See also [REQUIREMENTS.md](REQUIREMENTS.md).
