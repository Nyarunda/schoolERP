// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("School Settings", {
	setup(frm) {
		frm.set_query("default_income_account", () => ({ filters: { company: frm.doc.company, root_type: "Income", is_group: 0 } }));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},

	refresh(frm) {
		frm.add_custom_button(__("Run School Setup"), () => {
			frappe.confirm(__("Create classes, fee types, terms, periods and subjects that are missing? Nothing existing is changed."), () => {
				frappe.call({ method: "school_erp.api.setup.run_setup", freeze: true, freeze_message: __("Setting up...") }).then(({ message }) => {
					frappe.msgprint({
						title: __("Setup complete"),
						indicator: "green",
						message: `<p>${__("Created")}: ${message.created.join(", ") || __("nothing new")}</p>
							<p><b>${__("Next steps")}</b></p><ol>${message.next_steps.map((s) => `<li>${s}</li>`).join("")}</ol>`,
					});
					frm.reload_doc();
				});
			});
		});
		render_license(frm);
	},
});

function render_license(frm) {
	const status = (frm.doc.license_status || "Unlicensed").split(":")[0].toLowerCase();
	const color = { valid: "green", grace: "orange", expired: "red", invalid: "red" }[status] || "gray";
	frm.get_field("license_status_html").$wrapper.html(`
		<div class="indicator-pill ${color}" style="margin-bottom:8px">${frappe.utils.escape_html(frm.doc.license_status || __("No license key"))}</div>
		<div class="text-muted small">${__("Modules")}: ${frappe.utils.escape_html(frm.doc.licensed_modules || __("Core only"))}</div>
		${frm.doc.max_students ? `<div class="text-muted small">${__("Max active students")}: ${frm.doc.max_students}</div>` : ""}`);
}
