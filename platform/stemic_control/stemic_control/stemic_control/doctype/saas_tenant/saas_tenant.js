const TENANT_COLORS_FORM = { Draft: "gray", Pending: "orange", Provisioning: "blue", Active: "green", Suspended: "red", Failed: "red" };

frappe.ui.form.on("SaaS Tenant", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.page.set_indicator(__(frm.doc.status), TENANT_COLORS_FORM[frm.doc.status] || "gray");
        if (frm.doc.canonical_site) frm.add_custom_button(__("Open Site"), () => open_site(frm));
        show_progress(frm);
        // Manual fallbacks for the automated provisioner
        if (frm.doc.status === "Pending") {
            frm.add_custom_button(__("Provision Now"), () =>
                frappe.call({ method: "stemic_control.api.provision_tenant_now", args: { tenant: frm.doc.name } }).then(() => {
                    frappe.show_alert({ message: __("Handed to the provisioner"), indicator: "blue" });
                    setTimeout(() => frm.reload_doc(), 4000);
                }), __("Actions"));
        }
        if (["Draft", "Failed"].includes(frm.doc.status)) {
            frm.add_custom_button(frm.doc.status === "Failed" ? __("Retry Provisioning") : __("Queue Provisioning"), () =>
                frappe.call({
                    method: "stemic_control.api.queue_provisioning",
                    args: { tenant: frm.doc.name, request_key: `${frm.doc.name}-${Date.now()}` },
                    freeze: true,
                }).then(({ message }) => {
                    frappe.show_alert({ message: __("Queued {0}", [message]), indicator: "green" });
                    frm.reload_doc();
                }), __("Actions"));
        }
        frm.add_custom_button(__("Claim a Domain"), () => stemic_control.claim_domain(frm.doc.name), __("Actions"));
        if (["Active", "Suspended"].includes(frm.doc.status)) {
            const next = frm.doc.status === "Active" ? "Suspended" : "Active";
            frm.add_custom_button(next === "Suspended" ? __("Suspend") : __("Resume"), () =>
                frappe.confirm(__("Set {0} to {1}?", [frm.doc.school_name, __(next)]), () =>
                    frappe.call({ method: "stemic_control.api.set_tenant_status", args: { tenant: frm.doc.name, status: next } })
                        .then(() => frm.reload_doc())), __("Actions"));
        }
        frm.add_custom_button(__("Domains"), () => frappe.set_route("List", "SaaS Domain", { tenant: frm.doc.name }), __("View"));
        frm.add_custom_button(__("Provisioning Jobs"), () => frappe.set_route("List", "SaaS Provisioning Job", { tenant: frm.doc.name }), __("View"));
        if (frm.doc.subscription) {
            frm.add_custom_button(__("Subscription"), () => frappe.set_route("Form", "SaaS Subscription", frm.doc.subscription), __("View"));
        }
    },
});

// Pending / Provisioning: say what is happening and refresh until it settles; Failed: show why
function show_progress(frm) {
    clearTimeout(frm._stemic_poll);
    if (["Pending", "Provisioning"].includes(frm.doc.status)) {
        frm.set_intro(frm.doc.status === "Pending"
            ? __("Waiting for the provisioner to pick up the site job. This page refreshes by itself.")
            : __("Creating the school's site (database, ERPNext and School ERP). This usually takes 3 to 8 minutes; the page refreshes by itself."), "blue");
        frm._stemic_poll = setTimeout(() => {
            if (frappe.get_route()[0] === "Form" && cur_frm === frm && !frm.is_dirty()) frm.reload_doc();
        }, 15000);
    } else if (frm.doc.status === "Failed") {
        frappe.db.get_list("SaaS Provisioning Job", { filters: { tenant: frm.doc.name, status: "Failed" }, fields: ["name", "last_error"],
                                                      order_by: "creation desc", limit: 1 })
            .then((rows) => rows.length && frm.set_intro(
                `<b>${__("Provisioning failed")}</b> (${frappe.utils.escape_html(rows[0].name)}). ${__("Fix the cause, then use Actions > Retry Provisioning.")}
                 <pre style="margin:8px 0 0;max-height:160px;overflow:auto;white-space:pre-wrap">${frappe.utils.escape_html((rows[0].last_error || "").slice(-1500))}</pre>`, "red"));
    }
}

function open_site(frm) {
    const site = frm.doc.canonical_site;
    if (!/\.localhost$/.test(site)) return window.open(`https://${frm.doc.primary_domain || site}`);
    // A local site is not served by `bench start` (it serves the default site), so say how to run it
    const port = 8002;
    const d = new frappe.ui.Dialog({
        title: __("Open {0}", [frm.doc.school_name]),
        fields: [{ fieldname: "info", fieldtype: "HTML" }],
        primary_action_label: __("Open in Browser"),
        primary_action: () => window.open(`http://${site}:${port}`),
        secondary_action_label: __("Show Password"),
        secondary_action: () => frappe.call({ method: "stemic_control.api.site_access", args: { tenant: frm.doc.name } })
            .then(({ message }) => d.fields_dict.info.$wrapper.find(".sc-pass").text(message.password || __("(not stored)"))),
    });
    d.fields_dict.info.$wrapper.html(`<div class="sc-preview">
        <div class="sc-preview-host">${frappe.utils.escape_html(site)}<span class="sc-badge ok">${__("Provisioned")}</span></div>
        <ol>
            <li>${__("Start it in a terminal:")}<br><code>cd ~/frappe-bench && bench --site ${frappe.utils.escape_html(site)} serve --port ${port}</code></li>
            <li>${__("Open")} <code>http://${frappe.utils.escape_html(site)}:${port}</code> ${__("and log in as Administrator")}</li>
            <li>${__("Password:")} <code class="sc-pass">••••••••</code></li>
        </ol></div>`);
    d.show();
}
