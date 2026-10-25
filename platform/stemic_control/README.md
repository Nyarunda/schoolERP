# Stemic Schools control plane (review implementation)

A dedicated **Frappe v16** app for the separate `admin.stemischools.com` management site. Do **not** install this on a school tenant.

## Delivered

Seven DocTypes: SaaS Tenant, SaaS Domain, SaaS Plan, SaaS Subscription, SaaS Agent, SaaS License, SaaS Provisioning Job. Administrative endpoints for tenant registration, domain claim requests, idempotent provisioning requests, and a dashboard overview. Only System Manager and Stemic Platform Admin can invoke them. Each application site continues to have a separate database.

**Important:** This is a reviewable **control-plane foundation**, not an operational production SaaS. Provisioning requests are recorded but do not yet execute Bench, create databases, change DNS, provision TLS, or issue licenses. Domain ownership verification, subscription invoicing, agent commissions, secret storage and signed-license issuance are not yet implemented. Domain claims must stay Pending Verification until trusted DNS verification is implemented. No live school should be onboarded automatically with this branch.

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
- `POST /api/method/stemic_control.api.queue_provisioning` (idempotent queue record, **no site creation**)
- `GET /api/method/stemic_control.api.overview`

Never put private license-signing keys or database root passwords on tenant sites. Use distinct roles for platform operators versus school administrators.

## Review checklist

1. Install on a disposable admin site; migrate and inspect DocTypes.
2. Confirm Guest and agent users cannot call the four administration APIs.
3. Confirm duplicate slugs/domains are rejected.
4. Request a tenant, subdomain, and custom hostname; verify ownership remains Pending Verification.
5. Queue a provisioning request twice with the same key and confirm it creates only one job.
6. Confirm no jobs execute shell commands or create databases.
7. Add real DNS ownership verification, provisioner authentication and status transitions before activating tenants.
