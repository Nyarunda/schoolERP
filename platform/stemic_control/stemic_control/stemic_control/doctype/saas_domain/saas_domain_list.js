const DOMAIN_COLORS = { "Pending Verification": "orange", Verified: "blue", Active: "green", Disabled: "gray" };

frappe.listview_settings["SaaS Domain"] = {
    add_fields: ["status"],
    // domains are claimed through the API (it picks the type, checks the name and issues the DNS token)
    primary_action() {
        stemic_control.claim_domain(frappe.route_options && frappe.route_options.tenant);
    },
    get_indicator(doc) {
        return [__(doc.status), DOMAIN_COLORS[doc.status] || "gray", "status,=," + doc.status];
    },
};
