"""Settings DocTypes (singles) read with their defaults.

A single that has never been saved stores nothing, and Frappe turns unset Check/Int fields into 0 when it loads one, so
a fresh install would read every default as blank. These helpers fill in the JSON default of any field the school has
never stored, without writing to the database.
"""

import frappe
from frappe.utils import cint, flt


def get_settings(doctype: str) -> frappe._dict:
	doc = frappe.get_cached_doc(doctype)
	out = frappe._dict(doc.as_dict())
	stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype = %s", doctype))
	for df in doc.meta.fields:
		if df.default is None or df.default == "" or df.fieldname in stored:
			continue
		if df.fieldtype in ("Check", "Int"):
			out[df.fieldname] = cint(df.default)
		elif df.fieldtype in ("Float", "Currency", "Percent"):
			out[df.fieldname] = flt(df.default)
		else:
			out[df.fieldname] = df.default
	return out


def get_setting(doctype: str, fieldname: str):
	return get_settings(doctype).get(fieldname)
