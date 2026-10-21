// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Leave Application", {
	setup(frm) {
		frm.set_query("reliever", () => ({ filters: { status: "Active", name: ["!=", frm.doc.staff_member || ""] } }));
		frm.set_query("staff_member", () => ({ filters: { status: ["!=", "Left"] } }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.staff_member) {
			frappe.call("school_erp.api.staff.my_staff_record").then((r) => r.message && frm.set_value("staff_member", r.message));
		}
	},

	refresh(frm) {
		const colors = { "Pending Approval": "orange", Approved: "green", Rejected: "red", Cancelled: "gray" };
		if (!frm.is_new()) frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status]);
		show_balance(frm);

		const can_decide = frm.doc.docstatus === 0 && !frm.is_new() && frm.doc.status === "Pending Approval" &&
			(frm.doc.approver === frappe.session.user || frappe.user.has_role(["Head Teacher", "School Admin", "System Manager"]));
		if (can_decide) {
			frm.page.clear_primary_action();
			frm.add_custom_button(__("Approve"), () => decide(frm, "Approved")).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => decide(frm, "Rejected")).addClass("btn-danger");
		} else if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.set_intro(__("Waiting for approval by {0}", [frm.doc.approver || __("the Head Teacher")]), "orange");
		}
	},

	staff_member: show_balance,
	leave_type: show_balance,
});

function decide(frm, decision) {
	frappe.prompt(
		{ fieldname: "comment", label: decision === "Rejected" ? __("Reason") : __("Comment (optional)"), fieldtype: "Small Text", reqd: decision === "Rejected" },
		(v) => frappe.call({ method: "school_erp.api.staff.decide_leave", args: { name: frm.doc.name, decision, comment: v.comment }, freeze: true })
			.then(() => {
				frappe.show_alert({ message: __("Leave {0}. The applicant (and reliever) have been notified.", [__(decision).toLowerCase()]), indicator: decision === "Approved" ? "green" : "red" });
				frm.reload_doc();
			}),
		decision === "Approved" ? __("Approve leave") : __("Reject leave"),
		__(decision === "Approved" ? "Approve" : "Reject"),
	);
}

function show_balance(frm) {
	if (!frm.doc.staff_member) return;
	frappe.call("school_erp.api.staff.leave_balances", { staff_member: frm.doc.staff_member }).then(({ message }) => {
		const rows = (message || []).filter((r) => r.entitled)
			.map((r) => `<tr${r.leave_type === frm.doc.leave_type ? ' style="font-weight:600"' : ""}><td>${frappe.utils.escape_html(r.leave_type)}</td>
				<td style="text-align:right">${r.entitled}</td><td style="text-align:right">${r.taken}</td>
				<td style="text-align:right">${r.pending}</td><td style="text-align:right">${r.balance}</td></tr>`).join("");
		frm.dashboard.reset();
		if (rows) {
			frm.dashboard.add_section(`<table class="table table-sm" style="margin:0">
				<thead><tr><th>${__("Leave balance this year")}</th><th style="text-align:right">${__("Entitled")}</th>
				<th style="text-align:right">${__("Taken")}</th><th style="text-align:right">${__("Pending")}</th>
				<th style="text-align:right">${__("Left")}</th></tr></thead><tbody>${rows}</tbody></table>`);
			frm.dashboard.show();
		}
	});
}
