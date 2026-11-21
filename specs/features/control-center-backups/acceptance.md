# Control Center: school backups and restore: acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | Backup output from `bench backup --with-files` | Database, config, public, private paths and sizes are read | `test_backup_rules::test_parse_backup_output` | [ ] |
| 2 | 30 nightly backups, 1 pinned | Newest 7 daily, 4 weekly, 6 monthly, the pinned one and the newest kept; the rest pruned | `test_backup_rules::test_to_prune` | [ ] |
| 3 | A Backup operation succeeds | A SaaS Backup (kind Manual/Scheduled) with its files and size | `test_backups::test_backup_is_recorded` | [ ] |
| 4 | S3 destination set | The files are uploaded under `<folder>/<site>/<file>`; status Uploaded; an upload failure is Failed and alerted | `test_backups::test_offsite_upload` | [ ] |
| 5 | Test Destination | Writes and deletes a test object; a bad key gives a readable error | `test_backups::test_test_destination` | [ ] |
| 6 | The chosen hour comes | One Scheduled Backup queued per live school on this bench, not twice the same day | `test_backups::test_nightly_queue` | [ ] |
| 7 | Prune runs | Server files of pruned backups deleted, record Removed; off-server objects older than N days removed; pinned kept | `test_backups::test_prune` | [ ] |
| 8 | A live school with no backup in 26 h | Platform admins alerted once | `test_backups::test_watchdog` | [ ] |
| 9 | Restore with the wrong site typed, or another school's backup | Refused | `test_backups::test_restore_guards` | [ ] |
| 10 | Restore confirmed | Before-restore backup, maintenance on, restore (+files), migrate, maintenance off, school admin emailed, op Succeeded | `test_backups::test_restore_runs_in_order` | [ ] |
| 11 | Restore fails mid-way | Maintenance still switched off; op Failed; admins alerted; safety backup kept | `test_backups::test_restore_failure_turns_maintenance_off` | [ ] |
| 12 | Backups list | Shows the school's backups, newest first; download gives the file (server) or a short link (off-server); pin toggles | `test_backups::test_list_download_pin` | [ ] |
| 13 | A non-admin calls any of these | Permission error | `test_backups::test_admin_only` | [ ] |

## Not broken

- [ ] `./scripts/check.sh` and CI green
- [ ] Existing Open Site operations (Backup, Migrate, Clear Cache, Reset Admin Password) unchanged
- [ ] No secret in any operation output or log

## Docs

- [x] `platform/stemic_control/README.md`: Backups section
- [x] `CHANGELOG.md`
