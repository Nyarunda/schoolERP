# Class attendance and marks approval

## Daily class attendance (every school, part of core)

**Taking the register (teachers, on a phone):** sidebar → **Class Register**.
1. Your class opens automatically (the stream where you are *Class Teacher*); pick another stream or date if you need to.
2. Everyone starts as **P**resent. Tap **A**bsent, **L**ate or **E**xcused for the few who aren't. Tap a name to add a note ("sick", "came at 9:10").
3. Tap **Save register**. You can save again during the day; it updates the same register.

The Staff Room reminds a class teacher whose register is not in yet, and has a **Take register** button.

**Rules**
* One register per stream per day; no future dates.
* Teachers can only change today's register. *School Settings → Daily Operations → Teachers can change a register for (days)* widens that. The Head Teacher and School Admin can always correct older registers.
* **Late** counts as attending. **Excused** (sick note, school trip) does not.

**Telling parents (needs the SMS module).** Tick *School Settings → Daily Operations → SMS parents when a child is marked absent* and adjust the *Absence SMS* text (placeholders: `{first_name} {student_name} {student_id} {date} {guardian_name} {school_name}`).
* Each parent gets one SMS per child per day, when the child is first marked absent.
* Saving again doesn't resend it.
* Registers filled in for an earlier day never text parents.

**Seeing it**
* **Management Dashboard:** *Attendance today* tile; after 9am, *Class registers not taken today* under "Needs your attention".
* **Daily Attendance** report: every stream for a day, missing registers first.
* **Attendance Register** report: per student over a date range. Use *Only below (%)* to list children who need follow-up.
* **Parent portal:** each child's attendance this term, with recent absences.

## Marks approval (exams module)

Marks reach report cards only after the subject's **Head of Department** (or the Head Teacher) approves them. This runs on a Frappe Workflow, *School Marks Approval*.

**Set up:** on each **Subject**, set *Head of Department (login)*. That user is given the *Head of Department* role automatically. Subjects without one go to the *Head Teacher / Principal* set in School Settings.

**Teacher**
1. Enter marks and Save as usual.
2. When the class is done: **Actions → Send for Approval**. Every student needs a mark or *Absent* first.
3. If it comes back **Returned**, read the reason at the top, fix the marks, Save, then **Actions → Resend**.

**Head of Department / Head Teacher**
* Each sheet sent gets you a toast, a bell notification and an email; the Staff Room shows the count.
* On a sheet: **Actions → Approve** (this submits it) or **Return** (you're asked what to correct; the teacher gets a red toast with it).
* For a whole class at once: open the **Exam** → **Approve Marks (n)**. You see each sheet's students, absentees, average and high/low; untick any that look wrong, open them to return them, and **Approve selected**.
* A Head of Department can't approve a sheet they entered themselves; the Head Teacher can.

**Report cards** use approved sheets only. *Generate Report Cards* warns if some sheets are still waiting.

The Exam's progress grid shows each stream × subject:
* ✓ approved
* ⏳ waiting for approval
* ↩ returned
* … in progress

**Switching it off:** untick *School Settings → Parent Portal & Exams → Marks must be approved before report cards*. Teachers then Submit sheets directly, as before.

Mark sheets submitted before this feature existed count as approved.
