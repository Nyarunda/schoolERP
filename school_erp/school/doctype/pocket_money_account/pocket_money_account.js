// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Pocket Money Account", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.dashboard.add_indicator(__("Balance {0}", [format_currency(frm.doc.balance)]), frm.doc.balance > 0 ? "green" : "orange");
		if (frm.doc.is_frozen) frm.dashboard.add_indicator(__("Frozen"), "red");
		const quick = (type, extra = []) => frappe.prompt([
			{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1 },
			...extra,
			{ fieldname: "description", label: __("What for"), fieldtype: "Data" },
		], (v) => frappe.call({ method: "school_erp.api.pocket_money.quick_transaction", args: { student: frm.doc.student, transaction_type: type, ...v }, freeze: true })
			.then(() => frm.reload_doc()), __(type), __("Save"));
		frm.add_custom_button(__("Purchase"), () => quick("Purchase"), __("Record"));
		frm.add_custom_button(__("Deposit"), () => quick("Deposit", [
			{ fieldname: "mode", label: __("Paid by"), fieldtype: "Select", options: "Cash\nM-Pesa\nBank\nOther", default: "Cash", reqd: 1 },
			{ fieldname: "reference", label: __("M-Pesa / bank reference"), fieldtype: "Data", depends_on: "eval:doc.mode!='Cash'" },
		]), __("Record"));
		frm.add_custom_button(__("Withdrawal"), () => quick("Withdrawal", [
			{ fieldname: "mode", label: __("Paid out by"), fieldtype: "Select", options: "Cash\nM-Pesa\nBank\nOther", default: "Cash", reqd: 1 },
		]), __("Record"));
		frm.add_custom_button(__("Statement"), () => frappe.set_route("query-report", "Pocket Money Statement", { student: frm.doc.student }));
	},
});
