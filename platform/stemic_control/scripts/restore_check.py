"""Does a school's backup actually restore? Back it up, restore it into a throwaway site, compare, drop the copy.

    1. count the rows of every table in the school's database
    2. bench --site <school> backup --with-files            (the same backup Open Site > Back up takes)
    3. bench --site restorecheck-<run>.localhost restore <that backup> --with-public-files --with-private-files
       (with the school's encryption key: without it, every stored password and secret in the copy is unreadable)
    4. compare every table's row count, check the copy answers with its apps and holds the same number of files
    5. drop the copy

The school's own site is only read and backed up, never changed. Log tables (sessions, error and access logs...) may
change while this runs: differences there are reported, not failed.

    cd frappe-bench/sites
    ../env/bin/python ../apps/stemic_control/scripts/restore_check.py admin.localhost school.localhost
    ../env/bin/python ../apps/stemic_control/scripts/restore_check.py admin.localhost school.localhost --keep

Run with the admin site (for the database account, as the provisioner uses it, and the bench path) and the school site to check.
Exit status: 0 the backup restored and matches; 1 it did not.
"""

import json
import os
import re
import secrets
import sys
import time

ADMIN, SCHOOL = (sys.argv[1:3] + ["admin.localhost", ""])[:2]
KEEP = "--keep" in sys.argv[3:]
# tables that legitimately change while a check runs (or that a restore rewrites), so a difference is not a failure
VOLATILE = re.compile(r"(Log|Sessions|Session|Notification|Route History|Communication|Version|Error|Scheduled Job"
                      r"|Deleted Document|__global_search|__Auth|Prepared Report|Activity|Comment)", re.I)


def counts(conf):
    """Row count of every table, read with the site's own database login."""
    import MySQLdb

    conn = MySQLdb.connect(host=conf.get("db_host") or "127.0.0.1", port=int(conf.get("db_port") or 3306),
                           user=conf.get("db_user") or conf["db_name"], passwd=conf.get("db_password") or "",
                           db=conf["db_name"], connect_timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE'",
                    (conf["db_name"],))
        out = {}
        for (table,) in cur.fetchall():
            cur.execute(f"SELECT COUNT(*) FROM `{table}`")
            out[table] = cur.fetchone()[0]
        return out
    finally:
        conn.close()


def files_in(folder):
    return sum(len(names) for _r, _d, names in os.walk(folder)) if os.path.isdir(folder) else 0


def main():
    import frappe

    frappe.init(ADMIN, sites_path=".")
    frappe.connect()
    from stemic_control import provisioner, site_runtime

    if not SCHOOL or not os.path.isdir(site_runtime._site_dir(SCHOOL)):
        sys.exit(f"usage: restore_check.py <admin site> <school site on this bench> [--keep]  ({SCHOOL!r} not found)")
    root = provisioner._root_password()
    conf = site_runtime._config(SCHOOL)
    key = conf.get("encryption_key")
    scratch = f"restorecheck-{frappe.generate_hash(length=6).lower()}.localhost"
    password = secrets.token_urlsafe(14)
    hide = tuple(filter(None, (root, key, password, conf.get("db_password"))))
    cli = lambda *args, timeout=1800: provisioner._frappe_cli(*args, timeout=timeout, secrets_=hide)  # noqa: E731
    started, failures, notes = time.time(), [], []
    print(f"checking that {SCHOOL}'s backup restores, into {scratch}", flush=True)
    try:
        before = counts(conf)
        school_files = {kind: files_in(os.path.join(site_runtime._site_dir(SCHOOL), kind, "files")) for kind in ("public", "private")}
        print(f"  {SCHOOL}: {len(before)} tables, {sum(before.values()):,} rows, "
              f"{school_files['public']} public and {school_files['private']} private files", flush=True)

        output = cli("--site", SCHOOL, "backup", "--with-files")
        found = dict(re.findall(r"^\s*(Database|Public|Private)\s*:\s*(\S+)", output, re.M))
        if "Database" not in found:
            raise RuntimeError("the backup did not report a database file:\n" + output[-800:])
        sizes = ", ".join(f"{k.lower()} {os.path.getsize(v) / 1048576:.1f} MB" for k, v in found.items() if os.path.exists(v))
        print(f"  backup taken: {sizes}", flush=True)

        # restore needs a site to restore into: a bare one (Frappe only), which the backup then replaces
        t = time.time()
        new = ["new-site", scratch, *provisioner._root_args(), "--admin-password", password,
               "--db-name", "restorecheck_" + scratch.split("-")[1].split(".")[0]]
        scope = frappe.conf.get("stemic_mariadb_user_host_login_scope")
        if scope:
            new += ["--mariadb-user-host-login-scope", scope]
        cli(*new, timeout=1800)
        args = ["--site", scratch, "restore", found["Database"], *provisioner._root_args(), "--admin-password", password,
                "--force"]
        if found.get("Public"):
            args += ["--with-public-files", found["Public"]]
        if found.get("Private"):
            args += ["--with-private-files", found["Private"]]
        t = time.time()
        cli(*args, timeout=3600)
        if key:
            # the copy needs the school's own encryption key (not part of the backup) to read its stored passwords
            cli("--site", scratch, "set-config", "encryption_key", key, timeout=120)
        print(f"  restored into {scratch} in {time.time() - t:.0f}s", flush=True)

        provisioner.check_ready(scratch)  # the copy answers on its own database with every app
        after = counts(site_runtime._config(scratch))
        missing = sorted(set(before) - set(after))
        if missing:
            failures.append(f"{len(missing)} table(s) missing from the copy: {', '.join(missing[:8])}")
        differ = {t: (before[t], after.get(t)) for t in before if t in after and before[t] != after[t]}
        real = {t: v for t, v in differ.items() if not VOLATILE.search(t)}
        if real:
            failures.append(f"{len(real)} table(s) with different row counts: "
                            + ", ".join(f"{t} {a}→{b}" for t, (a, b) in list(real.items())[:8]))
        if len(differ) > len(real):
            notes.append(f"{len(differ) - len(real)} log/session table(s) changed while checking (expected)")
        copy_files = {kind: files_in(os.path.join(site_runtime._site_dir(scratch), kind, "files")) for kind in ("public", "private")}
        for kind in ("public", "private"):
            if copy_files[kind] < school_files[kind]:
                failures.append(f"{kind} files: {school_files[kind]} on the school, {copy_files[kind]} in the copy")
        if key and site_runtime._config(scratch).get("encryption_key") != key:
            failures.append("the copy does not have the school's encryption key: its stored passwords would be unreadable")
        print(f"  compared {len(before)} tables and {sum(copy_files.values())} files", flush=True)
    except Exception as e:
        failures.append(f"{type(e).__name__}: {str(e)[:600]}")
    finally:
        if KEEP:
            print(f"  kept {scratch} (drop it with: bench drop-site {scratch} --no-backup --force)")
        elif provisioner._site_dir_exists(scratch):
            try:
                cli("drop-site", scratch, *provisioner._root_args(), "--no-backup", "--force", timeout=600)
                print(f"  dropped {scratch}")
            except Exception as e:
                print(f"  could not drop {scratch}: {e}")
    for note in notes:
        print(f"  note: {note}")
    for failure in failures:
        print(f"  FAIL: {failure}")
    print(f"\n{'FAIL' if failures else 'PASS'}: {SCHOOL}'s backup {'did not restore cleanly' if failures else 'restores'} "
          f"({time.time() - started:.0f}s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
