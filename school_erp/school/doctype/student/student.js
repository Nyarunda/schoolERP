// Copyright (c) 2026, School ERP and contributors

const school_has = (m) => ((frappe.boot.school_erp || {}).modules || []).includes(m);

frappe.ui.form.on("Student", {
	setup(frm) {
		frm.set_query("stream", () => ({ filters: { is_active: 1 } }));
		frm.set_query("transport_route", () => ({ filters: { is_active: 1 } }));
		frm.set_query("activity", "activities", () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		frm.toggle_display("sb_services", school_has("transport") || school_has("lunch"));
		frm.toggle_display(["transport_route", "pickup_point"], school_has("transport"));
		frm.toggle_display("takes_lunch", school_has("lunch"));
		frm.toggle_display("sb_activities", school_has("activities"));
		frm.toggle_display("sb_fees", school_has("fees"));

		if (frm.is_new() || !school_has("fees")) return;

		frappe.call("school_erp.api.statement.get_balance", { student: frm.doc.name }).then((r) => {
			const bal = r.message || 0;
			const color = bal > 0 ? "red" : "green";
			const label = bal > 0 ? __("Balance due") : bal < 0 ? __("Credit") : __("Fully paid");
			frm.dashboard.add_indicator(`${label}: ${format_currency(Math.abs(bal))}`, color);
		});

		frm.add_custom_button(__("Record Payment"), () => {
			frappe.new_doc("Fee Payment", { student: frm.doc.name, payer_name: frm.doc.primary_guardian, payer_phone: frm.doc.primary_phone });
		}, __("Fees"));

		frm.add_custom_button(__("Fee Statement (PDF)"), () => statement_dialog(frm), __("Fees"));

		frm.add_custom_button(__("Bill for a Term"), () => {
			frappe.prompt(
				[
					{ fieldname: "school_term", label: __("Term"), fieldtype: "Link", options: "School Term", reqd: 1 },
					{ fieldname: "due_date", label: __("Due Date"), fieldtype: "Date" },
				],
				(v) => {
					frappe.call({
						method: "school_erp.api.billing.bill_single_student",
						args: { student: frm.doc.name, ...v },
						freeze: true,
					}).then((r) => {
						frappe.show_alert({ message: __("Invoice {0} created", [r.message]), indicator: "green" });
						frm.reload_doc();
					});
				},
				__("Bill {0}", [frm.doc.student_name]),
			);
		}, __("Fees"));

		frm.add_custom_button(__("Invoices"), () => frappe.set_route("List", "Sales Invoice", { student: frm.doc.name }), __("Fees"));
		frm.add_custom_button(__("Payments"), () => frappe.set_route("List", "Fee Payment", { student: frm.doc.name }), __("Fees"));

		if (school_has("messaging")) {
			frm.add_custom_button(__("Send Statement to Parents"), () => {
				frappe.prompt(
					{ fieldname: "channel", label: __("Send by"), fieldtype: "Select", options: "SMS and Email\nSMS\nEmail", default: "SMS and Email" },
					(v) => frappe.call({
						method: "school_erp.api.messaging.send_statement",
						args: { student: frm.doc.name, channel: v.channel },
						freeze: true,
						freeze_message: __("Sending..."),
					}).then((r) => frappe.msgprint(__("Sent {0} SMS and {1} email(s)", [r.message.sms, r.message.email]))),
					__("Send statement"),
				);
			}, __("Fees"));
		}
	},
});

function statement_dialog(frm) {
	frappe.prompt(
		[
			{ fieldname: "from_date", label: __("From"), fieldtype: "Date", description: __("Blank = start of the school year") },
			{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		],
		(v) => {
			const params = new URLSearchParams({ student: frm.doc.name, to_date: v.to_date || "" });
			if (v.from_date) params.set("from_date", v.from_date);
			window.open(`/api/method/school_erp.api.statement.download_statement?${params}`);
		},
		__("Fee Statement"),
		__("Download"),
	);
}
