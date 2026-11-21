const TENANT_COLORS = { Draft: "gray", "Pending Approval": "yellow", Approved: "cyan", Rejected: "red", Pending: "orange", Provisioning: "blue", Active: "green", Suspended: "red", Failed: "red" };

frappe.listview_settings["SaaS Tenant"] = {
    add_fields: ["status", "school_name"],
    get_indicator(doc) {
        return [__(doc.status), TENANT_COLORS[doc.status] || "gray", "status,=," + doc.status];
    },
    onload(listview) {
        // one form for the whole journey; the blank form stays under the usual Add button
        if (stemic_control.is_platform_admin()) {
            listview.page.add_inner_button(__("Onboard a School"), () => stemic_control.onboard_school())
                .removeClass("btn-default").addClass("btn-primary");
            listview.page.add_inner_button(__("Update All Schools"), () => stemic_control.update_all_schools(), __("Service"));
            listview.page.add_inner_button(__("Service Health"), () => stemic_control.service_health(), __("Service"));
            const bulk = (action, label) => listview.page.add_actions_menu_item(label, () => {
                const tenants = listview.get_checked_items(true);
                if (!tenants.length) return frappe.msgprint(__("Tick the schools first."));
                frappe.confirm(__("{0} for {1} school(s), one at a time?", [label, tenants.length]), () =>
                    frappe.xcall("stemic_control.service.bulk_action", { tenants, action }).then(stemic_control.batch_started));
            }, true);
            bulk("Backup", __("Back Up"));
            bulk("Migrate", __("Update (Migrate)"));
            bulk("Clear Cache", __("Clear Cache"));
            listview.page.add_actions_menu_item(__("Tell About Maintenance"), () => {
                const tenants = listview.get_checked_items(true);
                if (!tenants.length) return frappe.msgprint(__("Tick the schools first."));
                frappe.prompt([
                    { fieldname: "when", label: __("When"), fieldtype: "Data", reqd: 1, description: __("e.g. Saturday 23 Nov, 10pm to 11pm") },
                    { fieldname: "message", label: __("Message"), fieldtype: "Small Text", reqd: 1,
                        default: __("We will update your school system. It may be unavailable for a short time. Please save your work before then.") },
                ], (v) => frappe.xcall("stemic_control.service.notify_maintenance", { tenants, ...v }).then((r) =>
                    frappe.show_alert({ message: __("Emailed {0} school(s)", [r.sent.length]), indicator: "green" })),
                __("Tell {0} school(s) about maintenance", [tenants.length]), __("Send"));
            }, true);
        }
    },
};
