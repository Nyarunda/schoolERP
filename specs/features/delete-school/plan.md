# Delete a school: plan

| Requirement | Standard | Custom |
|---|---|---|
| Schedule / cancel / reminder / due | Frappe scheduler (daily) | `deletion.py`: `preview`, `schedule`, `cancel`, `delete_now`, `retry`, `daily`, `perform` |
| Suspend during grace | `suspension.apply` | store the previous status on the SaaS Deletion |
| Final copy | `bench backup --with-files` via `site_runtime`; S3 via `backups.Storage` | SaaS Backup kind *Final copy*, `delete_after`, tenant cleared; `backups.prune` removes it after 90 days |
| Drop | `frappe drop-site <site> --no-backup --force` with the provisioner's root account | remove `archived_sites/<site>*` |
| Records | `doc.cancel()` (reverses ERPNext entries through existing hooks), `frappe.delete_doc` | order: payments → invoices → commissions → the rest → ERPNext leftovers → school |
| Audit | new DocType **SaaS Deletion** (Data fields, not links) | |

Files: `deletion.py`, DocType `saas_deletion`, SaaS Backup (`delete_after`, `school_name`, kind *Final copy*),
SaaS Tenant status *Deleted*, `saas_tenant.js` (Delete School / Cancel Deletion), hooks daily, sidebar link,
`tests/test_delete_school.py`.

Risks: irreversible after the grace period, so: typed confirmation, 7-day grace, suspension during grace, reminder,
final copy for 90 days, never outside the school's own folders, never the admin site, audit record kept.

Deploy: migrate, `bench build --app stemic_control`.
