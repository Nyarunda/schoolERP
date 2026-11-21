"""Service-watch rules with no Frappe: disk space, certificate expiry, up/down changes, the app's code version."""

import datetime
import os

GB = 1024 ** 3
MIN_FREE = 5 * GB
DOWN_AFTER = 2  # checks in a row (15 minutes apart) before a school counts as down


def disk_problem(total, free, percent=10) -> str | None:
	"""Why the free disk space is a problem, or None."""
	if not total:
		return None
	pct = free * 100.0 / total
	if pct < float(percent or 0) or free < MIN_FREE:
		return f"Only {free / GB:.1f} GB free ({pct:.0f}%) of {total / GB:.0f} GB"
	return None


def cert_days_left(not_after: str, now: datetime.datetime) -> int:
	"""'Feb  5 12:00:00 2027 GMT' (ssl.getpeercert()['notAfter']) -> whole days from now (negative once expired)."""
	expires = datetime.datetime.strptime(" ".join(not_after.split()), "%b %d %H:%M:%S %Y %Z")
	return int((expires - now).total_seconds() // 86400)


def down_change(previous_failures: int, ok: bool) -> tuple[int, str | None]:
	"""(new failure count, 'down' | 'up' | None): 'down' on the DOWN_AFTER-th failure in a row, 'up' on the first
	success after the school was counted down."""
	if ok:
		return 0, ("up" if previous_failures >= DOWN_AFTER else None)
	failures = previous_failures + 1
	return failures, ("down" if failures == DOWN_AFTER else None)


def commit_from_git(app_dir: str) -> str | None:
	"""The commit an app's checkout is on, read from .git without running git."""
	git = os.path.join(app_dir, ".git")
	if os.path.isfile(git):  # a worktree / submodule: "gitdir: <path>"
		with open(git) as f:
			line = f.read().strip()
		if line.startswith("gitdir:"):
			git = os.path.normpath(os.path.join(app_dir, line.split(":", 1)[1].strip()))
	try:
		with open(os.path.join(git, "HEAD")) as f:
			head = f.read().strip()
	except OSError:
		return None
	if not head.startswith("ref:"):
		return head or None
	ref = head.split(":", 1)[1].strip()
	try:
		with open(os.path.join(git, ref)) as f:
			return f.read().strip() or None
	except OSError:
		pass
	try:
		with open(os.path.join(git, "packed-refs")) as f:
			for line in f:
				parts = line.strip().split()
				if len(parts) == 2 and parts[1] == ref:
					return parts[0]
	except OSError:
		pass
	return None


def batch_timeout(count, per_site, cap=12 * 3600) -> int:
	return int(min(max(count, 1) * per_site + 300, cap))
