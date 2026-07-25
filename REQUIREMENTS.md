# Day Pay — Features, Requirements & Implementation Stages

**Stack:** Django-only web app  
**Database:** SQLite for local development → PostgreSQL for staging/production (same Django models/migrations)  
**Other:** Celery/Redis when needed for background jobs  
**Goal:** Modern, fast, light/dark themed, scalable Day Pay HRMS (careful query patterns, no N+1)

Tick items when done: change `- [ ]` to `- [x]`

---

## Platform & quality

- [x] Web-based application (browser)
- [x] Django-only stack (no separate React/Next frontend)
- [x] Modern, clean, user-friendly UI
- [x] Light theme + dark theme (user toggle, preference persisted)
- [x] Fast UI (lean CSS/JS, pagination, no heavy unused assets)
- [x] Responsive layout (desktop-first, usable on mobile for approvals)
- [x] SQLite for development (zero setup)
- [x] PostgreSQL for production / later scale (migrate when ready)
- [ ] Fully scalable architecture (indexes done; Celery for heavy jobs later)
- [x] Careful ORM patterns — avoid N+1 (`select_related` / `prefetch_related`)
- [x] Query discipline: pagination + DB indexes on FKs & filters
- [x] Scalable app structure (domain apps + reusable query helpers)
- [x] Role-based access control — fully dynamic roles & permission catalog
- [x] Notifications (in-app stub; email later)
- [x] Approval workflows (model stub; full flows later)

---

## Feature requirements

### People

- [x] Employee onboarding — checklist tab on employee profile
- [x] Employee profile management (create/edit + tabbed detail)
- [x] Org masters (departments, divisions, locations, positions, banks) — CRUD + RBAC
- [x] Dynamic / additional employee attributes (HR can create fields and fill values)
- [x] List of active employees
- [x] List of employees on vacation / on leave
- [x] Employee document management (upload / open / delete)
### Attendance & shifts

- [x] Shift management system (work calendars, shift master + versions, assignments)
- [x] Holiday management (Time settings)
- [x] Attendance tracking (multi-punch + daily generation)
- [x] Biometric integration (import/API adapter)
- [x] Multi-device punch API + biometric ID mapping + vendor CSV adapters
- [x] Attendance regularization (request + approval)
- [x] Monthly employee-wise attendance register
- [x] Attendance register editing option
- [x] Day / month lock (Generate skips locked days unless Force)
- [x] Overtime calculator based on shift

### Leave

- [x] Leave management
- [x] Holiday management
- [x] Leave apply / approve / reject
- [x] Pending employees leave calculator (entitlement, used, pending, balance)

### Payroll

- [x] Payroll processing (salary components + structures; runs/payslips later)
- [x] Deductions (statutory / policy rules on payroll run)
- [x] Statutory compliance (configurable rules + UAE gratuity estimates)
- [x] Monthly salary statement for payroll process (period + run)
- [x] Employee slip / payslip generator (PDF)
- [x] Payslips download/print

### Performance

- [x] Performance reviews (cycles, ratings, manager feedback)

### Expenses

- [x] Expense claims
- [x] Reimbursement workflow (approve + payout status)

### Dashboards & reports

- [x] HR / Admin dashboards (shell + stats cards)
- [x] MIS reports and exports (PDF/Excel)

---

## Implementation stages

### Stage 0 — Project setup

- [x] Django project scaffold in this folder
- [x] SQLite configured for local development (default)
- [x] Settings ready to switch to PostgreSQL via env vars (no code rewrite)
- [x] Docker Compose for Postgres/Redis/worker — when moving beyond SQLite
- [x] Auth (login/logout) + base roles/groups
- [x] Modern base layout (sidebar, top bar, dashboard shell)
- [x] Light / dark theme system (CSS variables + toggle)
- [x] Base QuerySet / view mixins enforcing `select_related` / `prefetch_related` patterns
- [x] django-debug-toolbar in DEBUG (catch N+1 during development)
- [x] Notifications app stub
- [x] Shared approval/workflow app stub

### Stage 1 — People & onboarding

- [x] Department, Division, Location, Position, Bank (and related masters)
- [x] Employee model + profile screens
- [x] Employee onboarding wizard / checklist
- [x] Active employees list
- [x] Employees on vacation list
- [x] Basic document upload on profile

### Stage 2 — Shifts, attendance, biometric, OT

- [x] Shift definitions and employee shift assignment
- [x] Bulk shift assign + CSV import + department default shifts
- [x] Company holiday calendar
- [x] Punch data (manual entry + multi-punch In/Break/Out)
- [x] Biometric / file import adapter (multi-device API + CSV)
- [x] Daily attendance generation from punches
- [x] Attendance regularization flow
- [x] Monthly attendance register (view)
- [x] Monthly attendance register (edit)
- [x] Day / month attendance lock
- [x] Overtime calculator based on shift rules

### Stage 3 — Leave & holidays

- [x] Leave types and policies
- [x] Leave balances
- [x] Leave requests + approvals + notifications
- [x] Company holiday calendar
- [x] Pending leave calculator

### Stage 4 — Payroll, statutory, slips

- [x] Salary components (earnings / deductions)
- [x] Employee salary structure
- [x] Statutory rule configuration
- [x] Payroll period + monthly run
- [x] Monthly salary statement (period payslip list)
- [x] Employee slip / payslip PDF generator
- [x] Link approved expenses / loan EMI into payroll (when available)

### Stage 5 — Performance, expenses, dashboards

- [x] Performance review cycles and forms
- [x] Expense & reimbursement module
- [x] HR/Admin dashboards (headcount, on leave, pending approvals, payroll status)
- [x] Reports module (attendance, leave, payroll, headcount exports)

### Stage 6 — Harden & scale

- [ ] Full permission matrix per module
- [x] Performance indexes + pagination everywhere
- [x] N+1 audit pass on list/detail/report views
- [x] Biometric vendor connector polish
- [ ] Legacy InfoSoft data import helpers (if needed)
- [ ] UAT fixes and print/export polish
- [ ] Celery jobs for payroll / bulk attendance / emails (Docker Postgres ready; workers later)

---

## How to use this file

1. Implement a feature or stage item.
2. Mark it complete: `- [x] Employee onboarding`
3. Keep this file updated so progress is always visible.

**Progress:** Stage 0 mostly complete · Stage 1 models + lists started.
