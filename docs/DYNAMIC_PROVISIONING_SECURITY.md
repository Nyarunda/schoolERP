# Stemic Control Center — Dynamic Provisioning and Secrets Management

**Status:** Architecture proposal / implementation specification  
**Applies to:** `stemic_control` in the `schoolERP` repository  
**Updated:** 2026-10-28

## Purpose

Make school provisioning automatic, secure and operationally manageable across local development, WSL, Docker and production Linux, **without weakening existing onboarding, billing, licensing, backup or tenant-isolation behavior**. This is a design and acceptance plan, **not a claim that the features below are already implemented**.

## Current baseline

PR #36 introduced `stemic_provisioner`, a `scripts/provisioner_account.sql` grant script, environment-first secret resolution and Setup Check visibility into credential sources. The documented configuration uses `/etc/stemic/secrets.env`:

```dotenv
STEMIC_DB_ROOT_USERNAME=stemic_provisioner
STEMIC_DB_ROOT_PASSWORD=<strong-unique-secret>
STEMIC_LICENSE_PRIVATE_KEY_FILE=/path/outside/bench/license-signing.key
```

These are **examples only**. Never commit real values or the private signing key.

The previous behavior can fall back to privileged values in `site_config.json`; removing that fallback is a **security-hardening migration**, so inventory existing deployments and validate worker startup before switching it off. Existing backup archives may still contain former secrets: rotate any affected credentials and apply the backup retention/remediation policy.

### Threat model

Protect other sites and apps on shared MariaDB infrastructure against accidental access and credential compromise. The provisioner must not be treated as a fully constrained tenant account: MariaDB global user-management privileges can affect other application logins. Restrict who can invoke provisioning, isolate privileged execution and consider a dedicated MariaDB instance/host or constrained privileged broker for stronger boundaries.

**Important grant review:** Database-name patterns used in MariaDB grants must be tested against the actual server version and SQL wildcard semantics. A bare `sch_%` uses `_` as a SQL LIKE wildcard, so it is **not proof of a literal `sch_` prefix restriction**. Do not treat tests that merely confirm access to one desired database as sufficient; explicitly test prohibited near-matches. Verify the least-privilege grant syntax and behavior on the targeted MariaDB release before deploying any changed grants.

## Target architecture

```text
Authorized Control Center user
          |
          v
Business approval + billing eligibility
          |
          v
Durable provisioning job (idempotent, audited)
          |
          v
Dedicated provisioning worker / broker
          |                         |
          v                         v
Scoped credential provider    Infrastructure configuration
          |                         |
          +-------------+-----------+
                        v
               Controlled bench actions
           new-site / install / migrate /
           restore / domain / license
                        |
                        v
              Tenant health verification
                        |
                        v
                  Active school
```

The public-facing Frappe web processes should **not** receive MariaDB provisioner or signing-key credentials by default. Only designated privileged workers/brokers should receive them; enforce authorization at the job boundary and isolate the worker at the OS/container level. Separate command execution from HTTP handlers.

## 1. Secrets contract

Support explicit providers:

| Environment | Recommended provider |
|---|---|
| Ubuntu/WSL development | Protected env file injected by launcher/service |
| systemd production | `EnvironmentFile=` as a transitional option; prefer systemd credentials or dedicated secret manager |
| Docker Compose | Read-only mounted secret files |
| Kubernetes | External secrets integration with scoped service accounts |

Do not infer environment from OS alone. Use explicit `STEMIC_ENV`, secrets provider and worker configuration. Supported providers must be allowlisted; avoid arbitrary secret paths or names supplied through requests. Do not introduce multiple conflicting sources with implicit precedence in production.

**Required behavior:**

- Fail closed when provisioner credentials are missing or invalid; no implicit MariaDB root fallback.
- Reject root for routine provisioning; make exceptional break-glass recovery a separately audited, manually approved operation.
- Secret values never appear in URLs, exceptions, application/API responses, logs, traces, job payloads, database records or Git.
- Resolve secrets only in privileged processes; do not place secrets in command-line flags visible to process inspection when a safer channel is available.
- Keep credentials out of Frappe `site_config.json`, generated backups and diagnostic bundles; verify this with tests.
- Restrict secret-file ownership and permissions and use least-privilege access for service accounts.
- Define a rotation procedure: provision new credential, update provider, restart/reload required workers, verify jobs, revoke old credential, audit outcome.
- Show only **source**, **configured/valid status**, **last check**, and **safe error identifiers** in Setup Check.

> The current `STEMIC_DB_ROOT_*` variable names can be retained during migration for compatibility even when the username is `stemic_provisioner`. Plan a documented deprecation path rather than introducing a breaking rename.

## 2. Provisioning workflow

Suggested states:

`PENDING → APPROVED → QUEUED → VALIDATING → CREATING_SITE → INSTALLING → CONFIGURING → LICENSING → VERIFYING → ACTIVE`

Failure and compensation states: `RETRY_WAIT`, `FAILED`, `CLEANUP_REQUIRED`, `CANCELLED`.

- Create jobs only after authorization, approval and billing eligibility checks.
- Use stable idempotency keys per tenant and operation; enforce uniqueness in durable storage.
- Validate tenant slugs, database names, domains and filesystem paths before any shell/SQL operation.
- Avoid shell interpolation; invoke subprocesses with argument arrays, minimal environment, bounded timeouts and redacted logs.
- Restrict concurrency per server/bench and database host; account for storage and resource capacity.
- Persist checkpoint/state before and after every external side effect.
- Retry only transient failures with backoff and a hard retry limit; do not blindly rerun non-idempotent `new-site`, restore or deletion commands.
- Detect partial sites/databases/users and reconcile rather than overwriting or deleting unrelated resources.
- Require a confirmation/authorization boundary for destructive cleanup and restores.
- Audit actor, tenant, requested operation, worker, outcome and timestamps without storing secrets.

## 3. Database permissions and isolation

Retain `stemic_provisioner` only after **version-specific grant verification**. Review `CREATE USER`, `DROP USER`, `RELOAD`, `GRANT OPTION` and any access to `mysql.user`, including whether each is actually needed for supported Bench operations.

Run positive and negative tests for:

- Intended school and restore-check database creation, grant, restore and deletion.
- Denied read/write/drop access to `bookkeeping` and non-school databases.
- Denied creation/grant/deletion on names that almost match the intended prefix.
- Account/login operations outside a school, especially global user-management side effects.

For stronger isolation, separate tenant MariaDB infrastructure from unrelated applications, and ideally implement provisioning through a narrowly scoped broker that validates every operation. **Do not describe a global `CREATE USER` account as fully isolated.**

## 4. Infrastructure configuration

Keep non-secret operational settings in typed, validated configuration:

- Database hosts and provisioning capacity.
- Worker pools and bench installation locations.
- Allowed domain suffixes and custom-domain verification.
- Default apps/modules to install.
- Backup storage, restore verification and retention.
- Concurrency caps, deadlines, retry policy and resource quotas.

Do not allow an ordinary Control Center user to choose arbitrary server paths, executable commands, secret providers or database hosts.

## 5. Control Center operations UI

Expose enterprise-quality, role-restricted pages:

| Area | Minimum capabilities |
|---|---|
| Infrastructure | Host status, resource utilization, capacity warnings |
| Database servers | Health, capacity and connection checks, no raw passwords |
| Provisioning | Queue, active jobs, checkpoints, attempts, failures, retry/repair controls |
| Domains | Validation, DNS/tunnel routing status, TLS status |
| Secrets status | Configured source, validator result, rotation due (never values) |
| Security & audit | Privileged actions, approval history, denied operations |
| Backup & recovery | Job results, restore verification, retention alerts |

All privileged actions require server-side authorization and audit entries; UI visibility alone is insufficient access control.

## 6. Deployment and startup

**Local Ubuntu/WSL**: use a repeatable launcher or managed process that loads the secret source for privileged workers; avoid manual per-terminal sourcing.

**systemd**: explicitly attach credentials to the provisioning worker unit, not all bench processes. Example (illustrative, adapt paths/service account to deployment):

```ini
[Service]
User=hp
EnvironmentFile=/etc/stemic/secrets.env
```

This is a transitional implementation: environment variables can be visible to processes with appropriate OS privileges. Prefer the service manager's credential-file mechanism where supported.

**Docker**: mount provisioner credentials as read-only secret files only in the privileged worker container; do not bake them into images or Compose environment literals.

**Production**: use service management/restart policies, health probes, separate authorization for infrastructure changes and a documented emergency recovery plan.

## 7. Testing and acceptance

Preserve existing suites, including the **eight-step onboarding integration flow** and backup restore verification. Add automated tests for:

1. Absent/wrong secret, prohibited root fallback and validation failures.
2. Secret redaction across logs, API, status pages and error tracebacks.
3. Worker restart/reboot credential loading and privilege separation.
4. Authorization enforcement for provisioning, retry, rollback and deletion.
5. Duplicate approvals, concurrent jobs, idempotency and partial-state recovery.
6. Database grant positive/negative cases, near-match prefixes and unrelated-login impact.
7. Backup/restore isolation and removal of secrets from new backup artifacts.
8. Rotation, restart, revocation and continuity during credential changes.
9. Domain verification, TLS routing and multi-server configuration.

**Acceptance:** No manual credential sourcing; no implicit root fallback; reliable repeatable onboarding; no secret disclosure; independent worker privileges; auditable operations; safe recovery; successful onboarding/restore regression tests; documented upgrade/rollback.

## 8. Delivery plan

1. Inventory current secrets and dependent workloads; document the migration and rollback.
2. Add explicit secrets-provider contract and failure modes; tests first.
3. Split privileged provisioning worker from public-facing processes.
4. Implement durable state machine, idempotency, retry/compensation controls.
5. Revalidate MariaDB grants and tenant isolation with negative tests.
6. Build infrastructure, job and security-status pages.
7. Add systemd/Docker deployment examples and operational runbooks.
8. Run all existing tests plus eight-step onboarding and restore checks.
9. Ship via focused pull requests; do not auto-modify production secrets.

### Non-goals for this documentation-only change

This document does **not** change live credentials, SQL grants, DNS, CI, worker configuration, site databases or deployment state. Implementation must be delivered separately and measured against the acceptance tests above.

## References

- Existing repository implementation and README, including PR #36.
- Frappe Bench site provisioning operations and the installed Frappe/MariaDB versions must be verified in the target environment.
