# Control Center automation (phase 2): plan

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| Batches | SaaS Site Operation (+ `batch`), one RQ job on `long` | `service.start_batch` creates the ops without enqueueing them; `service.process_batch` runs them in order through `site_runtime.perform_operation` |
| Update all / bulk | whitelisted methods; list view `add_action_item` | `update_all_schools`, `bulk_action`, `batch_status` |
| Auto-update | Frappe scheduler (hourly) | `service.auto_update`: reads the app's git commit (`.git/HEAD` → ref file / packed-refs) |
| Health watch | scheduler cron `*/15`; `site_runtime.served_at`; `shutil.disk_usage`; `ssl` | `service.watch`, `service.check_certificates` (daily); counts kept in Redis cache |
| Alerts | `alerts.notify_admins` | titles with state, so each change alerts once |
| Health screen | `health.check()` | `service.service_health()` + dialog |
| Maintenance notice | `frappe.sendmail` | `service.notify_maintenance` |

Pure rules in `service_rules.py`: `disk_problem`, `cert_days_left`, `down_change`, `commit_from_git`.

## Changes

| File | Change |
|---|---|
| `stemic_control/service_rules.py`, `tests/test_service_rules.py` | pure rules + tests (CI quick checks) |
| `stemic_control/service.py` | batches, update all, bulk, auto-update, watch, certificates, health, maintenance notice |
| SaaS Site Operation | `trigger` + Bulk, After update; `batch` (Data) |
| Stemic Settings | tab **Service**: update after code change, watch schools, disk alert %, certificate alert days, hidden last commit |
| `site_runtime.queue_operation` | `batch` argument |
| hooks | cron `*/15` watch; hourly auto_update; daily certificates |
| JS | Schools list: Update All Schools, Service Health, bulk actions; Stemic Settings: Service menu |
| tests | `tests/test_service.py` |

## Risks

- A batch with many schools takes long: the job timeout is per school × count (capped 12 h); a stuck school's
  operation fails on its own timeout and the batch moves on.
- Auto-update right after deploy may overlap with the owner's own `bench --site all migrate`: the per-site lock skips
  sites with an operation running, and migrate is safe to run twice.
- Ping from the server to its own public address may fail behind some NAT setups; the alert says how it was checked.

## Deploy notes

`bench --site all migrate`, `bench build --app stemic_control`, restart.
