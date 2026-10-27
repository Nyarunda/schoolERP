frappe.listview_settings["SaaS Tax Profile"] = {
    add_fields: ["enabled", "seller_pin"],
    get_indicator(doc) {
        if (doc.enabled) return [__("Ready"), "green", "enabled,=,1"];
        return [doc.seller_pin ? __("Draft") : __("PIN Missing"), "orange", "enabled,=,0"];
    },
};
