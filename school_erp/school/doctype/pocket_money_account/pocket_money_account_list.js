frappe.listview_settings["Pocket Money Account"] = {
	onload(listview) {
		if (!frappe.user.has_role(["Bursar", "School Admin", "Accounts Manager", "System Manager"])) return;
		listview.page.add_inner_button(__("Check Ledger"), () => school_erp.ledger_check());
		listview.page.add_inner_button(__("Post Today's Shop Sales"), () =>
			frappe.xcall("school_erp.api.ledger.post_purchases_now").then((r) =>
				frappe.show_alert({ message: __("{0} journal entr(ies) posted", [r.entries.length]), indicator: "green" })));
	},
};
