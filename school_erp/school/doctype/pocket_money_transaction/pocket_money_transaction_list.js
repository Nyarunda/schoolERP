// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Pocket Money Transaction"] = {
	add_fields: ["transaction_type", "docstatus"],
	get_indicator(doc) {
		if (doc.docstatus === 2) return [__("Cancelled"), "red", "docstatus,=,2"];
		if (doc.docstatus === 0) return [__("Draft"), "orange", "docstatus,=,0"];
		const credit = ["Deposit", "Refund", "Adjustment In"].includes(doc.transaction_type);
		return [__(doc.transaction_type), credit ? "green" : "blue", `transaction_type,=,${doc.transaction_type}`];
	},
};
