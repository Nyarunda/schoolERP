"""Backup rules with no Frappe: reading `bench backup` output, which backups to keep, off-server names.

    Config  : ./school.example/private/backups/20261121_010000-school_example-site_config_backup.json 94.0B
    Database: ./school.example/private/backups/20261121_010000-school_example-database.sql.gz        1.2MiB
    Public  : ./school.example/private/backups/20261121_010000-school_example-files.tar              10.0KiB
    Private : ./school.example/private/backups/20261121_010000-school_example-private-files.tar      10.0KiB
"""

import datetime
import os
import re

PARTS = {"Database": "database_file", "Config": "config_file", "Public": "public_file", "Private": "private_file"}
LINE = re.compile(r"^\s*(Database|Config|Public|Private)\s*:\s*(\S+)(?:\s+([\d.]+)\s*([KMGT]?i?B))?\s*$")
UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4,
		 "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}
STAMP = re.compile(r"(\d{8}_\d{6})-")
SERVER_FILE = re.compile(r"^(\d{8}_\d{6})-.+?-(database\.sql\.gz|site_config_backup\.json|private-files\.tar|files\.tar)$")
SUFFIX_PART = {"database.sql.gz": "database_file", "site_config_backup.json": "config_file", "files.tar": "public_file",
			   "private-files.tar": "private_file"}


def parse_backup_output(output: str, sites_dir: str = "") -> dict:
	"""{database_file, config_file, public_file, private_file: absolute path, size_mb, taken_on} from the command's
	output. Paths are relative to the bench's sites folder."""
	out, total = {}, 0.0
	for line in (output or "").splitlines():
		m = LINE.match(line)
		if not m:
			continue
		part, path, size, unit = m.groups()
		out[PARTS[part]] = os.path.normpath(os.path.join(sites_dir, path)) if sites_dir and not os.path.isabs(path) else path
		if size:
			total += float(size) * UNITS.get(unit, 1)
	if "database_file" in out:
		out["size_mb"] = round(total / 1048576, 2)
		out["taken_on"] = stamp_time(os.path.basename(out["database_file"]))
	return out


def stamp_time(filename: str):
	"""20261121_010000-... -> datetime (the server's local time, as Frappe names its backups)."""
	m = STAMP.search(filename or "")
	return datetime.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S") if m else None


def group_server_files(filenames) -> dict:
	"""Backup files found in a site's backups folder -> {stamp: {part: filename}} (only sets with a database)."""
	sets: dict = {}
	for name in filenames:
		m = SERVER_FILE.match(name)
		if m:
			sets.setdefault(m.group(1), {})[SUFFIX_PART[m.group(2)]] = name
	return {k: v for k, v in sets.items() if "database_file" in v}


def to_prune(backups, keep_daily=7, keep_weekly=4, keep_monthly=6) -> set:
	"""backups: [{name, taken_on (datetime), pinned}] of one school, on the server. Keep the newest backup of each of
	the last `keep_daily` days that have one, of each of the last `keep_weekly` ISO weeks, of each of the last
	`keep_monthly` months, every pinned one, and always the newest. Returns the names to remove."""
	rows = sorted((b for b in backups if b.get("taken_on")), key=lambda b: b["taken_on"], reverse=True)
	if not rows:
		return set()
	keep = {rows[0]["name"]} | {b["name"] for b in rows if b.get("pinned")}
	for size, bucket in ((keep_daily, lambda t: t.date()), (keep_weekly, lambda t: t.isocalendar()[:2]),
						 (keep_monthly, lambda t: (t.year, t.month))):
		seen = []
		for b in rows:
			k = bucket(b["taken_on"])
			if k not in seen:
				if len(seen) >= int(size or 0):
					break
				seen.append(k)
				keep.add(b["name"])
	return {b["name"] for b in rows} - keep


def offsite_expired(taken_on, now, keep_days, pinned=False) -> bool:
	"""Off-server copies are kept `keep_days` days (0 = forever); pinned ones always."""
	if pinned or not keep_days or not taken_on:
		return False
	return (now - taken_on).days >= int(keep_days)


def object_key(prefix: str, site: str, path: str) -> str:
	"""Where a file goes in the bucket: <prefix>/<site>/<file name>."""
	parts = [p.strip("/") for p in (prefix or "", site, os.path.basename(path)) if p and p.strip("/")]
	return "/".join(parts)


def stale(last_success, now, hours=26) -> bool:
	"""No successful backup in the last `hours` hours."""
	return last_success is None or (now - last_success).total_seconds() > hours * 3600


def wants_nightly(now, hour, last_scheduled_day) -> bool:
	"""Hourly check: is it the chosen hour (or later, the same day) and not done yet today?"""
	return now.hour >= int(hour or 0) and last_scheduled_day != now.date()
