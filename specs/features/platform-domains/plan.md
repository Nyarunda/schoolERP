# Several platform domains: plan

## Design

| Requirement | Standard feature used | Custom code |
|---|---|---|
| Domain list | Child table on the Stemic Settings single | New child DocType **Stemic Platform Domain** (domain, enabled, is_default, notes); validation in `stemic_settings.py` |
| Which domains exist | — | `api.platform_domain()` (default: site_config override → table default → legacy field → built-in) ; `api.offered_domains()` (enabled, default first) ; `api.known_domains()` (all, for existing schools) |
| Health check | — | `domains.platform_domain_health()`: DNS lookup of a random label + https probe (526 = no certificate, 52x = cannot connect, 404/444 = ready) |
| Choose per school | Wizard dialog field | `wizard.check_slug(…, domain)`, `wizard.options()` lists domains, `onboard_school(…, platform_domain)` |
| No TXT for own domains | — | `api.request_domain` and `SaaS Domain.validate` accept `<slug>.<any known domain>` as a verified Stemic Subdomain |
| Remember the domain | New field **SaaS Tenant.platform_domain** | Patch `set_school_platform_domains` fills existing schools |
| Route and go live | `stemic-domains-sync` (existing) | `domains.routes()` includes every serving hostname that is not the site's own name; `hourly()` live-checks Verified non-site subdomains too, and makes the school's chosen-domain address primary when it passes; provisioner tries it once at build time |
| Links follow | — | `domains.public_host()` accepts any Active primary; `_custom()` guard allows non-site subdomains |

## Changes

| File | Change |
|---|---|
| `platform/.../doctype/stemic_platform_domain/` | New child DocType |
| `platform/.../doctype/stemic_settings/stemic_settings.json/.py/.js` | Table field, validation (one default, valid names), **Check Domains** button |
| `platform/.../doctype/saas_tenant/saas_tenant.json` | `platform_domain` (read only) |
| `platform/.../api.py` | domain helpers; `request_domain` accepts any known domain |
| `platform/.../policy.py` | `managed_base(host, bases)`, `reserved_hosts` over several bases |
| `platform/.../doctype/saas_domain/saas_domain.py` | Verified-on-create for `<slug>.<known domain>` |
| `platform/.../wizard.py`, `public/js/stemic_control.bundle.js` | Domain choice |
| `platform/.../provisioner.py` | Address on the school's domain; direct vs routed |
| `platform/.../domains.py` | routes, hourly activation + auto-primary, health, public_host, guard |
| `platform/.../patches/set_school_platform_domains.py` + `patches.txt` | Backfill |
| `platform/.../tests/test_platform_domains.py` | Tests below |

## Data and migration

New child table and one tenant field; patch sets every existing school's `platform_domain` to the current default.

## Risks

- Existing schools must keep their address: the legacy domain is always "known", and the patch pins each school.
- A new domain with no certificate: the school's links stay on its site address until the live check passes.

## Deploy notes

Control Center only (`admin.stemicschools.com`): migrate, `bench build --app stemic_control` (JS changed),
clear-cache, restart. Per new domain, once: add it to Cloudflare, wildcard DNS `*.<domain>` → server (Proxied),
Origin Certificate saved in `/etc/ssl/cloudflare/`.
