// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("School Message", {
	setup(frm) {
		frm.set_query("stream", () => (frm.doc.school_class ? { filters: { school_class: frm.doc.school_class } } : {}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.message) {
			frappe.db.get_single_value("School Settings", "reminder_sms_template").then((t) => t && frm.set_value("message", t));
		}
	},

	refresh(frm) {
		update_length(frm);
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Preview Recipients"), () => {
				frappe.call({ method: "school_erp.api.messaging.preview_audience", args: { doc: frm.doc }, freeze: true }).then(({ message: p }) => {
					const sample = p.sample
						.map((s) => `<div style="margin:8px 0;padding:8px;background:var(--subtle-fg);border-radius:6px">
							<b>${frappe.utils.escape_html(s.student_name)}</b><br>${frappe.utils.escape_html(s.text)}</div>`)
						.join("");
					frappe.msgprint({ title: __("{0} students", [p.count]), message: sample || __("No students match") });
				});
			});
		}
	},

	message: update_length,
});

function update_length(frm) {
	const n = (frm.doc.message || "").length;
	const parts = n <= 160 ? 1 : Math.ceil(n / 153);
	frm.get_field("sms_length").$wrapper.html(
		`<div class="text-muted small">${__("{0} characters, about {1} SMS per parent before placeholders are filled", [n, parts])}</div>`,
	);
}
