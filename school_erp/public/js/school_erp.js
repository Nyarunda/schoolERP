// Keep modules the school has not licensed out of the sidebar. Runs before the desk draws it; workspaces are
// filtered on the server (school_erp.licensing.get_desktop_page).
(() => {
	const lic = frappe.boot && frappe.boot.school_erp;
	const shell = frappe.boot && frappe.boot.module_sidebars && frappe.boot.module_sidebars.School;
	if (!lic || !shell || !(lic.hidden_doctypes || []).length) return;
	const hidden = { DocType: new Set(lic.hidden_doctypes), Report: new Set(lic.hidden_reports || []) };
	const kept = shell.items.filter((i) => !(i.type === "Link" && hidden[i.link_type] && hidden[i.link_type].has(i.link_to)));
	// a section heading with nothing left under it goes too
	shell.items = kept.filter((i, n) => i.type !== "Section Break" || (kept[n + 1] && kept[n + 1].child));
})();

// Global: license banner for admins
$(document).on("app_ready", () => {
	const lic = frappe.boot.school_erp;
	if (!lic || !frappe.user.has_role(["System Manager", "School Admin"])) return;
	const warn = ["grace", "expired", "invalid"].includes(lic.status) || (lic.days_left !== null && lic.days_left <= 30);
	if (warn) {
		frappe.show_alert({ message: __(lic.message), indicator: lic.status === "valid" ? "orange" : "red" }, 12);
	}
});

// Live toast for approvals and alerts sent to this user (see school_erp.api.notify)
$(document).on("app_ready", () => {
	frappe.realtime.on("school_toast", (d) => {
		const esc = frappe.utils.escape_html;
		const href = d.doctype ? frappe.utils.get_form_link(d.doctype, d.name) : null;
		const title = href ? `<a href="${href}" style="font-weight:600">${esc(d.title)}</a>` : `<b>${esc(d.title)}</b>`;
		frappe.show_alert({ message: title + (d.message ? `<div class="small" style="margin-top:2px">${esc(d.message)}</div>` : ""), indicator: d.indicator || "blue" }, 12);
		if (cur_frm && d.doctype === cur_frm.doctype && d.name === cur_frm.docname && !cur_frm.is_dirty()) cur_frm.reload_doc();
	});
});

// Students are customers too (Customer.student). Where a picker is for normal customers, keep ERPNext's own search
// and add "not a student" while `when(doc)` holds. Safe to call repeatedly: it never wraps itself.
frappe.provide("school_erp");
school_erp.exclude_students = function (frm, fieldname, when) {
	const field = frm.fields_dict[fieldname];
	if (!field || (field.get_query && field.get_query.__school_erp)) return;
	const base = field.get_query;
	const query = (doc, cdt, cdn) => {
		const q = Object.assign({}, typeof base === "function" ? base(doc, cdt, cdn) : base || {});
		if (when(doc)) {
			q.filters = Array.isArray(q.filters)
				? [...q.filters, ["Customer", "student", "is", "not set"]]
				: Object.assign({}, q.filters || {}, { student: ["is", "not set"] });
		}
		return q;
	};
	query.__school_erp = true;
	frm.set_query(fieldname, query);
};

// Graduate / Move Class: shared by the student form and the student list (bulk)
frappe.provide("school_erp");
school_erp.MOVE_REASONS = ["Repeating the class", "Promoted by mistake", "Moved up a class", "Change of stream", "Other"];

school_erp.report_bulk = function (r, what) {
	const esc = frappe.utils.escape_html;
	const lines = [__("{0} learner(s) {1}.", [r.done, what])];
	(r.failed || []).forEach((f) => lines.push(`<span style="color:var(--red-600)">${esc(f.student)}: ${esc(f.error)}</span>`));
	(r.warnings || []).forEach((w) => lines.push(`<span style="color:var(--orange-600)">${esc(w)}</span>`));
	frappe.msgprint({ title: __("Done"), indicator: (r.failed || []).length ? "orange" : "green", message: lines.join("<br>") });
};

school_erp.graduate_dialog = function (students, first_name, after) {
	const one = students.length === 1;
	frappe.prompt([
		{ fieldname: "leaving_date", label: __("Graduation date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "note", label: __("Note"), fieldtype: "Small Text", description: __("e.g. Completed Grade 9, KJSEA 2026") },
	], (v) => frappe.call({ method: one ? "school_erp.api.students.graduate" : "school_erp.api.students.bulk_graduate", freeze: true,
		args: one ? { student: students[0], ...v } : { students, ...v } }).then(({ message: r }) => {
		if (one) frappe.show_alert({ message: __("{0} has graduated", [first_name]), indicator: "green" });
		else school_erp.report_bulk(r, __("graduated"));
		after && after();
	}), one ? __("Graduate {0}", [first_name]) : __("Graduate {0} learners", [students.length]), __("Graduate"));
};

school_erp.move_class_dialog = function (students, doc, after) {
	const one = students.length === 1;
	const d = new frappe.ui.Dialog({
		title: one ? __("Move {0} to another class", [doc.first_name]) : __("Move {0} learners", [students.length]),
		fields: [
			{ fieldtype: "HTML", options: one ? `<p class="text-muted">${__("Now in {0}.", [frappe.utils.escape_html(doc.stream || doc.school_class || "-")])}</p>` : "" },
			{ fieldname: "stream", label: __("Move to stream"), fieldtype: "Link", options: "Stream", reqd: 1,
				get_query: () => ({ filters: { is_active: 1 } }) },
			{ fieldname: "reason", label: __("Reason"), fieldtype: "Select", reqd: 1, options: school_erp.MOVE_REASONS.join("\n"),
				default: "Repeating the class" },
			{ fieldname: "note", label: __("Note"), fieldtype: "Small Text" },
			{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Invoices already raised are not changed. The move is noted on the learner's timeline.")}</p>` },
		],
		primary_action_label: __("Move"),
		primary_action(v) {
			d.hide();
			frappe.call({ method: one ? "school_erp.api.students.move_class" : "school_erp.api.students.bulk_move", freeze: true,
				args: one ? { student: students[0], ...v } : { students, ...v } }).then(({ message: r }) => {
				if (one) {
					frappe.show_alert({ message: __("Moved to {0}", [r.to]), indicator: "green" });
					if (r.warning) frappe.msgprint({ title: __("Check the fees"), indicator: "orange", message: frappe.utils.escape_html(r.warning) });
				} else school_erp.report_bulk(r, __("moved"));
				after && after();
			});
		},
	});
	d.show();
};
