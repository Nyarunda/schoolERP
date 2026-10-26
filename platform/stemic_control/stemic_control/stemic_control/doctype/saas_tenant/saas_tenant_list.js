const TENANT_COLORS = { Draft: "gray", Pending: "orange", Provisioning: "blue", Active: "green", Suspended: "red", Failed: "red" };

frappe.listview_settings["SaaS Tenant"] = {
    add_fields: ["status", "school_name"],
    get_indicator(doc) {
        return [__(doc.status), TENANT_COLORS[doc.status] || "gray", "status,=," + doc.status];
    },
};
