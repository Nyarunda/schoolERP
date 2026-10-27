frappe.listview_settings["SaaS Invoice"] = {
    add_fields: ["status", "outstanding", "docstatus"],
    get_indicator(doc) {
        const colors = { Draft: "gray", Unpaid: "orange", "Partly Paid": "yellow", Paid: "green", Overdue: "red", Cancelled: "gray" };
        return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
    },
};
