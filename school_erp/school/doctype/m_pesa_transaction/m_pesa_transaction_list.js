frappe.listview_settings["M-Pesa Transaction"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = { Posted: "green", Unmatched: "orange", "Needs Review": "orange", Failed: "red", Received: "blue", Ignored: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(list) {
		frappe.realtime.on("paybill_unmatched", () => list.refresh());
	},
};
