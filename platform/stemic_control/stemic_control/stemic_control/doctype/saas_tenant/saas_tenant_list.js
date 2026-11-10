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
        }
    },
};
