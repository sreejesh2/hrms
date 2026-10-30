# Day Pay HRMS — Full Functionality Catalog (Quotation Ready)

**Product:** Day Pay — Human Resource Management & Payroll System  
**Focus:** Dubai / UAE operations (AED, Asia/Dubai timezone, UAE gratuity estimates)  
**Stack:** Django web application · SQLite (dev) / PostgreSQL (production) · responsive browser UI  
**Document purpose:** Module-wise capability list for commercial quotations, SOWs, and client scoping.

Use this file to:

1. List **what the product can do today** (scope for inclusion).
2. Show **what admins can configure** without custom code (“manageable” items).
3. Package modules for **standard vs optional** quotation lines.
4. Call out **gaps / optional add-ons** clients may request separately.

---

## 1. Product summary (one paragraph)

Day Pay is a browser-based HRMS covering employee master data, biometric attendance (including ZKTeco iFace ADMS), shift & calendar control, leave, salary advances, payroll runs with payslips, reimbursements, performance reviews, MIS reports (Excel/PDF), role-based access, activity audit, and in-app notifications. Organization masters, shifts, leave types, salary components, and permissions are **admin-manageable**; operational modules run day-to-day workflows for HR, managers, payroll, and employees.

---

## 2. Default roles (access packages)

| Role | Typical use |
|------|-------------|
| **Admin** | Full access — company setup, RBAC, all modules |
| **HR** | People, attendance, leave, org data, devices |
| **Manager** | Team leave / regularization / expense / review approvals |
| **Payroll** | Structures, periods, runs, payslips, advances recovery |
| **Employee** | Self-service profile, leave, corrections, claims, reviews |

Roles and permissions are **fully manageable** under Settings → Access control (catalog + assign users). Superusers bypass checks.

---

## 3. Module functionality matrix

Legend:

| Symbol | Meaning |
|--------|---------|
| ✅ Included | Built and usable in product |
| 🔧 Manageable | Admin/HR configures via UI (no code) |
| 👷 Operational | Day-to-day use (transactional) |
| 📎 Export | Excel / PDF / print available |

---

### 3.1 Platform & shell

| Capability | Status | Type | Notes |
|------------|--------|------|--------|
| Web browser application | ✅ | — | No separate mobile app required |
| Responsive layout | ✅ | — | Desktop-first; usable on tablet/phone |
| Light / dark theme | ✅ 🔧 | Manageable | User toggle; preference stored |
| Collapsible sidebar navigation | ✅ | — | Permission-aware menu |
| Dashboard (KPIs, queues, charts) | ✅ | Operational | Headcount, attendance, leave, expenses snapshots |
| In-app documentation hub | ✅ | — | Module guides at `/docs/` |
| Activity / audit log | ✅ | Operational | Who did what, when |
| In-app notifications inbox | ✅ | Operational | Approvals & system alerts |
| Email notifications (SMTP) | ✅ 🔧 | Manageable | Console in dev; SMTP via env for production |
| Docker / PostgreSQL ready | ✅ | — | `docker compose` for production-style deploy |

**Quotation line suggestion:** *Core platform (auth, dashboard, theme, audit, notifications, docs)*

---

### 3.2 Accounts & access control

| Capability | Status | Type |
|------------|--------|------|
| Email + password login / logout | ✅ | Operational |
| Self-service profile (name, password) | ✅ | Operational |
| Role-based access control (RBAC) | ✅ 🔧 | Manageable |
| Permission catalog (CRUD) | ✅ 🔧 | Manageable |
| Roles create / edit / delete | ✅ 🔧 | Manageable |
| Assign roles to users | ✅ 🔧 | Manageable |
| Link portal login to employee | ✅ | Operational |
| Create / reset / unlink employee login | ✅ | Operational |

**Manageable (Admin):** roles, permissions, user–role mapping.

---

### 3.3 Organization & company settings

| Capability | Status | Type |
|------------|--------|------|
| Company profile (name, address, TRN, logo) | ✅ 🔧 | Manageable |
| Default currency (AED-ready) | ✅ 🔧 | Manageable |
| Payroll cycle start day | ✅ 🔧 | Manageable |
| Divisions | ✅ 🔧 | Manageable master |
| Departments (+ optional default shift/calendar) | ✅ 🔧 | Manageable master |
| Locations | ✅ 🔧 | Manageable master |
| Positions / designations | ✅ 🔧 | Manageable master |
| Banks (employee salary banks) | ✅ 🔧 | Manageable master |
| Custom employee attribute fields | ✅ 🔧 | Manageable |

**Quotation line:** *Organization masters & company branding*

---

### 3.4 People (HRIS)

| Capability | Status | Type |
|------------|--------|------|
| Employee create / edit / list | ✅ | Operational |
| Search & filters | ✅ | Operational |
| Active employees list | ✅ | Operational |
| On vacation / on leave list | ✅ | Operational |
| Onboarding list + checklist on profile | ✅ | Operational |
| Tabbed employee profile | ✅ | Operational |
| Documents upload / open / delete | ✅ | Operational |
| Document categories & expiry | ✅ | Operational |
| Custom field values on profile | ✅ 🔧 | Operational + Manageable field defs |
| Portal login provisioning | ✅ | Operational |
| Biometric / device ID mapping | ✅ | Operational |
| ZKTeco enroll queue (face / finger / user) | ✅ | Operational |
| Profile: attendance history | ✅ | Operational |
| Profile: leave / salary / performance tabs | ✅ | Operational |

**Profile data typically includes:** employee code, name, status, department, location, position, contact, joining date, bank, biometric ID, employment fields.

**Quotation line:** *Employee master, onboarding, documents, portal access*

---

### 3.5 Time settings (attendance configuration)

| Capability | Status | Type |
|------------|--------|------|
| Work calendars (weekday working pattern) | ✅ 🔧 | Manageable |
| Holidays (company / location) | ✅ 🔧 | Manageable |
| Shift master | ✅ 🔧 | Manageable |
| Shift versions (effective-dated times, breaks, night day-span) | ✅ 🔧 | Manageable |
| Shift assignment — single employee | ✅ 🔧 | Manageable |
| Shift assignment — bulk | ✅ 🔧 | Manageable |
| Shift assignment — CSV import | ✅ 🔧 | Manageable |
| Department default shift auto-apply | ✅ 🔧 | Manageable |
| Temporary date-range assignments (resume prior shift) | ✅ 🔧 | Manageable |
| Overtime policies (basis, grace, rounding, rates) | ✅ 🔧 | Manageable |
| Late penalty policies & tiers | ✅ 🔧 | Manageable |
| Punch device registry | ✅ 🔧 | Manageable |

**Quotation line:** *Shift, calendar, holiday & OT policy configuration*

---

### 3.6 Attendance operations

| Capability | Status | Type |
|------------|--------|------|
| Punch log (device / import / manual) | ✅ | Operational |
| Multi-type punches (In / Break / Out / Auto) | ✅ | Operational |
| Vendor CSV punch import + sample templates | ✅ | Operational |
| Daily attendance generation from punches | ✅ | Operational |
| Statuses: present, absent, half day, leave, weekly off, holiday, missing punch | ✅ | Operational |
| Worked hours, payable hours, OT, actual OT | ✅ | Operational |
| Late minutes & late penalty | ✅ | Operational |
| Break overrun & penalty | ✅ | Operational |
| Daily detail & force regenerate | ✅ | Operational |
| Monthly attendance register (employee × day grid) | ✅ | Operational |
| Register day edit | ✅ | Operational |
| Generate month / lock month | ✅ | Operational |
| Attendance regularization request + approve/reject | ✅ | Operational |
| Apply leave from absent day (quick path) | ✅ | Operational |
| Day lock (skip overwrite on generate unless force) | ✅ | Operational |

**Quotation line:** *Attendance processing, monthly register, corrections*

---

### 3.7 Biometric & integrations

| Capability | Status | Type |
|------------|--------|------|
| ZKTeco ADMS protocol (`/iclock/…`) | ✅ | Integration |
| iFace-class push punches | ✅ | Integration |
| Device online/offline heartbeat | ✅ | Operational |
| Local or global (public) connection mode | ✅ 🔧 | Manageable |
| Auto time sync to device | ✅ | Operational |
| Device commands (add user, enroll face/finger) | ✅ | Operational |
| Bio template storage support | ✅ | Technical |
| HTTP JSON punch API (`/api/attendance/punches/`) | ✅ | Integration |
| Bearer token per device | ✅ 🔧 | Manageable |

**Quotation line (optional add-on if not standard):** *ZKTeco biometric integration + HTTP punch bridge*

---

### 3.8 Leave management

| Capability | Status | Type |
|------------|--------|------|
| Leave types CRUD | ✅ 🔧 | Manageable |
| Leave balances (entitled / used / pending / available) | ✅ 🔧 | Manageable |
| Ensure balances for a year (all active staff) | ✅ | Operational |
| Apply leave (full & half-day) | ✅ | Operational |
| Quick apply from attendance | ✅ | Operational |
| Approve / reject / cancel | ✅ | Operational |
| Sync approved leave → daily attendance | ✅ | Operational |
| Manager team scope / HR all-company (via perms) | ✅ 🔧 | Manageable |

**Quotation line:** *Leave types, balances, apply & approval workflow*

---

### 3.9 Payroll

| Capability | Status | Type |
|------------|--------|------|
| Salary components (earning / deduction) | ✅ 🔧 | Manageable |
| Component flags (taxable, prorate with attendance, etc.) | ✅ 🔧 | Manageable |
| Salary templates + lines | ✅ 🔧 | Manageable |
| Employee salary structures | ✅ 🔧 | Manageable |
| Apply template to structure | ✅ | Operational |
| Payroll periods create / open | ✅ | Operational |
| Payroll run (attendance-linked calculations) | ✅ | Operational |
| Payslip list & detail | ✅ | Operational |
| Payslip PDF | ✅ 📎 | Export |
| Payslip template / layout settings | ✅ 🔧 | Manageable |
| Lock period | ✅ | Operational |
| Statutory deduction rules | ✅ 🔧 | Manageable |
| Incentive plans & awards | ✅ 🔧 | Manageable |
| UAE EOS gratuity estimates list | ✅ | Operational |
| Advance recovery on run (ADV line) | ✅ | Operational |
| Expense / reimbursement integration into run | ✅ | Operational |
| Company salary sheet report | ✅ 📎 | Export |
| Monthly payroll register report | ✅ 📎 | Export |

**Typical run inputs:** structures, attendance (payable hours / LWP), OT, special OT, statutory, advances, incentives.

**Quotation line:** *Full payroll (components, structures, period run, payslip PDF, lock)*  
**Optional line:** *Incentives & gratuity estimates*

---

### 3.10 Salary advances (loans module)

| Capability | Status | Type |
|------------|--------|------|
| Request advance (amount, installments) | ✅ | Operational |
| Approve / reject | ✅ | Operational |
| Mark disbursed (bank / cash) | ✅ | Operational |
| Installment recovery schedule | ✅ | Operational |
| Auto recovery on payroll run | ✅ | Operational |
| Close when fully recovered | ✅ | Operational |

**Quotation line:** *Salary advance request, disbursement & payroll recovery*

---

### 3.11 Reimbursements / expenses

| Capability | Status | Type |
|------------|--------|------|
| Expense categories | ✅ 🔧 | Manageable |
| Multi-line claims + receipts | ✅ | Operational |
| Submit → approve / reject | ✅ | Operational |
| Mark paid (payout status) | ✅ | Operational |
| Payment method tracking | ✅ | Operational |

**Quotation line:** *Expense claims & reimbursement workflow*

---

### 3.12 Performance management

| Capability | Status | Type |
|------------|--------|------|
| Competency catalog | ✅ 🔧 | Manageable |
| Review cycles create / edit | ✅ 🔧 | Manageable |
| Open / close cycle | ✅ | Operational |
| Generate reviews for employees | ✅ | Operational |
| Review forms with competency scores | ✅ | Operational |
| Manager feedback & status workflow | ✅ | Operational |

**Quotation line:** *Performance cycles, competencies & reviews*

---

### 3.13 MIS reports

| Report | Formats | Notes |
|--------|---------|--------|
| Monthly payroll register | Excel / PDF | Period-based |
| Company salary sheet | Excel / PDF | Full company salary layout |
| Payslip line extract | Excel | Component lines |
| Bank payment list | Excel | Bank + net pay |
| Statutory & deduction summary | Excel | Period deductions |
| Attendance monthly register | Excel / PDF | Month grid |
| Daily attendance detail | Excel | Date range |
| Employee attendance sheet | PDF | Per employee period |
| Overtime MIS | Excel | OT analysis |
| Leave balance statement | Excel | Year balances |
| Leave utilization | Excel | Approved leave in range |
| Employee master / headcount | Excel | Roster export |
| EOS gratuity estimates | Excel | UAE Art. 51 style estimates |
| Salary structure snapshot | Excel | Current structures |

**Quotation line:** *MIS report suite (Excel/PDF)*

---

### 3.14 Workflows (framework)

| Capability | Status | Type |
|------------|--------|------|
| Generic approval request model | ✅ | Foundation |
| Module-native approval flows | ✅ | Leave, expenses, advances, regularization |

Note: domain modules implement concrete approvals; a shared workflow engine exists as foundation for future multi-step chains.

---

## 4. Manageable functionality checklist (configuration only)

Items HR/Admin can change in UI **without developers** — highlight these in a “configurable system” pitch.

### Company & people
- [ ] Company name, address, TRN, logo, currency, cycle start day  
- [ ] Departments, divisions, locations, positions, banks  
- [ ] Custom employee fields (definitions)  
- [ ] Onboarding checklist usage on profiles  

### Access
- [ ] Roles and permission sets  
- [ ] User role assignment  
- [ ] Employee portal login create/reset  

### Time & attendance rules
- [ ] Work calendars (working days of week)  
- [ ] Holidays  
- [ ] Shifts & versioned timings (day/night)  
- [ ] Employee shift assignments (single / bulk / CSV / date range)  
- [ ] OT policies  
- [ ] Late penalty policies  
- [ ] Device registry & API tokens  

### Leave
- [ ] Leave types  
- [ ] Yearly balances / ensure year  

### Payroll
- [ ] Salary components  
- [ ] Templates & structures  
- [ ] Statutory rules  
- [ ] Incentive plans / awards  
- [ ] Payslip template  
- [ ] Payroll periods (create/run/lock)  

### Expenses
- [ ] Expense categories  

### Performance
- [ ] Competencies  
- [ ] Review cycles  

### Operations (not masters, but manageable process controls)
- [ ] Generate / lock attendance month  
- [ ] Approve leave, regularization, advances, expenses  
- [ ] Lock payroll period after sign-off  

---

## 5. Suggested quotation packages

Use packaging below when issuing a commercial quote. Adjust unit prices and headcount tiers as needed.

### Package A — Core HR & Attendance
**Includes:** Platform · RBAC · Organization · People · Time settings · Attendance ops · ZK/JSON punches · Leave · Reports (people + attendance + leave) · Audit · Notifications  

**Best for:** Companies needing digital attendance + leave without full payroll run.

### Package B — Payroll suite (add-on to A or standalone with People)
**Includes:** Components · templates · structures · periods · run · payslips PDF · statutory · company salary sheet · bank payment · advances recovery · gratuity estimates  

### Package C — Finance self-service
**Includes:** Salary advances · Expense reimbursements  

### Package D — Performance
**Includes:** Cycles · competencies · reviews  

### Package E — Enterprise options (optional SOW)
| Option | Description |
|--------|-------------|
| ZKTeco multi-site rollout | Extra devices, public HTTPS, network design support |
| Data migration | Historical employees / punches / structures from legacy (e.g. InfoSoft) |
| Custom reports / branding | Extra PDF layouts beyond standard |
| Multi-company (group) | Not standard multi-tenant today — requires project |
| Celery background jobs | Bulk generate / email / large payroll async (architected; workers optional) |
| SMS / WhatsApp | Out of core — integration project |
| Mobile native apps | Out of core — web responsive only |
| ESS advanced (tax proofs, investment) | Out of core UAE focus unless scoped |

---

## 6. Implementation & go-live services (typical quote lines)

| Service | Description |
|---------|-------------|
| Installation & environment | Server/Docker, domain, SSL, PostgreSQL |
| Initial configuration | Company, masters, roles, calendars, shifts |
| Device setup | ZKTeco ADMS or HTTP punch devices |
| Master data load | Employees, structures, leave balances |
| UAT support | Test period + bugfix cycle |
| Training | Admin / HR / Manager / Payroll sessions |
| Documentation | In-app docs + this catalog |
| AMC / support (annual) | Bug fixes, minor enhancements, updates |

**Recommended setup order**

1. Company settings + org masters  
2. Roles & users  
3. Calendars, shifts, holidays, devices  
4. Employees (+ biometric IDs, logins)  
5. Leave types & balances  
6. Payroll components → structures → periods  
7. Connect biometrics / punch API  
8. Dry-run attendance + payroll → go live  

---

## 7. Technical assumptions for quotation

| Item | Default assumption |
|------|--------------------|
| Hosting | Client VPS / cloud (Linux) or managed by vendor |
| DB production | PostgreSQL |
| Concurrent users | Suitable for SME / mid-size (thousands of employees with pagination & indexes) |
| Browser | Modern Chrome / Edge / Safari / Firefox |
| Language | English UI |
| Currency / TZ | AED · Asia/Dubai (configurable company fields) |
| Backup | Client or vendor AMC responsibility (agree in contract) |
| SSL certificate | Client domain |

---

## 8. Scope boundary (honest “not included” unless purchased)

Use this list so quotations stay clear:

| Item | Status |
|------|--------|
| Multi-company / multi-legal-entity SaaS tenanting | Not standard — custom |
| Full multi-step configurable workflow designer | Partial (module approvals exist) |
| Full email template designer | Basic SMTP only |
| Celery workers for all heavy jobs | Optional hardening stage |
| Legacy InfoSoft one-click import | Planned / project-based |
| Payroll bank file (WPS/SIF) auto-generation | Not verified as full UAE WPS file — bank payment MIS only |
| Government e-channels (MOHRE portal sync) | Out of scope |
| Asset management / recruitment ATS | Out of scope |
| Training LMS / learning | Out of scope |
| Project time billing / job cost | Out of scope |

---

## 9. Feature count snapshot (for proposal annex)

| Module area | Approx. functional capability groups |
|-------------|--------------------------------------|
| Platform & security | 10+ |
| Organization | 8+ masters & settings |
| People | 12+ |
| Attendance config + ops | 25+ |
| Biometric integrations | 8+ |
| Leave | 8+ |
| Payroll | 18+ |
| Advances | 6+ |
| Expenses | 5+ |
| Performance | 6+ |
| MIS reports | 14 named reports |
| Audit & notifications | 2+ |

*Counts are capability groups for commercial presentation, not automated metrics.*

---

## 10. Quotation checklist template (copy into proposal)

```
Client: ____________________    Date: __________
Users / employees: __________    Sites: __________

[ ] Package A — Core HR & Attendance
[ ] Package B — Payroll
[ ] Package C — Advances & Expenses
[ ] Package D — Performance
[ ] ZKTeco / device integration services
[ ] Data migration
[ ] Training (days): ____
[ ] Hosting: Client / Vendor
[ ] AMC: ____ months
[ ] Customizations: ______________________________

Payment milestones:
  1. Contract signing ____%
  2. UAT sign-off ____%
  3. Go-live ____%

Notes:
________________________________________________
```

---

## 11. Related project docs

| File | Use |
|------|-----|
| [README.md](README.md) | Install & module map |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Build checklist vs requirements |
| In-app `/docs/` | End-user module guides |

---

*Document generated from Day Pay product modules (people, attendance, leave, payroll, loans, expenses, performance, reports, setup, accounts, audit, notifications). Update this file when major modules are added or commercial packaging changes.*
