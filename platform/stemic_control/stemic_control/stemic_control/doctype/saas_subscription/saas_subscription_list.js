const SUBSCRIPTION_COLORS = { Trial: "blue", Active: "green", "Past Due": "orange", Grace: "orange", Suspended: "red", Cancelled: "gray" };

frappe.listview_settings["SaaS Subscription"] = {
    add_fields: ["status", "ends_on"],
    get_indicator(doc) {
        const left = doc.ends_on ? frappe.datetime.get_diff(doc.ends_on, frappe.datetime.get_today()) : null;
        if (doc.status === "Active" && left !== null && left <= 30) {
            return [left < 0 ? __("Ended") : __("Ends in {0}d", [left]), left < 0 ? "red" : "orange", "status,=,Active"];
        }
        return [__(doc.status), SUBSCRIPTION_COLORS[doc.status] || "gray", "status,=," + doc.status];
    },
};
