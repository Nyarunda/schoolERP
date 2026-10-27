// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("M-Pesa Transaction", {
	refresh(frm) {
		const colors = { Posted: "green", Unmatched: "orange", Failed: "red", "Needs Review": "red", Received: "blue", Ignored: "gray" };
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "gray");

		if (frm.doc.error && frm.doc.status !== "Posted") {
			frm.set_intro(frappe.utils.escape_html(frm.doc.error), ["Failed", "Needs Review"].includes(frm.doc.status) ? "red" : "orange");
		}
		if (["Unmatched", "Failed", "Needs Review", "Ignored", "Received"].includes(frm.doc.status) && !frm.is_new()) {
			// A payment held for review failed our checks: whoever releases it records what they checked it against
			const held = frm.doc.status === "Needs Review";
			const fields = [{ fieldname: "student", label: __("Student"), fieldtype: "Link", options: "Student", reqd: 1, default: frm.doc.student }];
			if (held) {
				fields.push(
					{ fieldname: "verified_reference", label: __("Checked against (Safaricom statement or transaction ref)"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "verification_note", label: __("Why it is genuine"), fieldtype: "Small Text", reqd: 1,
					  description: __("Only a School Admin or accountant can release a held payment.") });
			}
			frm.add_custom_button(held ? __("Check & Post") : __("Post to Student"), () => {
				frappe.prompt(
					fields,
					(v) => frappe.call({
						method: "school_erp.api.paybill.assign_and_post",
						args: { name: frm.doc.name, ...v },
						freeze: true,
						freeze_message: __("Posting..."),
					}).then(({ message }) => {
						frappe.show_alert({ message: __("Status: {0}", [message.status]), indicator: message.status === "Posted" ? "green" : "red" });
						frm.reload_doc();
					}),
					__("Which student is this payment for?"),
					__("Post"),
				);
			}).addClass("btn-primary");
		}
		if (frm.doc.fee_payment) {
			frm.add_custom_button(__("Fee Payment"), () => frappe.set_route("Form", "Fee Payment", frm.doc.fee_payment), __("View"));
		}
		if (frm.doc.student) {
			frm.add_custom_button(__("Student"), () => frappe.set_route("Form", "Student", frm.doc.student), __("View"));
		}
	},
});
