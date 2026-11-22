# Changelog

What changed for schools and for Stemic, newest first. One line per change, in plain English, with its pull request.
Add your line in the PR that makes the change.

## Unreleased

- **School website**: the school's address now opens a homepage branded for the school (crest, colours, photos, fees
  and Paybill, notices, term dates, contacts), with a branded sign-in page, one header and footer on the public pages,
  and a calm "portal paused" page that keeps Stemic's invoice details for school administrators (#99).
- Control Center: **School Groups** for schools with several branches (each its own site): combined or separate
  billing, head-office statement and group payment; a **cost center per school** (branches under their group) on every
  posting, so Profit and Loss runs per school, branch and group (#98).
- Control Center: **Growth & Health** tab: MRR trend and growth, run rate, revenue per school, new and lost schools,
  churn, collection rate, overdue ageing, cash in vs costs, schools by county and plan; County on schools (#97).
- Control Center: **credit notes and refunds** on subscription invoices, posted as Sales Invoice returns and refund
  Payment Entries; invoices show credited/refunded and status Credited; KRA credit notes flagged when needed (#96).
- Control Center: **Stemic expenses**: record hosting, SMS, salaries, marketing etc. by category with receipts;
  approval posts them to the books (with claimable VAT); monthly repeats; **Costs vs Revenue** report (#95).
- Control Center: posting to the books is compulsory once the accounting company is set; **Post Missing Entries** and
  **Check Ledger**; sidebar redesigned with **Accounts** (chart of accounts, journals, GL, Trial Balance, P&L, Balance
  Sheet, Cash Flow, receivables, payables), **Tax (eTIMS)** and **Operations** groups (#94).
- Fixed (found live): backups of schools with long site names were taken but not recorded (file paths over 140
  characters); backup times used the server's file names (another time zone); nightly backups did not start when the
  last-run date was empty. Service Health now shows the nightly backup status (#93).
- Fixed: after the upgrade, the Control Center's new settings read 0 (nightly backups off, keep 0/0/0, site watch off);
  every migrate now stores the defaults of settings never set, without touching chosen values (#92).
- Control Center: **Delete School**: suspended at once, deleted after a 7-day grace (cancellable): site, database,
  backups, domains, invoices, payments and the school record are removed; a final copy is kept 90 days; tax records
  (eTIMS) and invoices filed with KRA are kept (#91).
- Control Center: **Update All Schools** (also automatic after a code change), bulk Back Up / Update / Clear Cache and
  maintenance emails from the Schools list, a 15-minute health watch (site answering, disk, certificates) with alerts,
  and a **Service Health** screen (#90).
- Control Center: nightly backups of every school, an optional off-server copy (any S3-compatible storage),
  retention, a **Backups** list per school (download, pin) and a strict **Restore** (typed site name, safety backup
  first, maintenance mode, school emailed); alerts for failed or missing backups (#89).
- Sidebar: **Chart of Accounts** under Finance (#88).
- Fixed: cash pocket money deposits and library fines paid in cash posted to the default payment mode's account (often
  M-Pesa); they now use the school's Cash mode (#87).
- Finance: every shilling now reaches the General Ledger. Pocket money (deposits, shop sales, withdrawals) posts to
  Pocket Money Held and Tuck Shop Sales; unmatched M-Pesa goes to Unidentified Receipts until assigned; library fines
  paid at the library post to Library Fines; driver fuel raises a Fuel expense for approval; **Check Ledger** shows
  anything left out (#86).
- Fixed: new buttons (Graduate, Move Class, list actions) showed only after a hard refresh, because the desk-wide
  script was cached by browsers for a year; it is now a versioned bundle that updates on every deploy (#85).
- Sidebar regrouped by what people do (Students, Welfare & Discipline, Boarding, Academics, Exams & CBC, Library, Fees,
  Pocket Money, Finance, Staff, Transport, Parents & Messages, Accounts, Setup), each area with its own reports (#84).
- Students: **Graduate** and **Move Class** (back, up or to another stream, with a reason kept on the timeline), also
  for several learners from the list; **Move a Student Back** on a completed Year-end Promotion (#84).
- Sidebar: the duplicate Students link at the top is gone; Students & Welfare lists Active, Transferred, Graduated and
  All Students together (#83).
- Control Center: school addresses can live on several Stemic domains; choose one per school when onboarding, and
  check each domain is ready from Stemic Settings (#82).
- Parents are linked to their children by themselves when a guardian's email or phone matches their login, in
  whichever order the guardian and the login were added (#81).
- Spec-driven development: `AGENTS.md`, `specs/` (brief, technical design, roadmap, feature template) and this changelog.
- Checks: a sidebar change must bump its `modified` date, or `migrate` would skip it.

## 2026-11-14

- Report cards can be generated per stream or per class; each class teacher does their own stream; a whole stream
  prints as one PDF (#79).
- 14 ready-made job roles (Head Teacher, Bursar, Teacher, Secretary, Board / Auditor…) under Setup → Job Roles
  (#77, #78).
- A new licence key shows its modules in the desk straight away; library fine invoices say "Library fine" (#76).
- Lost sidebar links put back (#75).

## 2026-11-10

- Outbound webhooks, signed (#52).
- Student status lists: Active, Transferred, Graduated; Transfer Out and Re-admit (#74).
- New modules: sick bay & visitors (#72), library (#71), pocket money (#70), boarding & exeat (#69),
  homework (#68), online admissions (#67), CBC competency assessment (#66, #73).
- Government learner IDs and the NEMIS Census report (#65).

## 2026-11-06

- Parent portal: wide tabbed layout, fee breakdown, results by subject, lessons, raise a concern (#63, #64).
- Control Center: one-form onboarding, automation, richer Overview; amounts in KES (#58, #59).
- Fix: messages to schools were never sent from the background queue (#61).

## 2026-11-05

- Daily class attendance and Head of Department approval of marks (#56).

## 2026-10-26 to 2026-10-30

- Custom domains for schools, checked live (#54, #55); School Viewer role (#53).
- Suspension, communications, welcome email, SMS gateways (#44–#51); Stemic's own books (#43).
- Provisioning, checked backups, watchdog and alerts; unlicensed features hidden (#20–#35).
- Full ERPNext accounting for schools, Kenya VAT and withholding; eTIMS preparation (#13, #14, #19).
- QR-verifiable receipts, report cards, statements and certificates (#6, #9).
- M-Pesa Till, STK push, verified callbacks, Needs Review queue (#4, #5, #7, #8, #17).
- Control-plane foundation and dashboards (#3, #10–#12).
