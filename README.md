# schoolERP: School management for ERPNext v16

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

![Management Dashboard](docs/images/management-dashboard.png)

**Dashboards:** a Management Dashboard for leadership and a Staff Room for every teacher, with a notice board staff acknowledge. See [docs/DASHBOARDS.md](docs/DASHBOARDS.md).

> **New here? Running on Windows?** Follow **[docs/WSL_SETUP.md](docs/WSL_SETUP.md)**: install everything in WSL, run the app locally, and the test routine to follow before every push.

A simple school management app on top of ERPNext. Students are ERPNext **Customers** whose ID is the **Student ID**, so every fee is a normal Sales Invoice, every payment a normal Payment Entry, and all ERPNext accounting reports keep working.

| Module (license code) | What it gives the school |
|---|---|
| **Core** (always on) | Students, parents/guardians, classes, streams, teachers, school years and terms |
| `fees` | Fee types, fee structures per term/class/boarding, one-click term billing, fee payments split by fee type, receipts, **parent fee statements**, Fee Balances report |
| `transport` | Transport routes with a fee per term; students on a route are billed for it |
| `lunch` | Lunch fee charged only to students marked "Takes School Lunch" |
| `activities` | Games & activities (swimming, football...) each with a fee per term |
| `timetable` | Subjects, periods, class timetables with teacher clash checks, printable grid |
| `messaging` | SMS and email to parents: billing notices, payment receipts, reminders, PDF statements |
| `staff` | Staff members (teachers, drivers, support), **leave** with types, balances, approvals, approval + **reliever notifications**, **duty roster & daily Teacher-on-Duty reports**. See [docs/STAFF_AND_OPERATIONS.md](docs/STAFF_AND_OPERATIONS.md) |
| `expenses` | **Expense posting with amount-based approvals** (one or two levels), posted to the accounts automatically |
| `transport_ops` | **Driver morning check-in** (safety checklist, fitness, odometer, fuel), alerts for failed checks and missed check-ins, vehicles and document expiry |
| `welfare` | **Discipline incidents** (SMS parent) and **complaints** (staff + public web form with SMS tracking) |
| `mpesa` | **M-Pesa Paybill auto-posting**: parents pay with the Student ID as account number and the payment is posted to the student automatically. See [docs/MPESA.md](docs/MPESA.md) |

---

## 1. Install

```bash
cd ~/frappe-bench
bench get-app git@github.com:Nyarunda/schoolERP.git
bench --site yoursite install-app school_erp
bench --site yoursite migrate
bench build --app school_erp
```

Requires ERPNext (v16 / develop) with its setup wizard completed (company, chart of accounts).

## 2. One-time vendor setup (you, not the school)

Modules are switched on by a **signed license key**. The school can't edit it to add modules because only you hold the private key.

```bash
python tools/license_tool.py keygen
```

* Save the **private key** to `vendor.key` somewhere safe. Never ship it.
* Paste the **public key** into `school_erp/licensing/public_key.py` and commit. Every school install uses this same public key.

Issue a key for each school according to its agreement and payment:

```bash
python tools/license_tool.py issue --private-key-file vendor.key \
  --school "Greenhill Academy" --site greenhill.example.com \
  --modules fees,transport,lunch,activities,messaging,timetable,mpesa,staff,expenses,transport_ops,welfare \
  --expires 2027-12-31 --max-students 600
```

* `--site` locks the key to that Frappe site name (optional but recommended).
* `--max-students` caps active students (0 = unlimited).
* Omit `--expires` for a perpetual license.
* To upgrade a school (e.g. add transport), issue a new key and they paste it in.

**Expiry behaviour:** 30 days before expiry admins see a reminder. After expiry there is a 14-day grace period. After that, licensed modules become read-only, except **Fee Payment**, so the school can always receipt money. Unlicensed modules are blocked on save and their fields are hidden on the Student form; transport/lunch/activity fees are not billed.

> Honest note: this protects against casual misuse. Anyone with server access can edit Python code, so pair it with your hosting agreement.

## 3. School setup (per school)

1. **School Settings → School tab**: name, logo, motto, contacts.
2. **Accounts & IDs tab**: Company (required), income account, Student ID format (default `STU-.YYYY.-.####`, or tick "Use Admission Number as Student ID").
3. **License tab**: paste the key and save. The status shows which modules are on.
4. Click **Run School Setup**. It creates (only what's missing): classes for the chosen system (CBC PP1–Grade 9, 8-4-4, British, or Custom), fee types with their service items, this year's three terms, periods and subjects, and an M-Pesa Mode of Payment. It also turns off rounded totals so statements add up exactly.
5. Open **Mode of Payment → M-Pesa** and set the receiving account for your company (and the same for Cash / Bank).
6. Adjust **School Term** dates, then create **Streams** (e.g. Grade 4 East, Grade 4 West).
7. **Statements tab**: Paybill/till number, bank details, payment instructions, footer text, accent colour.
8. **SMS & Email tab**: choose the SMS provider (below) and edit the message templates.

## 4. SMS provider (chosen per school)

| Setting | Use when |
|---|---|
| **Frappe SMS Settings** | Any HTTP SMS gateway. Configure it in Frappe's own *SMS Settings* page (URL, parameters, headers). |
| **Africa's Talking** | Enter username, API key, sender ID (tick Sandbox to test). |
| **Custom Hook** | Your own adapter in another app: add `school_sms_sender = "my_app.sms.send"` to its hooks.py. The function receives `(numbers: list[str], message: str)` and returns `{"sent": [...], "failed": [...]}`. |

Numbers are normalised with the school's country code (`0712 345 678` → `254712345678`). Email uses the site's outgoing Email Account.

## 5. Day-to-day

**Admit a student** → Student form: names, stream, Day/Boarder, guardians (one marked Primary; tick SMS/Email per guardian), transport route, lunch, activities, scholarship %. A Customer with the same ID is created automatically.

**Set fees for a term** → *School Fee Structure*: pick the term, optionally a class and boarding type, add fee lines. You can have a general structure plus class-specific ones; the most specific wins per fee type. Transport and activity fees come from the route/activity, not the structure. "Once" fee types (e.g. Admission) are only ever charged once per student.

**Bill the term** → *Fee Billing Run*: pick term, due date, optionally a class or stream → **Preview** shows every student's lines and the total → Submit. Invoices are created in the background, one per student, never twice for the same term (safe to re-run later for new admissions). Parents are notified by SMS and/or emailed a PDF statement if enabled. Mid-term admissions: Student → Fees → *Bill for a Term*.

**Receive money** → *Fee Payment* (or Student → Fees → Record Payment). The form shows what's owed per fee type. Choose:
* **Oldest balance first** (default): oldest invoice first, then by fee-type priority (Tuition before Transport, etc.).
* **Specific fee types**: e.g. the parent says "this is for transport". Optionally spill any remainder onto other balances.
* Overpayments are kept as an advance and shown as a credit.
* M-Pesa codes can't be used twice. Submitting posts an ERPNext Payment Entry, prints a receipt, and SMSes the parent the new balance.

**Statements** → Student → Fees → *Fee Statement (PDF)* (choose dates), or *Send Statement to Parents*, or print the Student with the "Fee Statement" print format. Bulk: *School Message* with audience "Students with a balance", channel Email, tick "Attach PDF Fee Statement".

**Who owes what** → *Fee Balances* report (filter by term/class/stream; "Message these parents" button).

**Timetable** → *Timetable* per stream per term. Add lessons (day, period, subject, teacher, room). Duplicate slots, lessons in breaks and teachers double-booked across streams are rejected. Use "Copy Slots From" to start from last term. Print with "Class Timetable".

## 6. Reports & sidebar

The School sidebar has sections for Students & Welfare, Fees, Finance, Staff, Transport, Academics, Reports and Setup. 16 reports: Fee Balances, Fee Collection, Fee Structure Matrix (fees per class per term), Paybill Reconciliation, Income vs Expenses, Expense Register, Class Enrolment, Discipline Summary, Complaints Summary, Leave Balance, Staff On Leave, Duty Reports Register, Teacher Workload, Driver Check-in Register, Vehicle Fuel and Mileage, Transport List (and lunch list).

## 7. Roles

* **School Admin**: everything in the app.
* **Bursar**: students, fees, payments, billing, messages.
* **Teacher**: read students and timetables, duty reports, discipline incidents.
* **Head Teacher**: approves leave and final expenses; receives duty reports, complaints and alerts.
* **Staff**: every staff login: apply for leave, raise expenses.
* **Driver** / **Transport Manager**: driver check-ins and vehicles.

## 8. What's where

```
school_erp/
  logic/            pure business rules (no Frappe), unit tested
    billing.py      which fees a student owes
    allocation.py   splitting payments by fee type
    statement.py    statement totals
    license.py      key signing/verification and module rules
  api/              Frappe glue: billing, payments, statement, messaging, setup, timetable
  licensing/        license enforcement + public_key.py
  school/           DocTypes, print formats, Fee Balances report, workspace
  templates/fee_statement/   the parent statement design
  tests/            test_logic.py (unit), test_integration.py (bench)
tools/license_tool.py        vendor-only key generator
scripts/                     check.sh, validate_app.py, install-hooks.sh
docs/WSL_SETUP.md            local setup and testing on Windows
```

Testing:
* `./scripts/check.sh`: compile, DocType validation, JS syntax and logic unit tests (no bench needed).
* `bench --site test.localhost run-tests --app school_erp`: end-to-end tests on a real site.
* `./scripts/install-hooks.sh`: run the checks automatically before every `git push`.
* GitHub Actions runs both on every push and pull request.

## 9. Notes

* Frappe's separate **Education** and **LMS (Learning)** apps can be installed alongside; this app does not depend on them and uses its own DocType names to avoid clashes.
* Credit notes against an invoice show on the statement as "Fee credit / reversal". Payment Entries made directly in ERPNext (not through Fee Payment) still reduce balances; they are spread across fee types by priority.
