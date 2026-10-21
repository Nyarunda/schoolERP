// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Fee Payment", {
	setup(frm) {
		frm.set_query("student", () => ({ filters: { status: ["!=", "Graduated"] } }));
		frm.set_query("fee_type", "target_fee_types", () => ({}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.mode_of_payment) {
			frappe.db.get_single_value("School Settings", "default_mode_of_payment").then((m) => m && frm.set_value("mode_of_payment", m));
		}
	},

	refresh(frm) {
		frm.set_df_property("allocations", "read_only", frm.doc.manual_allocation ? 0 : 1);
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Print Receipt"), () => frm.print_doc());
			if (frm.doc.payment_entry) {
				frm.add_custom_button(__("Payment Entry"), () => frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry), __("View"));
			}
			frm.add_custom_button(__("Student"), () => frappe.set_route("Form", "Student", frm.doc.student), __("View"));
		}
		show_balances(frm);
	},

	student(frm) {
		show_balances(frm);
		if (frm.doc.student) {
			frappe.db.get_value("Student", frm.doc.student, ["primary_guardian", "primary_phone"]).then(({ message }) => {
				if (!frm.doc.payer_name) frm.set_value("payer_name", message.primary_guardian);
				if (!frm.doc.payer_phone) frm.set_value("payer_phone", message.primary_phone);
			});
		}
	},

	manual_allocation(frm) {
		frm.set_df_property("allocations", "read_only", frm.doc.manual_allocation ? 0 : 1);
	},
});

function show_balances(frm) {
	frm.set_intro("");
	if (!frm.doc.student || frm.doc.docstatus !== 0) return;
	frappe.call("school_erp.api.payments.get_open_balances", { student: frm.doc.student }).then(({ message: m }) => {
		if (!m) return;
		if (!m.by_fee_type.length) {
			frm.set_intro(__("Nothing is owed right now. This payment will be kept as an advance."), "blue");
			return;
		}
		const rows = m.by_fee_type
			.map((r) => `<tr><td>${frappe.utils.escape_html(r.fee_type)}</td><td style="text-align:right">${format_currency(r.outstanding)}</td></tr>`)
			.join("");
		frm.set_intro(
			`<b>${__("Currently owed")}: ${format_currency(m.balance)}</b>
			<table style="margin-top:6px;min-width:260px">${rows}</table>`,
			m.balance > 0 ? "orange" : "green",
		);
	});
}
