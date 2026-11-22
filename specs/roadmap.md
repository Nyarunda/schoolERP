# Roadmap

*Ordered list of features. Status: **Next** → **In progress** → **Done** (with PR). A feature is Done only when its
`acceptance.md` passes on test.stemicschools.com and the docs are updated. Replan here, not in the chat.*

## In progress

| # | Feature | Spec | Done when |
|---|---|---|---|
| 11 | **Control Center accounts + sidebar** (compulsory posting, Post Missing Entries, Check Ledger, Accounts/Tax/Operations groups) | `specs/features/control-center-accounts/` | Acceptance passes on admin.stemicschools.com |
| 12 | **Stemic expenses** (categories with accounts, approval posts to the GL, monthly repeats, Costs vs Revenue) | `specs/features/stemic-expenses/` | Acceptance passes on admin.stemicschools.com |
| 13 | **Refunds and credit notes** (Sales Invoice returns, refund Payment Entries, KRA flag) | `specs/features/credit-notes/` | Acceptance passes on admin.stemicschools.com |

## Next (in order)

| # | Feature | Why | Done when |
|---|---|---|---|
| 12 | **Stemic expenses** (hosting, SMS, domains, salaries, marketing by category, approval, posted to the GL; cost vs revenue) | Owner, 22 Nov: "everything through the chart of accounts" | Spec agreed |
| 13 | **Refunds and credit notes** (credit an invoice or refund a payment, linked, posted; eTIMS credit note) | Owner, 22 Nov | Spec agreed |
| 14 | **Growth and health KPIs** (MRR, ARR, new/churned schools, ARPU, collection rate, ageing, cash vs costs, by plan/county, trends) | Owner, 22 Nov | Spec agreed |

## Done

| Date | Feature | PR |
|---|---|---|
| 2026-11-22 | Control Center backups and restore (checked live: backups recorded, list, preview; long-path and nightly fixes) | #89, #92, #93 |
| 2026-11-22 | Control Center automation: Update All Schools, bulk actions, health watch, Service Health (checked live: after-update batch ran, site watch answering) | #90 |
| 2026-11-22 | Delete a school (preview checked live; deletion covered by CI) | #91 |
| 2026-11-21 | Every shilling through the General Ledger (checked live: opening entry, deposit, daily sales summary, Fine Paid, reconciliation) | #86 |
| 2026-11-21 | Clearer sidebar; graduate a learner; move learners between classes (checked live, incl. Move Class dialog) | #84, #85 |
| 2026-11-21 | Auto-link guardians to parent logins (checked live on the test site) | #81 |
| 2026-11-21 | Several platform domains (Check Domains: stemicschools.com ready, 3 schools) | #82 |
| 2026-11-21 | Sales kit: sales kit doc, School leads tracker sheet, one-page brochure | (artifacts) |
| 2026-11-21 | Guide screenshots for the 6 newer modules; PDF/Word re-exported | (user guide) |
| 2026-11-21 | Spec-driven development: constitution, feature template, CHANGELOG, sidebar guard | #80 |
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
