#!/usr/bin/env python3
"""Vendor tool for issuing School ERP license keys. Keep this and your private key OFF school servers.

    python tools/license_tool.py keygen
        -> prints a private key (keep secret) and a public key (paste into school_erp/licensing/public_key.py)

    python tools/license_tool.py issue --private-key-file vendor.key \
        --school "Greenhill Academy" --site greenhill.example.com \
        --modules fees,transport,lunch,activities,messaging,timetable \
        --expires 2027-12-31 --max-students 600
        -> prints the license key to paste into School Settings > License

    python tools/license_tool.py inspect --public-key <pub> <key>
"""

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from school_erp.logic import license as lic  # noqa: E402


def main():
	p = argparse.ArgumentParser()
	sub = p.add_subparsers(dest="cmd", required=True)
	sub.add_parser("keygen")

	i = sub.add_parser("issue")
	i.add_argument("--private-key-file", required=True)
	i.add_argument("--school", required=True)
	i.add_argument("--site", help="Frappe site name; key only works there")
	i.add_argument("--modules", required=True, help="comma list: " + ",".join(lic.MODULES))
	i.add_argument("--expires", help="YYYY-MM-DD; omit for no expiry")
	i.add_argument("--max-students", type=int, default=0)

	s = sub.add_parser("inspect")
	s.add_argument("--public-key", required=True)
	s.add_argument("key")

	a = p.parse_args()
	if a.cmd == "keygen":
		priv, pub = lic.generate_keypair()
		print("PRIVATE KEY (save to vendor.key, never share):\n" + priv)
		print("\nPUBLIC KEY (paste into school_erp/licensing/public_key.py):\n" + pub)
	elif a.cmd == "issue":
		priv = open(a.private_key_file).read().strip()
		payload = {
			"school": a.school,
			"modules": [m.strip() for m in a.modules.split(",") if m.strip()],
			"issued": date.today().isoformat(),
			"max_students": a.max_students,
		}
		if a.site:
			payload["site"] = a.site
		if a.expires:
			payload["expires"] = a.expires
		print(lic.issue(payload, priv))
	elif a.cmd == "inspect":
		print(json.dumps(lic.verify(a.key, a.public_key), indent=2))


if __name__ == "__main__":
	main()
