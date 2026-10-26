const LICENSE_COLORS = { Pending: "orange", Issued: "green", Revoked: "red" };

frappe.listview_settings["SaaS License"] = {
    add_fields: ["status", "expires_on"],
    get_indicator(doc) {
        const left = doc.expires_on ? frappe.datetime.get_diff(doc.expires_on, frappe.datetime.get_today()) : null;
        if (doc.status === "Issued" && left !== null && left <= 30) {
            return [left < 0 ? __("Expired") : __("Expires in {0}d", [left]), left < 0 ? "red" : "orange", "status,=,Issued"];
        }
        return [__(doc.status), LICENSE_COLORS[doc.status] || "gray", "status,=," + doc.status];
    },
};
