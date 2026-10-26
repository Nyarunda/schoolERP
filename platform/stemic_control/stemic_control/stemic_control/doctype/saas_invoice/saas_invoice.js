const INVOICE_COLORS = { Draft: "gray", Unpaid: "orange", "Partly Paid": "yellow", Paid: "green", Overdue: "red", Cancelled: "gray" };

frappe.ui.form.on("SaaS Invoice", {
    setup(frm) {
        frm.set_query("subscription", () => ({ filters: { status: ["!=", "Cancelled"], ...(frm.doc.tenant ? { tenant: frm.doc.tenant } : {}) } }));
    },
    refresh(frm) {
        if (frm.doc.docstatus === 1) frm.page.set_indicator(__(frm.doc.status), INVOICE_COLORS[frm.doc.status] || "gray");
        if (frm.doc.docstatus === 1 && frm.doc.outstanding > 0 && stemic_control.is_platform_admin()) {
            frm.add_custom_button(__("Record Payment"), () => stemic_control.record_payment(frm.doc.name, frm.doc.outstanding, () => frm.reload_doc()))
                .addClass("btn-primary");
        }
        if (!frm.is_new()) {
            frm.add_custom_button(__("Payments"), () => frappe.set_route("List", "SaaS Payment", { invoice: frm.doc.name }), __("View"));
            frm.add_custom_button(__("Subscription"), () => frappe.set_route("Form", "SaaS Subscription", frm.doc.subscription), __("View"));
        }
        if (frm.doc.docstatus === 1) {
            const left = frappe.datetime.get_diff(frm.doc.due_date, frappe.datetime.get_today());
            const msg = {
                Paid: __("Paid in full. The subscription runs to {0}.", [frappe.datetime.str_to_user(frm.doc.period_end)]),
                Overdue: __("{0} overdue since {1}.", [stemic_control.money(frm.doc.outstanding), frappe.datetime.str_to_user(frm.doc.due_date)]),
                Unpaid: __("{0} due in {1} days.", [stemic_control.money(frm.doc.outstanding), left]),
                "Partly Paid": __("{0} paid; {1} still owed.", [stemic_control.money(frm.doc.paid_amount), stemic_control.money(frm.doc.outstanding)]),
            }[frm.doc.status];
            if (msg) frm.set_intro(msg, { Paid: "green", Overdue: "red" }[frm.doc.status] || "orange");
        }
    },
    subscription(frm) {
        if (frm.doc.subscription) frappe.db.get_value("SaaS Subscription", frm.doc.subscription, "tenant").then(({ message }) => frm.set_value("tenant", message.tenant));
    },
});
