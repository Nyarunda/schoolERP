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
		setup_mpesa(frm);
		if (((frappe.boot.school_erp || {}).modules || []).includes("portal")) {
			frm.add_custom_button(__("Give All Parents Portal Access"), () =>
				frappe.confirm(__("Create parent portal logins for the guardians of every active student and SMS them their password?"), () =>
					frappe.call({ method: "school_erp.api.portal.give_portal_access", args: { all_students: 1 }, freeze: true, freeze_message: __("Creating logins...") })
						.then(({ message: m }) => frappe.msgprint(__("{0} new parent logins created, {1} guardians linked, {2} without a phone or email.", [m.new_logins, m.linked, m.without_contact])))),
				__("Parent Portal"));
		}
	},
	mpesa_callback_base_url: render_mpesa_urls,
	mpesa_enabled: render_mpesa_urls,
});

function setup_mpesa(frm) {
	render_mpesa_urls(frm);
	if (!frm.doc.mpesa_enabled) return;
	const grp = __("M-Pesa");

	frm.add_custom_button(__("Register URLs with Safaricom"), () => {
		if (frm.is_dirty()) return frappe.msgprint(__("Save first"));
		frappe.confirm(__("Register this site's callback URLs for paybill {0} ({1})?", [frm.doc.mpesa_shortcode, frm.doc.mpesa_environment]), () =>
			frappe.call({ method: "school_erp.api.paybill.register_urls", freeze: true, freeze_message: __("Contacting Safaricom...") })
				.then(({ message }) => {
					frappe.msgprint({ title: __("Registered"), indicator: "green", message: `<pre>${frappe.utils.escape_html(JSON.stringify(message.response, null, 1))}</pre>` });
					frm.reload_doc();
				}));
	}, grp);

	frm.add_custom_button(__("Test Payment (offline)"), () => {
		frappe.prompt(
			[
				{ fieldname: "bill_ref_number", label: __("Account No. (Student ID)"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1, default: 1000 },
				{ fieldname: "payer", label: __("Payer name"), fieldtype: "Data", default: "Test Parent" },
			],
			(v) => frappe.call({ method: "school_erp.api.paybill.local_test_payment", args: v, freeze: true }).then(({ message: m }) => {
				frappe.msgprint({
					title: __("Test payment {0}", [m.name]),
					indicator: m.status === "Posted" ? "green" : "orange",
					message: `${__("Status")}: <b>${m.status}</b>${m.student ? `<br>${__("Student")}: ${m.student}` : ""}${m.fee_payment ? `<br>${__("Fee Payment")}: <a href="/app/fee-payment/${m.fee_payment}">${m.fee_payment}</a>` : ""}${m.error ? `<br>${frappe.utils.escape_html(m.error)}` : ""}`,
				});
			}),
			__("Simulate a parent paying the Paybill (no Safaricom involved)"),
			__("Pay"),
		);
	}, grp);

	if (frm.doc.mpesa_environment === "Sandbox") {
		frm.add_custom_button(__("Simulate via Safaricom Sandbox"), () => {
			frappe.prompt(
				[
					{ fieldname: "bill_ref_number", label: __("Account No. (Student ID)"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "amount", label: __("Amount"), fieldtype: "Int", reqd: 1, default: 100 },
				],
				(v) => frappe.call({ method: "school_erp.api.paybill.simulate", args: v, freeze: true }).then(({ message }) =>
					frappe.msgprint(`<pre>${frappe.utils.escape_html(JSON.stringify(message, null, 1))}</pre>` +
						__("If accepted, Safaricom calls your confirmation URL within a few seconds. Check M-Pesa Transaction."))),
				__("Sandbox payment"),
			);
		}, grp);
	}

	frm.add_custom_button(__("Paybill Transactions"), () => frappe.set_route("List", "M-Pesa Transaction"), grp);
}

function render_mpesa_urls(frm) {
	const f = frm.get_field("mpesa_urls_html");
	if (!f) return;
	if (!frm.doc.mpesa_enabled || !frm.doc.mpesa_callback_token) {
		f.$wrapper.html(`<div class="text-muted small">${__("Tick 'Auto-post Paybill payments' and save to generate the callback URLs.")}</div>`);
		return;
	}
	const base = (frm.doc.mpesa_callback_base_url || window.location.origin).replace(/\/$/, "");
	const q = `?token=${frm.doc.mpesa_callback_token}`;
	const warn = /mpesa|m-pesa|safaricom|localhost|127\.0\.0\.1/i.test(base) || !base.startsWith("https://");
	f.$wrapper.html(`
		<div class="small">
			<div><b>${__("Confirmation URL")}</b><br><code>${base}/api/method/school_erp.api.paybill.confirm${q}</code></div>
			<div style="margin-top:6px"><b>${__("Validation URL")}</b><br><code>${base}/api/method/school_erp.api.paybill.validate${q}</code></div>
			${warn ? `<div style="margin-top:8px;color:var(--orange-600)">${__("Safaricom needs a public https address without the words mpesa/safaricom. Set 'Public Site URL'.")}</div>` : ""}
			<div class="text-muted" style="margin-top:6px">${__("Keep these URLs private: the token in them is what proves a callback is genuine.")}</div>
		</div>`);
}

function render_license(frm) {
	const status = (frm.doc.license_status || "Unlicensed").split(":")[0].toLowerCase();
	const color = { valid: "green", grace: "orange", expired: "red", invalid: "red" }[status] || "gray";
	frm.get_field("license_status_html").$wrapper.html(`
		<div class="indicator-pill ${color}" style="margin-bottom:8px">${frappe.utils.escape_html(frm.doc.license_status || __("No license key"))}</div>
		<div class="text-muted small">${__("Modules")}: ${frappe.utils.escape_html(frm.doc.licensed_modules || __("Core only"))}</div>
		${frm.doc.max_students ? `<div class="text-muted small">${__("Max active students")}: ${frm.doc.max_students}</div>` : ""}`);
}
