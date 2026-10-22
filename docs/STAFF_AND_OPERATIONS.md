# Staff, Finance, Transport & Welfare

Four add-on modules. Each is switched on by the school's license key: `staff`, `expenses`, `transport_ops`, `welfare`.

Everything sends **alerts** four ways: a **live toast** (pop-up) for anyone logged in, the bell in the desk (in-app), email (per each user's notification settings), and **SMS** if the `messaging` module is on and *School Settings → Staff & Approvals → Also SMS staff* is ticked. Staff need a phone number on their Staff Member record for SMS.

## First-time setup

1. **School Settings → Staff & Approvals**
   * *Head Teacher / Principal (login)*: approves leave for anyone without a "Reports To", gets duty reports and serious alerts.
   * *Expense approvals*: "One approval up to" (default 10,000). Above that, a second, final approval is needed. Pick the roles: blank means Bursar first, Head Teacher final.
   * *Teacher on Duty*: who receives duty reports, and the time after which missing reports are chased (default 5 pm).
   * *Driver Check-in*: the transport manager's login and the time drivers must check in by (default 06:30).
   * *Complaints*: the SMS texts sent to complainants, and how many web complaints one phone may send per day.
2. Click **Run School Setup** again. It adds the standard leave types (Annual 21, Sick 14 with a doctor's note, Maternity 90, Paternity 14, Compassionate 5, Study 10, Unpaid) and expense categories mapped to your chart of accounts. Adjust them as you like.
3. Create **Staff Members** (teachers, drivers, cooks, office...). Give each a phone number and, so they can use the system themselves, a **login** (User). The app then gives that login the right roles automatically: *Staff* for everyone, plus *Teacher* or *Driver*. Teaching staff automatically get a Teacher record for the timetable.
4. Set **Reports To** on staff whose leave a deputy or HOD should approve instead of the Head Teacher.
5. Assign roles by hand to: the **Head Teacher** (role *Head Teacher*), the **Bursar** (*Bursar*), and the **Transport Manager** (*Transport Manager*).

## Teachers & staff management
* **Staff Member** holds everyone: type, designation, department, TSC number, phone, login, who they report to, and driving licence expiry for drivers. The form shows each person's leave balances.
* **Teacher Workload** report: lessons per week, classes and subjects per teacher (from the timetable).

## Leave
1. A staff member opens **Leave Application** (from their phone or desk), picks the leave type and dates, gives a reason, and chooses a **reliever** if required.
   * Working days are counted automatically, skipping weekends and the company holiday list (except types marked "count weekends", e.g. maternity).
   * It checks the yearly balance, gender (maternity/paternity), overlapping leave, that the reliever isn't on leave themselves, and that a document is attached when needed.
2. The approver is alerted (toast + bell + email + SMS). They open it and use the workflow **Actions** menu: **Approve** or **Reject** (a reason is asked for before rejecting). Only the applicant's own approver (their *Reports To*) or the Head Teacher sees these actions.
3. On approval:
   * **the applicant** is told it is approved and who the reliever is;
   * **the reliever** is told whom they are covering, and for which dates.

   The applicant also gets a **toast** — green for approved, red for rejected. On rejection the applicant gets the reason. Cancelling approved leave tells the reliever they're released.
4. Staff status changes to *On Leave* automatically on the first day and back to *Active* afterwards.

Reports: **Leave Balance** (entitled / taken / left per type for every staff member) and **Staff On Leave** (who's away on a given day, their reliever and the reliever's phone).

## Teacher on duty
* **Duty Roster**: who is Teacher on Duty (and deputy, boarding master) for a week. Everyone on it is notified.
* **Duty Report**: the teacher on duty fills it daily: arrival time, assembly, late students/staff, lessons, meals, cleanliness, sick bay, visitors, incidents, remarks. One per teacher per day. On submit the Head Teacher gets it at once; problems (poor day, incidents, missed lessons, meals) are flagged in the subject and sent by SMS.
* If today's teacher on duty hasn't submitted by the due time, they get a reminder and the Head Teacher is told.
* **Duty Reports Register** shows every school day: who was on duty and whether they reported (missing ones in red).

## Finance: expenses & approvals
1. Anyone with the *Staff* role can raise a **School Expense**: category, amount, who was paid, which cash/bank/M-Pesa account it came from, receipt number, and a photo of the receipt. Then they choose **Actions → Send for Approval**.
2. **Up to the limit:** one approval by the first-level role (Bursar).
   **Above the limit:** the Bursar approves first, then the final role (Head Teacher).
   * Nobody can approve their own expense, and the same person can't give both approvals.
   * Each approver is alerted (toast + bell + email + SMS) when it's their turn and decides from the **Actions** menu.
   * The requester gets a toast when it is approved (green) or rejected (red, with the reason), and can edit and **Resend** a rejected one.
3. When fully approved, the expense is **posted automatically** as a Journal Entry: debit the category's expense account, credit the payment account. Rejecting requires a reason and posts nothing. Cancelling an approved expense reverses its Journal Entry.
4. Reports: **Expense Register** (by date, category, status, with approved vs awaiting totals) and **Income vs Expenses** (per month: fees billed, fees collected, expenses, and the difference).

## Transport: driver morning check-in
1. Every morning **before the pickup run**, the driver opens **Driver Daily Log** on their phone. Driver, vehicle, route and last odometer are filled in for them.
2. They tick the safety checklist (tyres, brakes, lights, seat belts, doors/emergency exit, mirrors, wipers, horn, first aid kit, fire extinguisher, oil & coolant, cleanliness). **Everything is OK** ticks all, then they untick anything faulty and describe it. They enter odometer and fuel level and must tick **"I am fit to drive"** to submit.
3. If anything isn't OK, or the vehicle's insurance/inspection or the driver's licence has expired, the **transport manager is alerted immediately** (bell + SMS).
4. Later the driver can add fuel bought, end odometer (distance is calculated) and students carried.
5. At the check-in deadline, the transport manager gets a list of drivers on active routes who **haven't checked in**, and those drivers get a reminder. Drivers on approved leave are skipped.
6. Daily, the transport manager is warned about insurance, inspection, speed governor and driving licences expiring within 14 days.

Set up **School Vehicles** (registration, seats, default driver, expiry dates), and on each **Transport Route** pick the vehicle and driver.

Reports: **Driver Check-in Register** (who checked in when, late, issues, and who hasn't checked in today), **Vehicle Fuel and Mileage** (km, litres, cost, km/L, cost/km per vehicle), **Transport List** (students per route and pick-up point with parent phone; also the lunch list).

## Welfare: discipline & complaints
**Discipline Incident**: student, date, category, severity, what happened, action taken (warning … suspension with dates … expulsion), follow-up date. Major/Critical incidents alert the Head Teacher. **SMS Parent** sends the guardians a notice. **Discipline Summary** groups incidents by class, category or student.

**Complaints**
* Staff log calls and walk-ins as **Complaint** records.
* Parents can also use the public form at **`https://<school-site>/complaint`**, with no login needed. It accepts only the complaint fields and is limited to a few per phone number per day.
* The complainant gets an SMS with a reference number. Urgent ones also alert the Head Teacher by SMS.
* Assign a complaint to a staff member and they're notified and can see it.
* Marking it **Resolved** requires a resolution note and SMSes the complainant.
* Parents can check progress at **`/complaint-status`** with their reference and phone number. They see the status and resolution only, never internal notes.
* **Complaints Summary** shows counts by category, open vs resolved, and average days to resolve.

## Fees differ per class and per term
That's how fee structures work: for each **term**, create one **School Fee Structure per class** (and/or Day vs Boarder), or a general one for all classes plus class-specific ones that override it per fee type.
* **Copy a term to another term** (Fee Structure list or form) duplicates every class's structure into the next term, optionally raising fees by a % and rounding (e.g. to the nearest 50).
* **Fee Structure Matrix** report shows the total per class (rows) × term (columns) for a school year, so you can compare at a glance.

## Sidebar
The School sidebar is arranged in sections: **Students & Welfare, Fees, Finance, Staff, Transport, Academics, Reports, Setup**, with quick links to Students and Record Payment at the top. Each area also has its own dashboard page (Fees and Finance, Staff, Transport, Students and Welfare, Academics). Users only see what their roles allow.

## Who sees what
| Role | Sees |
|---|---|
| Staff | Their own leave applications and expense requests |
| Teacher | Own duty reports; records discipline incidents; timetables |
| Driver | Own check-in logs; vehicles (read) |
| Bursar | All expenses (first approval), fees, payments |
| Head Teacher | Everything above: approves leave and final expenses, receives duty reports, complaints, serious incidents |
| Transport Manager | All driver logs and vehicles, check-in alerts |
| School Admin | Everything |

## Approvals run on Frappe Workflows
Leave and expense approvals use Frappe's built-in **Workflow** engine: *School Leave Approval* and *School Expense Approval* (see **Workflow** list). They are created on install/migrate and rebuilt when you change the approver roles in School Settings.

* States show on the form and in list views; the **Actions** button only shows what the current user may do.
* Anyone set as someone's **Reports To** automatically gets the *Leave Approver* role, and can only decide their own team's leave.
* You can deactivate a workflow (untick *Is Active*); the app won't recreate it on migrate. A custom first/final expense approver role needs **Submit** permission on School Expense.
