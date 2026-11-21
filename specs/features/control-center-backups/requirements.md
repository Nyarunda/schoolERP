# Control Center: school backups and restore (phase 1 of service automation)

*Branch: `feat/control-center-backups` · Roadmap item: #8 · Status: Agreed*

## Why

The owner: "control center add way to take backups for clients and restore them and add more controls and automation
from control center to improve service delivery".

Today a platform admin can run **Backup** for one school from Open Site, but backups are never scheduled, can't be
listed, downloaded or restored from the Control Center, nothing is pruned (disk fills up), and every copy sits on the
same server as the school: a lost server loses the school and its backups together.

Phase 2 (separate spec): Update all schools, health watch, bulk actions.

## Who uses it

| Role | What they do with it |
|---|---|
| Stemic platform admin | Sets the schedule and where copies go; sees every school's backups; downloads; restores |
| Schools (indirectly) | Get nightly protection; their admin is emailed when their site is restored |

## Must

1. **Where backups go is a setting** (owner: "setup based, I can choose where to"): Stemic Settings > Backups >
   Destination: *This server only* or *This server + S3-compatible storage* (endpoint, region, bucket, folder, access
   key, secret key). S3-compatible covers Backblaze B2, Wasabi, AWS S3, DigitalOcean Spaces, Cloudflare R2, MinIO.
   **Test Destination** writes and deletes a small file and says plainly what failed. Google Drive is out of scope
   for now (needs its own sign-in flow).
2. **Nightly backups**: at the chosen hour (default 01:00) every live school on this server is backed up (database +
   files, toggle), one at a time, each recorded as a SaaS Site Operation and a **SaaS Backup**.
3. Every backup (nightly, manual from Open Site, or before a restore) is a **SaaS Backup** record: school, site, when,
   kind (Scheduled / Manual / Before restore), files and sizes, where it is (server, off-server), status.
   Backups already on the server from before are picked up when the list is opened.
4. **Off-server copy**: with S3 set, each backup is uploaded right after it is taken; failures are recorded and
   alerted, and retried by the next run.
5. **Retention**: on the server keep the newest 7 daily, 4 weekly and 6 monthly backups per school (settings);
   off-server keep for N days (default 90; 0 = forever). Pinned backups and the newest backup are never removed.
6. **Backups list** per school (button on the school: **Backups**): date, kind, size, where; **Download** (database /
   files; from the server, or a 15-minute link from off-server storage), **Pin / Unpin**, **Restore**.
7. **Restore (strict)**:
   - platform admins only; the admin types the school's site name to confirm;
   - a fresh **Before restore** backup is taken first; if it fails, nothing is restored;
   - the site is put in maintenance mode, restored (database, and files when the backup has them), migrated, and
     maintenance is always switched off again, even after a failure;
   - a backup kept only off-server is downloaded first;
   - only a backup of that same school can be restored to it;
   - the school's admin email is told that their system was restored and to which date; platform admins are
     alerted on success or failure; the whole run is on record (who, when, from which backup, output).
8. **Alerts**: a failed backup or off-server upload, and any live school with no successful backup in 26 hours.

## Must not / out of scope

- No restoring one school's backup into another school's site; no restore by school staff.
- No change to schools' own data or apps outside a restore.
- Secrets (S3 secret key, database root password) never shown, logged or put in operation output.
- Phase 2 items (Update all schools, health watch, bulk actions, maintenance windows) are not in this PR.

## Rules and permissions

- Everything is platform-admin only (`System Manager` or `Stemic Platform Admin`), like the existing site operations.
- Commands run only on schools whose site is on this bench, with the provisioner's environment checks.
- One operation at a time per site (existing lock), restore included.

## Open questions

- [x] Destination: configurable (owner).
- [x] Restore protection: strict (owner).
- [ ] Phase 2 order: defaulting to Update all schools → health watch → bulk actions.
