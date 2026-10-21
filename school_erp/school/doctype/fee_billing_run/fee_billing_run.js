// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Fee Billing Run", {
	setup(frm) {
		frm.set_query("stream", () => (frm.doc.school_class ? { filters: { school_class: frm.doc.school_class } } : {}));
	},

	school_term(frm) {
		if (frm.doc.school_term && !frm.doc.due_date) {
			frappe.db.get_value("School Term", frm.doc.school_term, "start_date").then(({ message }) => {
				frm.set_value("due_date", message.start_date);
			});
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.school_term) {
			frm.add_custom_button(__("Preview"), () => preview(frm)).addClass("btn-primary");
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Invoices"), () => frappe.set_route("List", "Sales Invoice", { fee_billing_run: frm.doc.name }));
			if (["Queued", "Running"].includes(frm.doc.status)) {
				frm.dashboard.set_headline_alert(__("Billing in progress..."), "blue");
				frappe.realtime.on("fee_billing_run_done", (d) => d.name === frm.doc.name && frm.reload_doc());
				setTimeout(() => ["Queued", "Running"].includes(frm.doc.status) && frm.reload_doc(), 8000);
			}
		}
	},
});

function preview(frm) {
	frappe.call({
		method: "school_erp.api.billing.preview_billing",
		args: { school_term: frm.doc.school_term, school_class: frm.doc.school_class, stream: frm.doc.stream },
		freeze: true,
		freeze_message: __("Working out fees..."),
	}).then(({ message: p }) => {
		const rows = p.rows
			.map((r) => `<tr><td>${r.student}</td><td>${frappe.utils.escape_html(r.student_name)}</td><td>${r.school_class || ""}</td>
				<td style="font-size:11px;color:var(--text-muted)">${r.lines.map((l) => `${l.fee_type} ${format_number(l.amount)}`).join(", ")}</td>
				<td style="text-align:right">${format_currency(r.total)}</td></tr>`)
			.join("");
		const d = new frappe.ui.Dialog({
			title: __("Billing Preview - {0}", [frm.doc.school_term]),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Looks right - Submit"),
			primary_action() { d.hide(); frm.savesubmit(); },
		});
		d.fields_dict.body.$wrapper.html(`
			<div style="display:flex;gap:24px;margin-bottom:12px">
				<div><div class="text-muted">${__("Will be billed")}</div><h3>${p.to_bill}</h3></div>
				<div><div class="text-muted">${__("Total")}</div><h3>${format_currency(p.total)}</h3></div>
				<div><div class="text-muted">${__("Already billed")}</div><h3>${p.already_billed}</h3></div>
				<div><div class="text-muted">${__("No fees found")}</div><h3>${p.no_fees}</h3></div>
			</div>
			<div style="max-height:420px;overflow:auto"><table class="table table-sm table-bordered">
				<thead><tr><th>${__("ID")}</th><th>${__("Student")}</th><th>${__("Class")}</th><th>${__("Fees")}</th><th style="text-align:right">${__("Total")}</th></tr></thead>
				<tbody>${rows}</tbody></table></div>`);
		d.show();
	});
}
