// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["CBC Progress Report"] = {
	get_indicator(doc) {
		return doc.status === "Published" ? [__("Published"), "green", "status,=,Published"] : [__("Draft"), "orange", "status,=,Draft"];
	},
	onload(listview) {
		const pick = (title, primary, action) => frappe.prompt([
			{ fieldname: "school_term", label: __("Term"), fieldtype: "Link", options: "School Term", reqd: 1 },
			{ fieldname: "stream", label: __("Stream (blank for all)"), fieldtype: "Link", options: "Stream" },
		], action, title, primary);
		listview.page.add_inner_button(__("Generate for a Term"), () => pick(__("Build progress reports from submitted assessments"), __("Generate"), (v) => {
			frappe.call({ method: "school_erp.api.cbc.generate_progress_reports", args: v, freeze: true }).then(({ message: r }) => {
				frappe.msgprint(__("{0} progress reports built from {1} assessments.", [r.progress_reports, r.assessments]));
				listview.refresh();
			});
		}));
		listview.page.add_inner_button(__("Publish for a Term"), () => pick(__("Publish to parents"), __("Publish"), (v) => {
			frappe.call({ method: "school_erp.api.cbc.publish_progress_reports", args: { ...v, notify_parents: 1 }, freeze: true }).then(({ message: r }) => {
				frappe.msgprint(__("{0} progress reports published.", [r.published]));
				listview.refresh();
			});
		}));
	},
};
