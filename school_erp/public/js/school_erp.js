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
		const href = d.doctype ? `/app/${frappe.router.slug(d.doctype)}/${encodeURIComponent(d.name)}` : null;
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
