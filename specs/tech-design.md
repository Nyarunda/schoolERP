# Technical design

*How each requirement in `brief.md` is met: which standard Frappe/ERPNext feature we use, and where custom code is
genuinely needed. Update this file when a design decision changes; feature `plan.md` files point back here.*

## Shape of the system

```
admin.stemicschools.com (Frappe v16 + stemic_control)      one bench, one database per site
  schools, plans, subscriptions, licences, domains,  ───►  <school>.stemicschools.com (Frappe v16 + ERPNext v16 + school_erp)
  provisioning jobs, invoices, agents, alerts               test.stemicschools.com = Stemic Test School
Cloudflare (Full strict, wildcard *.stemicschools.com) → nginx (host → site, stemic-domains-sync for custom domains)
```

`school_erp` layers:

| Layer | Path | Rule |
|---|---|---|
| Business rules | `school_erp/logic/` | Pure Python, no Frappe imports, unit tested in `check.sh` |
| Frappe glue | `school_erp/api/` | Whitelisted methods, permissions, DB access; calls `logic/` |
| Model | `school_erp/school/doctype/`, `report/`, `web_form/`, `print_format/`, `sidebar/` | JSON + small controllers |
| Licensing | `school_erp/licensing/`, `logic/license.py` | Ed25519-signed keys; modules gate DocTypes, reports, fields |
| Setup | `school_erp/setup/` | Install/migrate: roles, workflows, finance, viewer, role profiles |
| Portal | `school_erp/www/` | `/parent`, `/admission-status`, `/complaint-status`, `/verify` |

## Requirement → design

| Requirement (brief) | Standard Frappe / ERPNext | Custom code |
|---|---|---|
| Learners are billable | Each Student is an ERPNext **Customer** (ID = Student ID) | Student DocType, guardians table, status flow |
| Fees and billing | **Sales Invoice**, Item per fee type, standard receivables | Fee structures, Fee Billing Run, `logic/billing.py` |
| Payments | **Payment Entry**, Mode of Payment | Fee Payment, split by fee type (`logic/allocation.py`), receipts |
| M-Pesa | — | Daraja C2B auto-posting, STK push, callback verification, Needs Review queue (`api/paybill.py`, `api/stk.py`) |
| Statements | Print formats, `frappe.utils.pdf` | `templates/fee_statement`, `logic/statement.py` |
| Approvals | **Workflow** (leave, School Expense Approval, School Marks Approval) | Approver resolution, notifications |
| Roles | Roles, DocPerm, **Role Profile** (job roles) | `setup/role_profiles.py` keeps earned roles; School Viewer read-all |
| Exams and report cards | — | Mark sheets, `logic/exams.py` (grades, competition ranks), per-stream generation, bulk PDF |
| CBC assessment | — | Strands, rubric, progress reports (`logic/cbc.py`) |
| NEMIS / KNEC | — | Government ID fields, NEMIS Census report (`logic/nemis.py`) |
| Admissions, complaints | **Web Form** | Status pages, admit-as-student |
| Parent portal | Website users, `www` pages | `api/portal.py` (children via guardian `user` link only) |
| SMS / email | Email Account, `frappe.sendmail` | School SMS Gateway (any HTTP provider), templates, `api/messaging.py` |
| Background work | **Scheduler** (daily/hourly/cron), `frappe.enqueue` | Term auto-billing, overdue exeats, M-Pesa retries, overdue library SMS |
| Licensing | — | Signed keys, hidden DocTypes/reports in boot, read-only after grace |
| Verifiable documents | — | QR + SHA-256 registry, `/verify` |
| Dashboards | Number cards, Script Reports | Management Dashboard, Staff Room pages |
| Accounting | Full ERPNext (Kenya VAT, withholding) | `setup/finance.py` gives Bursar/Admin the accounting roles |
| Platform | — | stemic_control: wizard onboarding, provisioner, licences, domains, invoices, eTIMS prep, watchdog, alerts |

## Decisions worth remembering

- **Standard first**: invoices, payments, workflows, role profiles and web forms are Frappe/ERPNext's own, so ERPNext
  reports keep working and upgrades stay cheap. Custom DocTypes only where nothing standard fits.
- **Hidden, not locked**: unlicensed DocTypes/reports are removed from the boot for every user (`hidden_doctypes`);
  a new key clears the boot cache so it shows at once.
- **One site per school**: no shared tables between schools; the Control Center only talks to sites through the
  provisioner and signed licences.
- **Positions** use competition ranking (1, 2, 2, 4); class positions always span every stream of the class.
- **Guardian → parent login** is an explicit link (`Student Guardian.user`), set by Give Parents Portal Access.
- **No real side effects in tests**: SMS, M-Pesa and email are mocked; the test site has no SMS gateway.

## Open design questions

- Several platform domains (choose a domain per school at onboarding): see roadmap.
- Automatic guardian ↔ login linking on Student save: see roadmap.
