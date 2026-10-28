"""Platform settings: the Stemic Settings screen, with site_config.json taking precedence.

A value set in the admin site's site_config.json wins (deployment overrides, and how tests configure things); otherwise
the Stemic Settings value applies; otherwise the default. Secrets (database root password, license signing key) are
read from site_config only and never stored in, or shown by, the database.
"""

import frappe

# key -> (Stemic Settings field, default)
SETTINGS = {
    "stemic_platform_domain": ("platform_domain", "stemicschools.com"),
    "stemic_site_domain": ("site_domain", "localhost"),
    "stemic_site_apps": ("site_apps", "erpnext\nschool_erp"),
    "stemic_bench_path": ("bench_path", None),
    "stemic_local_provisioner": ("local_provisioner", 0),
    "stemic_dns_over_https": ("dns_over_https", "https://cloudflare-dns.com/dns-query"),
}


def _settings():
    if not frappe.db.exists("DocType", "Stemic Settings"):
        return None
    return frappe.get_cached_doc("Stemic Settings")


def get(key):
    if frappe.conf.get(key) not in (None, ""):
        return frappe.conf.get(key)
    field, default = SETTINGS[key]
    settings = _settings()
    value = settings.get(field) if settings else None
    return value if value not in (None, "") else default


def source(key) -> str:
    """Where a setting currently comes from: 'site_config', 'settings' or 'default'."""
    if frappe.conf.get(key) not in (None, ""):
        return "site_config"
    settings = _settings()
    return "settings" if settings and settings.get(SETTINGS[key][0]) not in (None, "") else "default"


# Secrets: the process environment first (in production, loaded by supervisor / systemd from a file only the bench's
# user can read, e.g. /etc/stemic/secrets.env), then site_config.json (development). Never Stemic Settings.
SECRETS = {
    "stemic_db_root_username": "STEMIC_DB_ROOT_USERNAME",  # the MariaDB account that creates school databases
    "stemic_db_root_password": "STEMIC_DB_ROOT_PASSWORD",
    "stemic_license_private_key_file": "STEMIC_LICENSE_PRIVATE_KEY_FILE",
}


def secret(key):
    """A secret's value and where it came from: (value, 'environment' | 'site_config' | None)."""
    import os

    value = os.environ.get(SECRETS[key])
    if value:
        return value, "environment"
    value = frappe.conf.get(key)
    if key == "stemic_db_root_password" and not value:
        value = frappe.conf.get("root_password")  # bench's own name for it
    return (value, "site_config") if value else (None, None)


def site_apps() -> list[str]:
    apps = get("stemic_site_apps")
    if isinstance(apps, str):
        apps = [a.strip() for a in apps.replace(",", "\n").splitlines()]
    return [a for a in apps if a]
