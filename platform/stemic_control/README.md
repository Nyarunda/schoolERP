# Stemic Schools control plane (review implementation)

A dedicated **Frappe v16** app for the separate `admin.stemischools.com` management site. Do **not** install this on a school tenant.

## Delivered

Seven DocTypes: SaaS Tenant (named by slug), SaaS Domain (named by hostname), SaaS Plan (by plan name), SaaS Subscription (`SUB-`), SaaS Agent (`AGT-`), SaaS License (`LIC-`), SaaS Provisioning Job (`JOB-`). Administrative endpoints for tenant registration, domain claims and DNS verification, idempotent per-tenant provisioning requests, guarded job results, suspend/resume and a dashboard overview. Only System Manager and Stemic Platform Admin can invoke them. Agents (role **Stemic Agent**, linked from a SaaS Agent record) can read only the schools and subscriptions carrying their agent, and their own agent record. Each application site continues to have a separate database.

**Important:** This is a reviewable **control-plane foundation**, not an operational production SaaS. Provisioning jobs are recorded and their results reported through the API, but nothing here executes Bench, creates databases, changes DNS, provisions TLS, or issues licenses. **Create Site jobs cannot be marked Succeeded until a trusted infrastructure provisioner with independent site-readiness checks exists; this prevents false Active tenants.** Subscription invoicing, agent commissions, secret storage, signed-license issuance and the privileged provisioner (with its own credentials) are not yet implemented. No live school should be onboarded automatically with this branch.

## Configuration (admin site `site_config.json`)

| Key | Default | Purpose |
| --- | --- | --- |
| `stemic_platform_domain` | `stemischools.com` | Domain school subdomains live under (`<slug>.<domain>`); its reserved names (admin, www, api, ...) cannot be claimed |
| `stemic_dns_over_https` | `https://cloudflare-dns.com/dns-query` | DNS-over-HTTPS resolver used to verify custom domains (JSON API) |

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
bench --site admin.stemischools.com install-app stemic_control
bench --site admin.stemischools.com migrate
```

Only run after reviewing app import paths and local Bench permissions. Do not use the `school.localhost` tenant site as admin.

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
