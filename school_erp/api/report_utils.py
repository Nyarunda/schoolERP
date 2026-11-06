"""Small helpers shared by the School reports."""

from frappe import _
from frappe.utils import get_first_day, getdate, nowdate


def col(fieldname, label, fieldtype="Data", width=120, options=None):
	c = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
	if options:
		c["options"] = options
	return c


def date_range(filters):
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or get_first_day(to_date))
	return from_date, to_date


# ----------------------------------------------------------------------------- charts and summary cards
# One validated categorical order (light mode steps; Frappe Charts has no per-theme colours). Slot 1 for a single
# series; slots 1-2 for a pair. Never cycled: a report with more series folds them, or shows a table.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]


def bar_chart(labels, datasets, money=False, horizontal=False, height=280, stacked=False):
	"""datasets: [(name, values)] or a single list of values. Returns a Frappe report chart."""
	if datasets and not isinstance(datasets[0], (list, tuple)):
		datasets = [(_("Value"), datasets)]
	chart = {
		"data": {"labels": [str(x) if x is not None else _("Not set") for x in labels],
				 "datasets": [{"name": n, "values": [v or 0 for v in vals]} for n, vals in datasets]},
		"type": "bar", "height": height, "colors": SERIES[:max(1, len(datasets))],
		"barOptions": {"spaceRatio": 0.4, "stacked": 1 if stacked else 0},
		"axisOptions": {"xAxisMode": "tick", "shortenYAxisNumbers": 1},
	}
	if money:
		chart["fieldtype"] = "Currency"
	return chart


def line_chart(labels, datasets, money=False, height=280, percent=False):
	chart = bar_chart(labels, datasets, money=money, height=height)
	chart.update({"type": "line", "lineOptions": {"regionFill": 1, "hideDots": 0}, "axisOptions": {"xIsSeries": 1, "shortenYAxisNumbers": 1}})
	if percent:
		chart["fieldtype"] = "Percent"
	return chart


def top(rows, key, value, n=12, other_label=None):
	"""Biggest n categories by value; the rest folded into 'Other' so a chart never runs out of room."""
	rows = sorted(rows, key=lambda r: -(r.get(value) or 0))
	head, tail = rows[:n], rows[n:]
	labels, values = [r.get(key) for r in head], [r.get(value) or 0 for r in head]
	if tail:
		labels.append(other_label or _("Other ({0})").format(len(tail)))
		values.append(sum(r.get(value) or 0 for r in tail))
	return labels, values


def card(label, value, datatype="Int", indicator=None, currency=None):
	c = {"label": _(label), "value": value, "datatype": datatype}
	if indicator:
		c["indicator"] = indicator
	if currency:
		c["currency"] = currency
	return c
