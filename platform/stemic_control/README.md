# Stemic Schools control plane (review implementation)

A dedicated **Frappe v16** app for the separate `admin.stemischools.com` management site. Do **not** install this on a school tenant.

## Delivered

Seven DocTypes: SaaS Tenant (named by slug), SaaS Domain (named by hostname), SaaS Plan (by plan name), SaaS Subscription (`SUB-`), SaaS Agent (`AGT-`), SaaS License (`LIC-`), SaaS Provisioning Job (`JOB-`). Administrative endpoints for tenant registration, domain claims and DNS verification, idempotent provisioning requests, job results, suspend/resume and a dashboard overview. Only System Manager and Stemic Platform Admin can invoke them. Agents (role **Stemic Agent**, linked from a SaaS Agent record) can read only the schools and subscriptions carrying their agent, and their own agent record. Each application site continues to have a separate database.

**Important:** This is a reviewable **control-plane foundation**, not an operational production SaaS. Provisioning jobs are recorded and their results reported through the API, but nothing here executes Bench, creates databases, changes DNS, provisions TLS, or issues licenses. Subscription invoicing, agent commissions, secret storage, signed-license issuance and the privileged provisioner (with its own credentials) are not yet implemented. No live school should be onboarded automatically with this branch.

## Configuration (admin site `site_config.json`)

| Key | Default | Purpose |
| --- | --- | --- |
| `stemic_platform_domain` | `stemischools.com` | Domain school subdomains live under (`<slug>.<domain>`); its reserved names (admin, www, api, ...) cannot be claimed |
| `stemic_dns_over_https` | `https://cloudflare-dns.com/dns-query` | DNS-over-HTTPS resolver used to verify custom domains (JSON API) |

## Status model

- **Tenant:** Draft -> Pending (job queued) -> Provisioning (job running) -> Active, or Failed; Active <-> Suspended. Any other change is refused when the tenant is saved.
- **Provisioning job:** Queued -> Running -> Succeeded or Failed. A failed job is retried with a new idempotency key. A job's result moves its tenant (Create Site: Provisioning / Active / Failed; Suspend / Resume jobs: Suspended / Active).
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
