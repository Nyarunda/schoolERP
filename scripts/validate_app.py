#!/usr/bin/env python3
"""Static checks that catch most broken-migrate problems without a bench.

- every JSON file parses
- DocType field names are unique, Link/Table targets exist, child tables are istable
- fetch_from points at a real field, title_field exists, submittables have amended_from
- every DocType folder has __init__.py, a controller and a JSON
"""

import glob
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "school_erp")
# DocTypes from Frappe / ERPNext that our Links may point to
EXTERNAL = {
	"Customer", "Company", "Currency", "Account", "Cost Center", "Mode of Payment", "Customer Group",
	"Territory", "Employee", "User", "Item", "Sales Invoice", "Payment Entry", "Role", "Journal Entry",
}

errors = []

for f in glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True):
	try:
		json.load(open(f))
	except Exception as e:
		errors.append(f"{f}: invalid JSON ({e})")

ours = {}
for folder in glob.glob(os.path.join(ROOT, "school", "doctype", "*", "")):
	base = os.path.basename(os.path.dirname(folder))
	if base == "__pycache__":
		continue
	for need in ("__init__.py", f"{base}.py", f"{base}.json"):
		if not os.path.exists(os.path.join(folder, need)):
			errors.append(f"doctype/{base}: missing {need}")
	jf = os.path.join(folder, f"{base}.json")
	if os.path.exists(jf):
		d = json.load(open(jf))
		ours[d["name"]] = d

for name, d in ours.items():
	names = [x["fieldname"] for x in d["fields"]]
	dup = {n for n in names if names.count(n) > 1}
	if dup:
		errors.append(f"{name}: duplicate fields {dup}")
	if d.get("field_order") and d["field_order"] != names:
		errors.append(f"{name}: field_order does not match fields")
	for fld in d["fields"]:
		ft, opt = fld["fieldtype"], fld.get("options")
		if ft in ("Link", "Table", "Table MultiSelect") and opt not in ours and opt not in EXTERNAL:
			errors.append(f"{name}.{fld['fieldname']}: unknown target {opt}")
		if ft in ("Table", "Table MultiSelect") and opt in ours and not ours[opt].get("istable"):
			errors.append(f"{name}.{fld['fieldname']}: {opt} is not a child table")
		if fld.get("fetch_from"):
			link, target = fld["fetch_from"].split(".", 1)
			lf = next((x for x in d["fields"] if x["fieldname"] == link), None)
			if not lf:
				errors.append(f"{name}.{fld['fieldname']}: fetch_from link {link} missing")
			elif lf.get("options") in ours and target not in [x["fieldname"] for x in ours[lf["options"]]["fields"]]:
				errors.append(f"{name}.{fld['fieldname']}: {lf['options']} has no field {target}")
	if d.get("title_field") and d["title_field"] not in names:
		errors.append(f"{name}: title_field {d['title_field']} missing")
	if d.get("is_submittable") and "amended_from" not in names:
		errors.append(f"{name}: submittable without amended_from")

# controller class names must follow Frappe's rule (spaces and hyphens removed, capitals kept)
import re  # noqa: E402

for name, d in ours.items():
	folder = name.lower().replace(" ", "_").replace("-", "_")
	py = os.path.join(ROOT, "school", "doctype", folder, folder + ".py")
	if os.path.exists(py):
		m = re.search(r"^class (\w+)\(", open(py).read(), re.M)
		want = name.replace(" ", "").replace("-", "")
		if not m or m.group(1) != want:
			errors.append(f"{name}: controller class should be {want}")

if errors:
	print("\n".join(errors))
	sys.exit(1)
print(f"validate_app: {len(ours)} DocTypes OK")
