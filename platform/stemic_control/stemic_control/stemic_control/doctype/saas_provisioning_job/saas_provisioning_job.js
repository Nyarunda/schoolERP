const JOB_COLORS_FORM = { Queued: "orange", Running: "blue", Succeeded: "green", Failed: "red" };

frappe.ui.form.on("SaaS Provisioning Job", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.page.set_indicator(__(frm.doc.status), JOB_COLORS_FORM[frm.doc.status] || "gray");
        if (frm.doc.status === "Queued" && frm.doc.action === "Create Site") {
            frm.add_custom_button(__("Provision Now"), () =>
                frappe.call({ method: "stemic_control.api.provision_now", args: { job: frm.doc.name } }).then(() => {
                    frappe.show_alert({ message: __("Handed to the provisioner"), indicator: "blue" });
                    setTimeout(() => frm.reload_doc(), 4000);
                })).addClass("btn-primary");
        }
        if (frm.doc.status === "Running") {
            // Manual fallback when a worker died mid-job (the scheduler also does this after 90 minutes)
            frm.add_custom_button(__("Mark Failed"), () =>
                frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Why"), reqd: 1,
                                default: __("Stopped by an operator: the worker appeared to be stuck") },
                    ({ reason }) => frappe.call({ method: "stemic_control.api.record_job_result", args: { job: frm.doc.name, status: "Failed", error: reason } })
                        .then(() => frm.reload_doc()),
                    __("Mark this job Failed?"), __("Mark Failed")));
            frm.set_intro(__("The site is being created. This page refreshes by itself."), "blue");
            setTimeout(() => cur_frm === frm && frm.reload_doc(), 15000);
        }
        if (frm.doc.status === "Failed" && frm.doc.last_error) frm.set_intro(__("Failed: see Last Error below."), "red");
        frm.add_custom_button(__("School"), () => frappe.set_route("Form", "SaaS Tenant", frm.doc.tenant), __("View"));
    },
});
