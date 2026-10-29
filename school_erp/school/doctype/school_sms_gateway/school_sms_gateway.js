frappe.ui.form.on("School SMS Gateway", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Send Test SMS"), () => {
			frappe.prompt(
				{ fieldname: "number", fieldtype: "Data", label: __("Phone number"), reqd: 1, default: frm.doc.test_number },
				({ number }) =>
					frappe
						.call({
							method: "school_erp.api.sms_gateway.send_test",
							args: { gateway: frm.doc.name, number },
							freeze: true,
							freeze_message: __("Sending..."),
						})
						.then(({ message: r }) =>
							r.sent
								? frappe.msgprint({ title: __("Sent"), indicator: "green",
									message: __("The gateway accepted the message to {0}. Check the phone.", [r.number]) })
								: frappe.msgprint({ title: __("Not sent"), indicator: "red",
									message: frappe.utils.escape_html(r.error || __("The gateway refused the message.")) })
						),
				__("Send Test SMS"),
				__("Send")
			);
		});
	},
});
