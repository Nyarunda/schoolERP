# Roadmap

*Ordered list of features. Status: **Next** → **In progress** → **Done** (with PR). A feature is Done only when its
`acceptance.md` passes on test.stemicschools.com and the docs are updated. Replan here, not in the chat.*

## In progress

| # | Feature | Spec | Done when |
|---|---|---|---|
| 6 | **Clearer sidebar; graduate a learner; move a learner back** | `specs/features/students-sidebar-and-class-moves/` | Acceptance passes on the test site |
| 1 | Spec-driven development: constitution, feature template, CHANGELOG, sidebar guard | `AGENTS.md`, `specs/` | Merged; next feature starts from `specs/features/_template` |

## Next (in order)

| # | Feature | Why | Done when |
|---|---|---|---|
| 2 | **Auto-link guardians to parent logins** | Parents with a login saw an empty portal (14 Nov) | Saving a Student links any guardian whose email or phone matches an existing Parent login; test proves it; guide updated |
| 3 | **Several platform domains** | Branding/country domains, spread risk | Stemic Settings lists domains (on/off, default, certificate + DNS check); onboarding picks one; no TXT step for Stemic's own domains; links follow the chosen domain |
| 4 | **Guide screenshots for the 6 newer modules** | Guide sections 5 and 8 are text only | Homework, admissions, exeat, pocket money, library, sick bay screenshots in the guide; PDF/Word re-exported |
| 5 | **Sales kit** | No first client yet | Lead tracker, first email + WhatsApp follow-up, one-page brochure, demo script on test.stemicschools.com |

## Done

| Date | Feature | PR |
|---|---|---|
| 2026-11-14 | Report cards per stream/class by each class teacher; bulk PDF | #79 |
| 2026-11-14 | Default job role profiles (14) and Setup → Job Roles | #77, #78 |
| 2026-11-14 | New licence refreshes the desk at once; library fine invoice remarks | #76 |
| 2026-11-14 | Sidebar links restored; non-group Supplier Group in tests | #75 |
| 2026-11-10 | Signed outbound webhooks | #52 |
| 2026-11-10 | Student status: Active, Transferred, Graduated lists; Transfer Out / Re-admit | #74 |
| 2026-11-10 | Sick bay, visitors, gate passes | #72 |
| 2026-11-10 | Library with fines billed to fees | #71 |
| 2026-11-10 | Pocket money | #70 |
| 2026-11-10 | Boarding and exeat | #69 |
| 2026-11-10 | Homework and assignments | #68 |
| 2026-11-10 | Online admissions | #67 |
| 2026-11-10 | CBC competency assessment and progress reports | #66, #73 |
| 2026-11-10 | Government learner IDs and NEMIS Census | #65 |
| 2026-11-06 | Parent portal: tabs, fees breakdown, results, lessons, concerns | #63, #64 |
| 2026-11-06 | Control Center: one-form onboarding and automation | #58 |
| 2026-11-05 | Daily class attendance; Head of Department marks approval | #56 |
| 2026-10-30 | Custom domains, live-checked, usable as main address | #54, #55 |
| 2026-10-29 | School Viewer read-only role | #53 |
| 2026-10-29 | Suspension, communications, welcome email, SMS gateways | #44–#51 |
| 2026-10-28 | Stemic's own books: subscription invoices, commissions | #43 |
| 2026-10-27 | Provisioning, backups checked, watchdog, alerts, licences hidden-not-locked | #20–#35 |
| 2026-10-27 | Full ERPNext accounting for schools; eTIMS preparation | #13, #14, #19 |
| 2026-10-26 | QR-verifiable receipts, report cards, statements, certificates | #6, #9 |
| 2026-10-26 | M-Pesa Till, STK, callback verification, Needs Review | #4, #5, #7, #8, #17 |
| 2026-10-26 | Control plane foundation; dashboards | #3, #10–#12 |
