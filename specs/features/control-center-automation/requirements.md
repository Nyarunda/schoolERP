# Control Center automation (phase 2): update all schools, health watch, bulk actions

*Branch: `feat/control-center-automation` (on top of #89) · Roadmap item: #9 · Status: Agreed*

## Why

The owner: "add more controls and automation from control center to improve service delivery", then "next" after
phase 1 (backups and restore, #89). Today each school is handled one at a time from its Open Site dialog, nobody is
told when a school's site stops answering or its certificate is about to expire, and after a code update every school
must be migrated by hand.

## Who uses it

| Role | What they do with it |
|---|---|
| Stemic platform admin | Updates all schools in one click; acts on several schools at once; sees service health on one screen; is alerted when something breaks |
| Schools (indirectly) | Fewer outages, faster fixes, told ahead of planned maintenance |

## Must

1. **Update All Schools** (Stemic Settings and the Schools list): migrate every live school on this bench **one at a
   time** in a single background job, as a batch of Site Operations; a batch report shows each school's result.
2. **Automatic update after a code change** (setting, default on): when the School ERP code on this bench changes
   (new commit), all schools are updated once, the same way.
3. **Bulk actions** on the Schools list: select schools → Back Up / Update (Migrate) / Clear Cache, as one batch, one at
   a time; and **Tell About Maintenance** (date, time, message) → email to each school's admin.
4. **Health watch** every 15 minutes:
   - each live school's site answers (`/api/method/ping`, at its public address in production); alert after two
     checks in a row fail, and again when it answers once more;
   - the bench disk: alert when free space is under the set percentage (default 10%) or under 5 GB;
   - daily: each school address's HTTPS certificate expires in fewer than the set days (default 14): alert.
5. **Service Health** screen (button on the Schools list and Stemic Settings): machinery problems (workers, scheduler,
   queues: the existing health check), disk, and one row per live school: answering, certificate days left, last
   backup, last operation, any batch running.
6. Everything platform-admin only; all runs on record as Site Operations; no secrets in output.

## Must not / out of scope

- No restore in bulk; no bulk drop of sites; no action on schools whose site is not on this bench.
- Bulk Migrate never runs in parallel (two migrations at once can starve the server).
- No SMS for the maintenance notice in this phase (email only); no maintenance windows that lock schools out.

## Rules and permissions

`System Manager` or `Stemic Platform Admin` only. Schools with an operation already running are skipped in a batch
and reported as skipped.

## Open questions

- [ ] Auto-update after a code change defaults on (deploys already run `bench --site all migrate`; this catches a
  forgotten step and is harmless twice).
