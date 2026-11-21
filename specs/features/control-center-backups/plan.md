# Control Center: school backups and restore: plan

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| Take a backup | `bench --site X backup --with-files` via existing `site_runtime` operations | record a SaaS Backup from the command output |
| Restore | `frappe --site X restore <sql> --with-public-files --with-private-files --force` with the provisioner's database root account; `set-maintenance-mode`; `migrate` | `backups.perform_restore` steps, always-off maintenance in `finally` |
| Off-server | boto3 (a Frappe dependency) S3 client with `endpoint_url` | `backups.storage()` upload / delete / presign / test |
| Schedule | Frappe scheduler (hourly) | `backups.hourly()`: at the chosen hour queue one Backup per live school; prune; watchdog |
| Retention | — | `backup_rules.to_prune()` (pure, unit tested): daily/weekly/monthly + pinned + newest |
| Alerts | `alerts.notify_admins` | titles for failures and stale schools |

## Changes

| File | Change |
|---|---|
| `stemic_control/backup_rules.py` | Pure: `parse_backup_output`, `to_prune`, `offsite_expired`, `object_key`, `stale` |
| `stemic_control/backups.py` | Settings, storage client, `record_backup`, `sync_server_backups`, `upload`, `list_backups`, `download`, `toggle_pin`, `request_restore`, `perform_restore`, `hourly`, `prune`, `watchdog`, `test_destination`, `backup_all_now` |
| `stemic_control/site_runtime.py` | `ACTIONS` gains Restore (run only through `backups.request_restore`); after a Backup succeeds, `backups.record_backup`; operation `trigger` |
| DocType **SaaS Backup** (new) | tenant, site, taken_on, kind, database_file, public_file, private_file, config_file, size_mb, on_server, offsite_status (Not set up / Pending / Uploaded / Failed / Removed), offsite_key, pinned, status (Available / Removed), operation, note |
| SaaS Site Operation | `action` + Restore; `trigger` (Manual / Scheduled / Before restore); `backup` (Link SaaS Backup) |
| Stemic Settings | tab **Backups**: enable nightly, hour, with files, keep daily/weekly/monthly, destination, S3 fields, keep off-server days; buttons Test Destination, Back Up All Now |
| JS | SaaS Tenant **Backups** dialog (list, download, pin, restore with typed confirmation); Stemic Settings buttons |
| Sidebar (Control Center) | SaaS Backup link (bump `modified`) |
| hooks | hourly `backups.hourly` |
| tests | `tests/test_backup_rules.py` (pure, in CI quick checks); `tests/test_backups.py` (bench, CLI and S3 mocked) |

## Data and migration

New DocType and fields only; defaults: nightly on at 01:00, with files, 7/4/6, destination *This server only*,
off-server 90 days. Nothing runs until the next hour after deploy; existing server backups are picked up when listed.

## Risks

- **Restore overwrites live data**: strict flow (typed confirmation, safety backup first, same school only,
  maintenance always off, everything recorded). Restore is never scheduled or bulk.
- **Disk**: retention removes old server copies; the first prune may remove many old files: it only removes files
  this module recorded or found in the site's own backups folder, keeping the newest and pinned.
- **Nightly load**: one school at a time on the `long` queue.
- **Live school** (mogongapagsecondary): gets nightly backups (good); retention may prune its old manual backups
  beyond 7/4/6. Pin any you want kept before deploying.

## Deploy notes

Backup first, `bench --site all migrate`, `bench build --app stemic_control`, restart. Then in admin Stemic Settings >
Backups choose the destination and Test Destination.
