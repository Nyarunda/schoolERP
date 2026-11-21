# Changelog

What changed for schools and for Stemic, newest first. One line per change, in plain English, with its pull request.
Add your line in the PR that makes the change.

## Unreleased

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
