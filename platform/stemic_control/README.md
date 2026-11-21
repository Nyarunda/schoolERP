# Stemic Schools control plane (review implementation)

A dedicated **Frappe v16** app for the separate `admin.stemicschools.com` management site. Do **not** install this on a school tenant.

## Delivered

Seven DocTypes: SaaS Tenant (named by slug), SaaS Domain (named by hostname), SaaS Plan (by plan name), SaaS Subscription (`SUB-`), SaaS Agent (`AGT-`), SaaS License (`LIC-`), SaaS Provisioning Job (`JOB-`). Administrative endpoints for tenant registration, domain claims and DNS verification, idempotent per-tenant provisioning requests, guarded job results, suspend/resume and a dashboard overview. Only System Manager and Stemic Platform Admin can invoke them. Agents (role **Stemic Agent**, linked from a SaaS Agent record) can read only the schools and subscriptions carrying their agent, and their own agent record. Each application site continues to have a separate database.

**Important:** This is a reviewable **control-plane foundation**, not an operational production SaaS. Provisioning jobs are recorded and their results reported through the API, but nothing here executes Bench, creates databases, changes DNS, provisions TLS, or issues licenses. **Create Site jobs cannot be marked Succeeded until a trusted infrastructure provisioner with independent site-readiness checks exists; this prevents false Active tenants.** Subscription invoicing, agent commissions, secret storage, signed-license issuance and the privileged provisioner (with its own credentials) are not yet implemented. No live school should be onboarded automatically with this branch.

## Onboarding a school (one form)

**Onboard a School** (the Overview page's main button, and the Schools list) does in one step what used to take five
forms: it registers the school, reserves `<address>.<platform domain>`, puts it on a plan, starts its **free trial**
(or invoices and records its **first payment**, or marks it **internal / demo**), claims its own domain if it has one,
and approves it and queues its site. Every step goes through the same guarded function an operator would press by
hand (`stemic_control/wizard.py`), in one transaction: if any step is refused, nothing is kept and the form says which
step and why. Choose "Send to another admin to approve" to keep the four-eyes approval, or "Save as a draft".

Defaults (plan, trial length, how schools usually start, build straight away) are in **Stemic Settings > Onboarding**.

## What happens by itself

| When | What | Switch (Stemic Settings > Onboarding) |
| --- | --- | --- |
| A school's site is built (or an existing site is linked) | The licence key for its plan is signed and emailed | Issue the licence key when a site is ready |
| A payment extends a subscription | A new key for the new end date (the old one would stop working) | Issue a new key after each renewal |
| A free trial is 7 days from its end | Its first invoice is raised, starting the day after the trial | Invoice schools before their trial ends |
| A free trial is 3 days from its end | The school is reminded by email (and SMS), once | Remind the school 3 days before |
| A subscription is saved | The school's form points at it (unless it already has a live one) | always |

If a key cannot be issued (no signing key on the server, an ended subscription), nothing else is held up: the
platform admins get an alert saying why, and Issue License on the subscription does it by hand.

## Configuration (admin site `site_config.json`)

| Key | Default | Purpose |
| --- | --- | --- |
| `stemic_platform_domain` | `stemicschools.com` | The default domain school subdomains live under (`<slug>.<domain>`); its reserved names (admin, www, api, ...) cannot be claimed. Further domains: **Stemic Settings > Platform Domains** (see `server/README.md`, "Adding another platform domain") |
| `stemic_dns_over_https` | `https://cloudflare-dns.com/dns-query` | DNS-over-HTTPS resolver used to verify custom domains (JSON API) |

## Backups and restore

Each school's site is backed up from here; settings in **Stemic Settings > Backups**.

- **Nightly**: every live school on this bench (Active or Suspended) at the chosen hour (default 01:00), one at a time,
  with or without uploaded files. **Back Up All Schools Now** queues them at once.
- **Where**: *This server only*, or *This server + S3-compatible storage* (endpoint, region, bucket, folder, keys):
  Backblaze B2, Wasabi, AWS S3, DigitalOcean Spaces, Cloudflare R2, MinIO. **Test Destination** writes and deletes a
  test file. Each backup is copied right after it is taken; failed copies are alerted and retried next night.
- **Retention**: on the server the newest of each of the last 7 days, 4 weeks and 6 months (settings); off-server
  copies for 90 days (0 = forever). Pinned backups and the newest are never removed.
- **The school's Backups button**: every backup (nightly, manual, before restore, or found in the site's backups
  folder), download (from the server, or a 15-minute link to the off-server copy), pin, restore.
- **Restore** (platform admins): type the site name; a pinned safety backup is taken first (nothing is touched if
  it fails); maintenance mode on; `restore` with files; `migrate`; maintenance always off again; the school's admin
  is emailed and platform admins alerted. Only a school's own backups can be restored to it. Each run is a
  **Site Operation** with its output (secrets removed).
- **Alerts**: failed backup or off-server copy, failed restore, and any live school without a backup for 26 hours.

## Service automation

- **Update All Schools** (Schools list > Service, or Stemic Settings): migrates every live school on this bench one at
  a time in one background job (a *batch* of Site Operations); schools with an operation running are skipped and
  listed. **After a code change** (Stemic Settings > Service, on by default) the same runs once by itself when the
  School ERP commit on this bench changes.
- **Bulk actions** (Schools list, tick schools > Actions): Back Up, Update (Migrate), Clear Cache as one batch;
  **Tell About Maintenance** emails each school's admin the time and message.
- **Health watch**: every 15 minutes each live school's `/api/method/ping` (public address in production; alert after
  two failures in a row and again when it answers), and the disk (alert under the set % or 5 GB free); daily, each
  school address's HTTPS certificate (alert within the set days).
- **Service Health** (Schools list > Service): workers/scheduler/queues, disk, and per school: site check,
  certificate days, last backup, last operation; batches running.

## Status model

- **Tenant:** Draft -> Pending Approval -> Approved (or Rejected) -> Pending (job queued) -> Provisioning (job running) -> Active, or Failed; Active <-> Suspended. A rejected school only goes back to Draft. Any other change is refused when the tenant is saved.

### Provisioning safeguards (`onboarding.py`)

A site is built only when all three hold, and is otherwise refused by default:

1. **Approved.** An operator (System Manager or Stemic Platform Admin) approves the school. The approval fields (who, when, note) are written only by the approval actions, never by a form save or REST.
2. **Commercially eligible.** One of the school's subscriptions must be Active with a paid SaaS Invoice, an operator-approved Free Trial that has not ended, or an operator-approved Internal / Demo subscription. An ordinary unpaid subscription does not qualify, including one activated by hand.
3. **Authorised environment.** Both settings come from the admin site's `site_config.json` only, never from Stemic Settings, a school record or an API argument:
   - `stemic_provision_environment`: `production`, `staging` or `development`;
   - `stemic_provision_allowed_benches`: the bench paths sites may be built in.

   A production provisioner refuses `.localhost` sites.

`queue_provisioning` checks the first two, so the operator hears about a problem at once. The provisioner checks all three again on locked rows before it runs anything. A refused job is marked Failed with the reason, and the school goes back to Approved (or Draft) to be fixed. Each job records the environment that built it. During automated tests, Frappe's CLI refuses to run unless a test opts in with `frappe.flags.stemic_cli_in_tests`.
- **Provisioning job:** Queued -> Running -> Failed for Create Site until the provisioner is built. The transition to Succeeded is deliberately blocked for Create Site. A failed job is retried with a new idempotency key. A job's result moves its tenant (Create Site: Provisioning / Failed). Active activation is withheld until a verified provisioner is implemented.
- **Domain:** the school's own `<slug>.<platform domain>` is Verified when claimed (the platform owns that DNS). A custom domain stays Pending Verification until `verify_domain` finds a TXT record `_stemic-verification.<hostname>` holding the token returned when it was claimed.

## Installation on a separate admin Bench

Copy the `platform/stemic_control` app directory to the admin Bench apps directory and install it as `stemic_control` using supported Bench install steps. First create the admin site and install Frappe. ERPNext is optional for the admin app (required for invoicing if later integrated).

Example using a symlink for local development:

```bash
cd ~/admin-bench
ln -s /absolute/path/to/schoolERP/platform/stemic_control apps/stemic_control
./env/bin/pip install -e apps/stemic_control
bench --site admin.stemicschools.com install-app stemic_control
bench --site admin.stemicschools.com migrate
```

Only run after reviewing app import paths and local Bench permissions. Do not use the `school.localhost` tenant site as admin.

## Keeping it running (production)

Scheduled jobs run on the background workers, so if the workers stop, nothing scheduled inside Frappe can report it.
Three things cover that:

1. **Restart what crashes.** On a production server run `sudo bench setup production <user>`. It installs supervisor
   (or systemd) and nginx, and supervisor restarts the web server, workers and scheduler when they stop. `bench start`
   is for development only: it stops when its terminal closes.
2. **The watchdog.** `scripts/watchdog.py` checks the machinery from outside the workers: workers running, the
   scheduler enabled and ticking, jobs not waiting too long, school site jobs not stuck (`stemic_control.health`).
   Add it to the server user's crontab (`crontab -e`):

       */5 * * * *  cd /home/<user>/frappe-bench/sites && ../env/bin/python ../apps/stemic_control/scripts/watchdog.py <admin site>

   It emails the platform admins (System Manager / Stemic Platform Admin users with an email address) straight to the
   mail server, without the job queue, when a problem starts, every hour while it lasts and once when it clears.
   **It needs a default outgoing Email Account**; without one it prints the alert, and cron mails that to the server's
   user. It also records an Error Log entry.
3. **The Control Center shows it.** The Home page's attention list starts with "Background jobs not running" when
   anything is wrong, and the Setup Check lists each part.

**Backups:** `scripts/restore_check.py <admin site> <school site>` proves a school's backup restores (see its header).
Keep each school's `encryption_key` (in its `site_config.json`) somewhere other than its server: the backup does not
contain it, and without it a restored school's stored passwords and secrets are unreadable.

## Schools' own domains (production)

A verified custom domain is set up on the server by `stemic-domains-sync` (no hand-edited nginx), checked live from
the Control Center, and can become the school's main address. One-time install and certificates: `server/README.md`.

## Secrets (production)

Two secrets let the control plane act on the server: the password of the MariaDB account that creates school
databases, and the file holding the license signing key. In development they can sit in the admin site's
`site_config.json`; in production keep them out of it (every bench command and every backup can read that file):

1. **A file only the bench's user can read**, outside the bench:

       sudo install -d -m 700 -o <user> /etc/stemic
       sudo install -m 600 -o <user> /dev/null /etc/stemic/secrets.env

   with

       STEMIC_DB_ROOT_USERNAME=stemic_provisioner
       STEMIC_DB_ROOT_PASSWORD=<its password>
       STEMIC_LICENSE_PRIVATE_KEY_FILE=/etc/stemic/vendor.key      (also mode 600)

2. **Load it into the bench's processes.** With supervisor (from `bench setup production`), add to each program in
   `config/supervisor.conf`: `environment=` with those variables, or start supervisord with them in its environment;
   with systemd, `EnvironmentFile=/etc/stemic/secrets.env`. The environment wins over `site_config.json`
   (`stemic_control.config.secret`), and the Setup Check shows where each secret comes from.
3. **A limited database account instead of root.** `scripts/provisioner_account.sql` creates `stemic_provisioner`,
   which can create and drop only school databases (`sch_...`) and restore-check copies, and their logins. Root can
   read and drop every database on the server, including other applications'. One limit: MariaDB's CREATE USER
   privilege, which every new school's login needs, also lets it drop other logins (not read their data).

## Stemic's books (optional)

Subscription invoices, payments and agents' commission can be posted to ERPNext on the admin site, so Stemic's own
accounts (P&L, VAT, receivables, agents payable) come from the Control Center without retyping (`stemic_control/accounting.py`):

| Control Center | ERPNext | Debit | Credit |
| --- | --- | --- | --- |
| SaaS Invoice submitted | Sales Invoice (customer = the school, item = the plan) | Debtors | Deferred Subscription Income, Output VAT |
| ... each month of its period | Process Deferred Accounting (ERPNext's monthly job) | Deferred Subscription Income | Subscription Income - <plan> |
| SaaS Payment submitted | Payment Entry against that invoice | M-Pesa Paybill / Stemic Bank / Cash (by mode) | Debtors |
| Commission earned | Journal Entry | Agent Commission | Agent Commission Payable (the agent, as supplier) |
| Commission paid out | Journal Entry (Bank Entry) | Agent Commission Payable | M-Pesa Paybill / Stemic Bank |

Plan prices include VAT: with Stemic Tax Settings on Standard Rated, 16/116 of each invoice goes to Output VAT; Exempt
or Zero Rated invoices carry none. Each posting is in the same transaction as its Control Center record, so the books
never disagree with it: if ERPNext refuses (no fiscal year, a closed period, another currency), the invoice or payment
is refused with that reason. Cancelling a payment or invoice cancels its entry. Invoices raised before posting was
switched on are not back-posted (the Setup Check counts them).

To switch it on:

    bench --site <admin site> install-app erpnext       # then finish ERPNext's setup wizard: company, Kenya, KES, fiscal year

then Stemic Settings > Accounting: enter the company's exact name, save, **Set Up Accounts** (creates the accounts,
one income account and item per plan, the VAT template, the modes of payment and monthly deferred processing; safe to
run again), and tick **Post to accounts**. Check the bank and M-Pesa accounts it created against your real ones.

## What schools are told (email and SMS)

`stemic_control/communications.py`. Every message goes to the school's contact email, and to its contact phone too
when **Stemic Settings → Communications → SMS schools** is on and the gateway is filled in:

| Event | Email | SMS |
| --- | --- | --- |
| Site ready | Address, username, one-time set-password link (`welcome.py`) | Address; "we emailed you a link" |
| Invoice issued (renewals too) | Amount, period, due date, payment instructions | Invoice, amount, due date, how to pay |
| Payment received | Amount, reference, balance, active until | Short receipt |
| Invoice overdue | Reminder with how to pay (once per invoice) | Short reminder |
| License issued | The key and how to install it | "The key is in your email" |
| Suspended / resumed | Notice | Short notice |

**Platform admins** (System Manager / Stemic Platform Admin) get a one-line summary of every event above, plus **new
school registered**, in the notification bell and by email, and by SMS to their mobile number (User > Mobile No)
when SMS is on. Problem alerts (a failed or refused build, a failed site operation, invoices that disagree with their
payments) go by SMS too. Each part has a switch.

Links and license keys go by email only. Each event has its own switch on the Communications tab. Nothing is ever
sent to reserved test addresses (`*.test`, `*.example`, `*.invalid`, `*.localhost`), and nothing is queued by
automated tests. Messages are sent
in the background after the record that caused them is committed, and never block billing. Each message and channel
is recorded as a **SaaS Communication** (Sent, Failed with the reason, Skipped with the reason), which also stops the
same invoice or payment being announced twice. The SMS gateway is the same setup-based sender schools use (any HTTP
provider, success rule, https to a public address only); **Send Test SMS** on Stemic Settings checks it.

## APIs

Authenticated platform admin only:
- `POST /api/method/stemic_control.api.register_tenant`
- `POST /api/method/stemic_control.api.request_domain`
- `POST /api/method/stemic_control.api.verify_domain` (checks the TXT record over DNS-over-HTTPS)
- `POST /api/method/stemic_control.api.queue_provisioning` (idempotent queue record, **no site creation**; concurrent calls with one key return one job)
- `POST /api/method/stemic_control.api.record_job_result` (Running / Succeeded / Failed, moves the tenant)
- `POST /api/method/stemic_control.api.set_tenant_status` (Suspended / Active only)
- `GET /api/method/stemic_control.api.overview`

Never put private license-signing keys or database root passwords on tenant sites. Use distinct roles for platform operators versus school administrators.

## Tests

- Framework-free: `pytest stemic_control/tests/test_policy.py stemic_control/tests/test_api.py` (from this directory, in a Bench Python environment).
- Integration, on a disposable admin site with the app installed: `bench --site <site> run-tests --module stemic_control.tests.test_integration`. Covers tenant naming and duplicates, subdomain vs custom-domain verification (DNS mocked), idempotent and concurrent provisioning, job and tenant transitions, agent row-level access and Guest refusal.

Verified on Frappe/ERPNext 16.52: install-app, migrate, uninstall-app, 6 framework-free and 7 integration tests passing, and a live DNS-over-HTTPS TXT lookup.

## Review checklist

1. Install on a disposable admin site; migrate and inspect DocTypes.
2. Confirm Guest and agent users cannot call the four administration APIs.
3. Confirm duplicate slugs/domains are rejected.
4. Request a tenant, subdomain, and custom hostname; verify ownership remains Pending Verification.
5. Queue a provisioning request twice with the same key and confirm it creates only one job.
6. Confirm no jobs execute shell commands or create databases.
7. Before activating tenants: build the provisioner with its own credentials (calling `record_job_result`), secret storage and signed-license issuance.

## Review hardening (post-4d15e81)

- A verified domain cannot be reassigned and domain verification cannot be forged by a direct document save. Custom domains still require the DNS verification API.
- Provisioning job state and immutable identifiers cannot be edited using a normal document save; the API governs transitions.
- A per-tenant database row lock serializes Create Site requests; different active idempotency keys for one tenant are rejected.
- Subscriptions require their agent assignment to match the tenant agent. A future commission ledger must preserve historical attributions.
- Manual Create Site success is refused: a queued/running record is **not** proof that a site exists. There is currently no production-ready infrastructure provisioner.
- Integration tests added for domain status forgery, tenant reassignment, competing provisioning keys and direct job-state changes.
- The competing-job check ignores a job under the same key, so a concurrent retry still gets its job back.
- Verified on Frappe/ERPNext 16.52: 10 integration and 6 framework-free tests pass, `scripts/check.sh` passes.

## KPI dashboard (new review page)

Open `/app/stemic-overview` on the **admin** site after updating the app, migrating, clearing cache and building assets.

- Overview: Total Schools, Active Schools, Active Subscriptions, Pending Provisioning.
- Schools: Total, Active, Trial, Pending Provisioning, Failed Provisioning, Pending Domains.
- Billing: Active, Trial, Past Due, Expiring Within 30 Days.
- Agents: Total, Active, Referred Schools, Active Referrals.

The dashboard uses one role-checked read-only `dashboard_metrics` API. It uses 4/2/1-column responsive card grids and only enables clickthrough where exact list filters are available. No fictional MRR, paid invoices or commissions are displayed. The `Active Schools` count reflects an *administrative status*, not confirmed infrastructure readiness.

**Important:** This page is separate from the four local Workspaces and seeded Number Cards described in the operator's report. Those local uncommitted assets were not accessible through the GitHub connector and have not been modified or inspected. Merge their layouts only after those files are committed or provided for review.

No Bench runtime tests have been run for this change; verify `/app/stemic-overview`, agent/guest denial, responsive widths and filtered card links locally.
