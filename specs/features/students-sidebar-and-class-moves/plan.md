# Clearer sidebar, graduate a learner, move a learner back: plan

## The new sidebar

| Section | Links (reports last) |
|---|---|
| *(top)* | Home · Management Dashboard · Staff Room · Class Register · Notice Board · Record Payment |
| **Students** | Dashboard · Active Students · Transferred Students · Graduated Students · All Students · Admission Applications · Class Attendance · Stream · Class · Year-end Promotion · Certificates & Letters · Verified Documents · *Class Enrolment · NEMIS Census · Admissions Pipeline · Daily Attendance · Attendance Register* |
| **Welfare & Discipline** | Discipline Incident · Complaint · Sick Bay Visit · Health Records · Visitor Log · Gate Pass · *Discipline Summary · Complaints Summary · Sick Bay Register · Visitor Register* |
| **Boarding** | Dormitory · Boarding Allocation · Exeat · *Dormitory Occupancy · Exeat Register* |
| **Academics** | Timetable · Homework · Subject · Period · School Activity · *Homework Register · Teacher Workload* |
| **Exams & CBC** | Exam · Enter Marks · Marks to Approve · Report Card · Competency Assessment · CBC Progress Report · CBC Strands · Grading Scale · *Merit List · Subject Analysis · CBC Summary* |
| **Library** | Library Books · Library Loans · *Library Overdue Books · Library Circulation* |
| **Fees** | Dashboard · Fee Payment · Student Invoices · Paybill Transactions · Portal Payments (STK) · Fee Billing Run · Fee Structure · Fee Type · *Fee Balances · Fee Collection · Fee Structure Matrix · Paybill Reconciliation* |
| **Pocket Money** | Pocket Money · Pocket Money Transactions · *Pocket Money Balances · Pocket Money Statement* |
| **Finance** | Dashboard · School Expense · Expense Category · Suppliers · Supplier Bills · Customers · Customer Invoices · Payments · Bank Reconciliation · Journal Entry · Withholding Tax Types · *Income vs Expenses · Expense Register · VAT Summary · Withholding Tax Register · Customer Balances* |
| **Staff** | Dashboard · Staff Member · Teacher · Leave Application · Leave Type · Duty Roster · Duty Report · *Leave Balance · Staff On Leave · Duty Reports Register* |
| **Transport** | Dashboard · Transport Route · School Vehicle · Driver Daily Log · *Transport List · Driver Check-in Register · Vehicle Fuel and Mileage* |
| **Parents & Messages** | Parent Messages · Parent Logins · *Parent Portal Access* |
| **Accounts** | *Accounts Receivable · Accounts Payable · General Ledger · Trial Balance · Profit and Loss · Balance Sheet · Cash Flow · Bank Reconciliation Statement* |
| **Setup** | School Settings · School Year · School Term · Staff Users · Job Roles · Admission Settings · Library Settings · CBC Settings |

Built by a script (`scripts/regroup_sidebar.py`, kept for future edits) that moves the existing link objects, so
icons, filters and flags are untouched; it fails if a link would be lost or doubled. `modified` bumped.

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| Sidebar | Sidebar JSON, migrate sync, licence filter (sections with no links left disappear) | Regrouping script |
| Graduate | Student status Graduated (exists), leaving date/reason fields | Status → Graduate prompt; Re-admit allowed from Graduated |
| Move Class | Student stream/class, Comment on the timeline | `api/students.move_class()`; `logic/promotion.move_kind()` (back / up / same class, by class `level`) |
| Bulk | List view actions menu | `api/students.bulk_move`, `bulk_graduate` (each learner saved through the same rules; per-learner errors reported) |
| Move back from a promotion | — | `api/students.move_back_from_promotion(promotion, student)`; button on a submitted Student Promotion; item marked "Moved back" |
| Invoice warning | Sales Invoice (student, school_term) | Returned as a warning when the learner has an invoice for the current term |

## Changes

| File | Change |
|---|---|
| `school_erp/school/sidebar/school/school.json` | Regrouped |
| `scripts/regroup_sidebar.py` | The regrouping, re-runnable |
| `school_erp/logic/promotion.py` | `move_kind()` |
| `school_erp/api/students.py` | New: move_class, bulk_move, bulk_graduate, graduate, move_back_from_promotion |
| `school_erp/school/doctype/student/student.js` | Status → Graduate, Re-admit from Graduated, Class → Move Class |
| `school_erp/school/doctype/student/student_list.js` | Actions: Move to Stream, Mark as Graduated |
| `school_erp/school/doctype/student_promotion/student_promotion.js` | Move a Student Back |
| `school_erp/tests/test_logic.py`, `tests/test_class_moves.py` | Tests |

## Data and migration

No new fields. Promotion item status gains the value "Moved back" (Select option added).

## Risks

- People used to "Reports → X" find reports in their area now: the user guide is updated in the same PR's follow-up.
- Moving a learner mid-term: invoices stay; the warning tells the bursar.

## Deploy notes

JS changed: `bench build --app school_erp`; migrate (sidebar, Select option); clear-cache.
