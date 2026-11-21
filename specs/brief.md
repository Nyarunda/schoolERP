# Brief: Stemic Schools

*Owner: Stemic Technologies. Everything else in `specs/` is derived from this file; change it first when the
business changes.*

## The problem

Kenyan private schools (academies, primary, junior and senior schools, boarding and day) run on exercise books,
Excel and WhatsApp. The bursar cannot say who owes what without hours of reconciling M-Pesa statements; parents
dispute balances; report cards are typed by hand; NEMIS census data is chased every term; head teachers have no
view of the school until something goes wrong.

## Who it is for

| Person | What they need |
|---|---|
| **Proprietor / director** | Fees collected vs owed, enrolment, expenses, one number they trust |
| **Head teacher** | Attendance, discipline, approvals (leave, expenses, exeat, marks), results, notices |
| **Bursar** | Bill a term in minutes, M-Pesa payments posted by themselves, balances and statements per learner |
| **Class teacher / teacher** | Register from a phone, homework, marks entry, CBC assessments, their stream's report cards |
| **Support staff** | Secretary (admissions, visitors), nurse (sick bay), librarian, matron, canteen, drivers |
| **Parents** | Balance, statement, receipts, report cards, homework, notices, pay by M-Pesa from the phone |
| **Board / auditors** | See everything, change nothing |
| **Stemic** | Onboard a school in minutes, licence modules per plan, bill subscriptions, support every school from one place |

## What it must do

1. **Fees**: fee structures per term/class/boarding, one-click term billing, payments split by fee type, receipts,
   statements, balances; M-Pesa Paybill/Till auto-posting and STK push; accounting stays standard ERPNext.
2. **Learners**: admission (including online applications), guardians, streams, status (active, transferred,
   graduated), year-end promotion, government IDs (UPI, birth certificate, KNEC) and the NEMIS census.
3. **Academics**: timetable, daily attendance, homework, exams with marks approval, positions and report cards per
   stream, CBC competency assessment with progress reports, merit lists.
4. **Welfare and operations**: discipline, complaints, boarding and exeat, sick bay and visitors, library, pocket
   money, transport and driver checks, staff leave and duty reports, expenses with approvals.
5. **Communication**: SMS and email to parents (any HTTP gateway), notices, the parent portal.
6. **Roles**: ready-made job roles; each person sees only what their job needs.
7. **Modules by licence**: a school pays for the modules it uses; unlicensed features are hidden, not just locked.
8. **Platform**: one-form onboarding, free trials, subscriptions and invoices, licence keys issued by themselves,
   custom domains, suspension and resume, backups that are checked, alerts when something fails.
9. **Trust**: QR-verifiable receipts, report cards and certificates; audit trail; Kenya Data Protection Act
   compliance (consent for marketing messages, parents see only their own children).

## Constraints

- Kenya first: KES, M-Pesa (Daraja), CBC and 8-4-4, NEMIS/KEMIS, KNEC, eTIMS for Stemic's own invoices, three
  terms a year, phone-first users on slow connections.
- Built on Frappe/ERPNext v16 and stays upgradeable: standard DocTypes and accounting wherever they fit.
- Each school is its own site and database; one school's data never reaches another.
- Plain English everywhere a school user reads.

## Success looks like

A new school is billing its term and receiving M-Pesa payments within its first week, the bursar stops reconciling
by hand, parents stop disputing balances, and report cards go out the day marks are approved.
