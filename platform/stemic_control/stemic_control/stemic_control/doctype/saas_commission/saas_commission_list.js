frappe.listview_settings["SaaS Commission"] = {
    add_fields: ["status"],
    get_indicator(doc) {
        return [__(doc.status), { Due: "orange", Paid: "green", Cancelled: "gray" }[doc.status] || "gray", "status,=," + doc.status];
    },
    onload(list) {
        if (!stemic_control.is_platform_admin()) return;
        list.page.add_inner_button(__("Pay an Agent"), () => frappe.prompt([
            { fieldname: "agent", fieldtype: "Link", options: "SaaS Agent", label: __("Agent"), reqd: 1 },
            { fieldname: "reference", fieldtype: "Data", label: __("Payout Reference"), reqd: 1, description: __("Marks all of this agent's due commission as paid.") },
        ], (v) => frappe.call({ method: "stemic_control.billing.pay_commissions", args: v, freeze: true }).then(({ message }) => {
            frappe.show_alert({ message: __("{0} commission(s) paid, {1}", [message.paid, stemic_control.money(message.total)]), indicator: "green" });
            list.refresh();
        }), __("Pay Commission"), __("Mark Paid")));
    },
};
