const JOB_COLORS = { Queued: "orange", Running: "blue", Succeeded: "green", Failed: "red" };

frappe.listview_settings["SaaS Provisioning Job"] = {
    add_fields: ["status"],
    onload(list) {
        // Manual run of the provisioner's 5-minute check
        list.page.add_inner_button(__("Process Queue Now"), () =>
            frappe.call({ method: "stemic_control.api.process_queue_now" }).then(({ message }) => {
                frappe.show_alert({ message: __("{0} job(s) handed to the provisioner", [message.handed_to_worker]), indicator: "blue" });
                setTimeout(() => list.refresh(), 3000);
            }));
    },
    get_indicator(doc) {
        return [__(doc.status), JOB_COLORS[doc.status] || "gray", "status,=," + doc.status];
    },
};
