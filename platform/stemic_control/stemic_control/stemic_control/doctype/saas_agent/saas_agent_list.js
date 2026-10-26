frappe.listview_settings["SaaS Agent"] = {
    add_fields: ["status"],
    get_indicator(doc) {
        return [__(doc.status), doc.status === "Active" ? "green" : "gray", "status,=," + doc.status];
    },
};
