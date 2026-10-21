// Copyright (c) 2026, School ERP and contributors
// Designed to be filled on a phone before the morning pickup.

frappe.ui.form.on("Driver Daily Log", {
	setup(frm) {
		frm.set_query("vehicle", () => ({ filters: { is_active: 1 } }));
		frm.set_query("route", () => ({ filters: { is_active: 1 } }));
		frm.set_query("driver", () => ({ filters: { staff_type: "Driver", status: ["!=", "Left"] } }));
	},

	onload(frm) {
		if (!frm.is_new()) return;
		frappe.call("school_erp.api.transport_ops.driver_defaults").then(({ message: d }) => {
			if (!d) return;
			["driver", "vehicle", "route", "odometer_start"].forEach((f) => d[f] && !frm.doc[f] && frm.set_value(f, d[f]));
			if (!(frm.doc.checklist || []).length) {
				d.checklist.forEach((item) => frm.add_child("checklist", { item, ok: 0 }));
				frm.refresh_field("checklist");
			}
		});
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Everything is OK"), () => {
				(frm.doc.checklist || []).forEach((r) => frappe.model.set_value(r.doctype, r.name, "ok", 1));
				frappe.show_alert({ message: __("All checks ticked. Untick anything that is not OK."), indicator: "green" });
			});
			frm.set_intro(__("Check the vehicle before leaving. Untick any item that is not OK and describe it. The transport manager is alerted automatically."), "blue");
		}
		if (frm.doc.has_issues) {
			frm.dashboard.set_headline_alert(__("Issues reported on this check-in"), "red");
		}
	},
});
