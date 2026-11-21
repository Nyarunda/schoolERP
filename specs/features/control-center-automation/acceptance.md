# Control Center automation (phase 2): acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | Disk 1000 GB with 50 GB free, threshold 10% | Problem reported; 200 GB free: none; 4 GB free on a small disk: problem | `test_service_rules::test_disk_problem` | [ ] |
| 2 | Certificate notAfter string | Days left computed | `test_service_rules::test_cert_days_left` | [ ] |
| 3 | Ping results over checks | Alert on 2nd failure in a row, recovery alert on next success, nothing otherwise | `test_service_rules::test_down_change` | [ ] |
| 4 | A git HEAD with a ref, or detached | The commit is read | `test_service_rules::test_commit_from_git` | [ ] |
| 5 | Update All Schools with 2 live schools, 1 busy | A batch: one Migrate queued, one skipped; one job enqueued | `test_service::test_update_all_batches` | [ ] |
| 6 | The batch job runs | Operations run in order; batch status lists each result | `test_service::test_process_batch_in_order` | [ ] |
| 7 | Code commit changes (setting on) | One After-update batch; same commit again: none | `test_service::test_auto_update_once_per_commit` | [ ] |
| 8 | Bulk action Back Up on selected schools; Restore asked | Batch of Backups; Restore refused | `test_service::test_bulk_action` | [ ] |
| 9 | A school stops answering twice, then answers | One down alert, one recovered alert | `test_service::test_watch_alerts_on_change` | [ ] |
| 10 | Service Health | Machinery problems, disk, one row per live school | `test_service::test_service_health` | [ ] |
| 11 | Tell About Maintenance for 2 schools | Each school's admin emailed | `test_service::test_maintenance_notice` | [ ] |
| 12 | A non-admin | Permission error on every method | `test_service::test_admin_only` | [ ] |

## Not broken

- [ ] `./scripts/check.sh` and CI green
- [ ] Open Site operations and phase 1 backups unchanged

## Docs

- [x] `platform/stemic_control/README.md`: Service automation section
- [x] `CHANGELOG.md`
