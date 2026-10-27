frappe.ui.form.on("SaaS eTIMS Invoice", {
    refresh(frm) {
        if (frm.is_new() || !["System Manager", "Stemic Platform Admin"].some((r) => frappe.user.has_role(r))) return;
        if (frm.doc.status === "Draft") {
            frm.add_custom_button(__("Approve Tax Review"), () => frappe.confirm(
                __("Confirm the legal seller, tax classification and totals have been checked."),
                () => frappe.call({ method: "stemic_control.etims.approve_invoice", args: { name: frm.doc.name } })
                    .then(() => frm.reload_doc())));
        }
        if (frm.doc.status === "Ready") {
            frm.add_custom_button(__("Queue eTIMS Submission"), () => frappe.confirm(
                __("Send this reviewed invoice to the configured certified integration?"),
                () => frappe.call({ method: "stemic_control.etims.queue_submission", args: { name: frm.doc.name } })
                    .then(() => frm.reload_doc())));
        }
        if (frm.doc.status === "Pending Submission") {
            // Never resend an uncertain submission: ask the provider what happened to it
            frm.add_custom_button(__("Reconcile With Provider"), () => frappe.confirm(
                __("Query provider status without submitting the invoice again?"),
                () => frappe.call({ method: "stemic_control.etims.reconcile_invoice", args: { name: frm.doc.name }, freeze: true })
                    .then(({ message }) => {
                        frappe.show_alert({ message: __("Status: {0}", [__(message.status)]), indicator: "blue" });
                        frm.reload_doc();
                    })));
        }
        frm.add_custom_button(__("Submission History"), () =>
            frappe.call({ method: "stemic_control.etims.invoice_history", args: { name: frm.doc.name }, type: "GET" })
                .then(({ message }) => {
                    const esc = frappe.utils.escape_html;
                    const rows = (message || []).map((e) => `<tr><td>${esc(frappe.datetime.str_to_user(e.recorded_on))}</td>
                        <td>${esc(e.event_type)}</td><td>${esc(e.old_status || "")} → ${esc(e.new_status || "")}</td>
                        <td>${esc(e.details || "")}</td></tr>`).join("");
                    frappe.msgprint({
                        title: __("Tax Submission History"), wide: true,
                        message: rows ? `<table class="table table-sm"><thead><tr><th>${__("When")}</th><th>${__("Event")}</th>
                            <th>${__("Status")}</th><th>${__("Details")}</th></tr></thead><tbody>${rows}</tbody></table>`
                            : __("No events yet."),
                    });
                }), __("View"));
    },
});
