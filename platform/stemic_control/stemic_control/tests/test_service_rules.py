"""Pure service-watch rules: python -m pytest platform/stemic_control/stemic_control/tests/test_service_rules.py"""

import datetime as dt

from stemic_control.service_rules import GB, batch_timeout, cert_days_left, commit_from_git, disk_problem, down_change


def test_disk_problem():
	assert disk_problem(1000 * GB, 50 * GB, 10)
	assert disk_problem(1000 * GB, 200 * GB, 10) is None
	assert disk_problem(40 * GB, 4 * GB, 5)  # under 5 GB, whatever the percentage
	assert disk_problem(0, 0) is None
	assert "GB free" in disk_problem(100 * GB, 3 * GB)


def test_cert_days_left():
	now = dt.datetime(2026, 11, 21, 12)
	assert cert_days_left("Dec  5 12:00:00 2026 GMT", now) == 14
	assert cert_days_left("Nov 20 12:00:00 2026 GMT", now) == -1


def test_down_change():
	assert down_change(0, False) == (1, None)
	assert down_change(1, False) == (2, "down")
	assert down_change(2, False) == (3, None)  # still down: no repeat
	assert down_change(3, True) == (0, "up")
	assert down_change(1, True) == (0, None)  # one blip never alerted
	assert down_change(0, True) == (0, None)


def test_commit_from_git(tmp_path):
	app = tmp_path / "school_erp"
	(app / ".git" / "refs" / "heads").mkdir(parents=True)
	(app / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
	(app / ".git" / "refs" / "heads" / "main").write_text("abc123\n")
	assert commit_from_git(str(app)) == "abc123"
	(app / ".git" / "refs" / "heads" / "main").unlink()
	(app / ".git" / "packed-refs").write_text("# pack-refs\ndef456 refs/heads/main\n")
	assert commit_from_git(str(app)) == "def456"
	(app / ".git" / "HEAD").write_text("0123abcd\n")
	assert commit_from_git(str(app)) == "0123abcd"
	assert commit_from_git(str(tmp_path / "missing")) is None


def test_batch_timeout():
	assert batch_timeout(3, 3600) == 3 * 3600 + 300
	assert batch_timeout(100, 3600) == 12 * 3600
