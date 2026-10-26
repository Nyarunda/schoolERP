frappe.listview_settings["SaaS Plan"] = {
    add_fields: ["enabled", "modules"],
    get_indicator(doc) {
        return doc.enabled ? [__("Enabled"), "green", "enabled,=,1"] : [__("Disabled"), "gray", "enabled,=,0"];
    },
    formatters: {
        student_limit: (value) => (cint(value) ? value : __("No limit")),
    },
};
