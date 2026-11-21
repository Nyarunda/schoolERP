# Clearer sidebar, graduate a learner, move a learner back: requirements

*Branch: `feat/students-sidebar-and-class-moves` · Includes #83 · Status: Agreed*

## Why

The owner (21 Nov): "I wanted the sidebar links to be improved, the grouping is awesome but if you can improve it
better, plus the Active, Transferred and Graduated Students is recommended, and a place to graduate a student; after
auto promote to new class we have somewhere to downgrade if necessary."

Today **Students & Welfare** holds 22 links (students, discipline, health, boarding, admissions, documents), and
**Reports** is one flat list of 41. A learner can only graduate through Year-end Promotion, and a promotion cannot
be undone: the only way back is editing the learner's class and stream by hand, with no record of why.

## Who uses it

| Role | What they do with it |
|---|---|
| Everyone | Finds things faster: each area has its own section, with its reports beside it |
| School Admin, Bursar (can edit students) | Graduates a learner, or several from the list; moves a learner (or several) to another class or stream, back or up, with a reason |
| School Admin, Head Teacher (Year-end Promotion) | Moves a promoted learner back from the promotion itself |

## Must

1. **Sidebar** grouped by what people do, each area with its own reports:
   Students · Welfare & Discipline · Boarding · Academics · Exams & CBC · Library · Fees · Pocket Money · Finance ·
   Staff · Transport · Parents & Messages · Accounts (financial statements) · Setup (all settings in one place).
   Quick links at the top stay. No link is lost; no link appears twice.
2. **Graduate** on a learner (Status menu): date and note; status Graduated, shown in the Graduated Students list.
   **Re-admit** also brings a graduated learner back.
3. **Move Class** on a learner: choose the new stream (any class), a reason (Repeating the class, Promoted by mistake,
   Moved up a class, Change of stream, Other) and a note. The class and stream change, and a line is kept on the
   learner's timeline: from, to, whether it was back or up, the reason and who did it.
4. From the **student list**, select learners and **Move to Stream** or **Mark as Graduated** in one go.
5. On a completed **Year-end Promotion**, **Move a Student Back** returns a promoted learner to the class and stream
   they were promoted from, and marks that line on the promotion.
6. Invoices already raised are not changed; the person is told if the learner has an invoice for the current term,
   so the bursar can adjust it.

## Must not / out of scope

- Re-bill or credit invoices automatically.
- Undo a whole promotion at once.
- Change who may edit students (same permission as editing the learner).

## Rules and permissions

Core (no module). Graduate / Move Class / bulk actions need write access to Student (School Admin, Bursar). Move a
Student Back needs write access to Student as well. Sections whose links are all unlicensed disappear, as today.

## Open questions

None: the regrouping is a proposal the owner can adjust; links keep their names except where noted in the plan.
