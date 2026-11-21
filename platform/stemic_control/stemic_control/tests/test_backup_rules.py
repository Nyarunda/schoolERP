"""Pure backup rules (no Frappe): python -m pytest platform/stemic_control/stemic_control/tests/test_backup_rules.py"""

import datetime as dt

from stemic_control.backup_rules import (group_server_files, object_key, offsite_expired, parse_backup_output, stale,
										  stamp_time, to_prune, wants_nightly)

OUTPUT = """Backup Summary for school.example at 2026-11-21 01:00:04.123
Config  : ./school.example/private/backups/20261121_010000-school_example-site_config_backup.json 94.0B
Database: ./school.example/private/backups/20261121_010000-school_example-database.sql.gz         1.5MiB
Public  : ./school.example/private/backups/20261121_010000-school_example-files.tar              512.0KiB
Private : ./school.example/private/backups/20261121_010000-school_example-private-files.tar      1.0MiB
Backup for Site school.example has been successfully completed with files"""


def test_parse_backup_output():
	r = parse_backup_output(OUTPUT, "/home/frappe/frappe-bench/sites")
	assert r["database_file"] == "/home/frappe/frappe-bench/sites/school.example/private/backups/20261121_010000-school_example-database.sql.gz"
	assert r["public_file"].endswith("-files.tar") and r["private_file"].endswith("-private-files.tar")
	assert r["config_file"].endswith("site_config_backup.json")
	assert r["size_mb"] == 3.0
	assert r["taken_on"] == dt.datetime(2026, 11, 21, 1, 0, 0)
	assert parse_backup_output("something went wrong") == {}
	db_only = parse_backup_output("Database: ./s/private/backups/20261121_010000-s-database.sql.gz 2.0MiB")
	assert "public_file" not in db_only and db_only["size_mb"] == 2.0


def test_group_server_files():
	names = ["20261121_010000-s-database.sql.gz", "20261121_010000-s-files.tar", "20261121_010000-s-private-files.tar",
			 "20261121_010000-s-site_config_backup.json", "20261120_010000-s-files.tar", "notes.txt"]
	assert group_server_files(names) == {"20261121_010000": {
		"database_file": names[0], "public_file": names[1], "private_file": names[2], "config_file": names[3]}}
	assert stamp_time(names[0]) == dt.datetime(2026, 11, 21, 1, 0)


def test_to_prune():
	start = dt.datetime(2026, 11, 21, 1, 0)
	backups = [{"name": f"b{i}", "taken_on": start - dt.timedelta(days=i), "pinned": i == 25} for i in range(60)]
	backups.append({"name": "extra-today", "taken_on": start - dt.timedelta(minutes=30), "pinned": False})
	gone = to_prune(backups, 7, 4, 6)
	kept = {b["name"] for b in backups} - gone
	assert "b0" in kept                                   # the newest
	assert {f"b{i}" for i in range(7)} <= kept            # 7 daily
	assert "extra-today" in gone                          # same day as b0, older
	assert "b25" in kept                                  # pinned
	assert {"b21", "b52"} <= kept                         # newest of October and of September (monthly)
	assert len(kept) <= 7 + 4 + 6 + 1
	assert to_prune([]) == set()
	assert to_prune([{"name": "only", "taken_on": start, "pinned": False}], 0, 0, 0) == set()  # newest always kept


def test_offsite_and_keys_and_schedule():
	now = dt.datetime(2026, 11, 21, 2)
	assert offsite_expired(now - dt.timedelta(days=91), now, 90)
	assert not offsite_expired(now - dt.timedelta(days=10), now, 90)
	assert not offsite_expired(now - dt.timedelta(days=900), now, 0)        # 0 = forever
	assert not offsite_expired(now - dt.timedelta(days=900), now, 90, True)  # pinned
	assert object_key("stemic/backups/", "school.example", "/x/y/20261121-db.sql.gz") == "stemic/backups/school.example/20261121-db.sql.gz"
	assert object_key("", "s", "f.tar") == "s/f.tar"
	assert stale(None, now) and stale(now - dt.timedelta(hours=27), now) and not stale(now - dt.timedelta(hours=3), now)
	assert wants_nightly(now, 1, None) and not wants_nightly(now, 1, now.date()) and not wants_nightly(now, 3, None)
