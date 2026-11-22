frappe.listview_settings["Stemic Expense"] = {
	add_fields: ["docstatus", "repeat_monthly"],
	get_indicator(doc) {
		if (doc.docstatus === 1) return [__("Posted"), "green", "docstatus,=,1"];
		if (doc.docstatus === 2) return [__("Cancelled"), "red", "docstatus,=,2"];
		return [__("To approve"), "orange", "docstatus,=,0"];
	},
	onload(listview) {
		listview.page.add_inner_button(__("This Month"), () => frappe.xcall("stemic_control.expenses.month_summary", {}, "GET").then((r) => {
			const esc = frappe.utils.escape_html, fmt = (v) => format_currency(v, "KES");
			frappe.msgprint({ title: __("Costs in {0}", [r.month]), indicator: r.net >= 0 ? "green" : "red",
				message: `<table class="table table-sm">${r.categories.map((c) => `<tr><td>${esc(c.category)}</td><td class="text-right">${fmt(c.amount)}</td></tr>`).join("")}
					<tr><th>${__("Total costs")}</th><th class="text-right">${fmt(r.costs)}</th></tr></table>
					<p>${__("Collected from schools")}: <b>${fmt(r.collected)}</b>; ${__("agent commission")}: ${fmt(r.commission)};
					${__("left over")}: <b style="color:var(--${r.net >= 0 ? "green" : "red"}-600)">${fmt(r.net)}</b></p>` });
		}));
		listview.page.add_inner_button(__("Costs vs Revenue"), () => frappe.set_route("query-report", "Costs vs Revenue"));
	},
};
