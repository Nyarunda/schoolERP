const DOMAIN_COLORS_FORM = { "Pending Verification": "orange", Verified: "blue", Active: "green", Disabled: "gray" };

frappe.ui.form.on("SaaS Domain", {
    onload(frm) {
        // A blank form would skip the checks and the DNS token; claim through the dialog instead
        if (!frm.is_new()) return;
        const tenant = frm.doc.tenant;
        frappe.set_route("List", "SaaS Domain").then(() => stemic_control.claim_domain(tenant));
    },
    refresh(frm) {
        if (frm.is_new()) return;
        frm.page.set_indicator(__(frm.doc.status), DOMAIN_COLORS_FORM[frm.doc.status] || "gray");
        if (frm.doc.status !== "Pending Verification") return;
        const esc = frappe.utils.escape_html;
        frm.set_intro(
            `<b>${__("To verify this domain, publish this DNS record:")}</b>
            <table class="table table-bordered" style="margin:8px 0 0;max-width:720px;background:var(--fg-color)">
                <tr><td style="width:90px">${__("Type")}</td><td><code>TXT</code></td></tr>
                <tr><td>${__("Name")}</td><td><code>_stemic-verification.${esc(frm.doc.hostname)}</code></td></tr>
                <tr><td>${__("Value")}</td><td><code style="word-break:break-all">${esc(frm.doc.verification_token || "")}</code></td></tr>
            </table>`,
            "orange",
        );
        frm.add_custom_button(__("Verify DNS"), () =>
            frappe.call({ method: "stemic_control.api.verify_domain", args: { domain: frm.doc.name }, freeze: true, freeze_message: __("Checking DNS...") })
                .then(() => {
                    frappe.show_alert({ message: __("Domain verified"), indicator: "green" });
                    frm.reload_doc();
                })).addClass("btn-primary");
    },
});
