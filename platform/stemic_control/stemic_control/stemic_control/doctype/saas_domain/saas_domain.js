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
        if (frm.doc.domain_type === "Custom Domain" && ["Verified", "Active"].includes(frm.doc.status)) return serving(frm);
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

// Verified -> live -> main address (stemic_control/domains.py)
function serving(frm) {
    const d = frm.doc, esc = frappe.utils.escape_html;
    const call = (method, msg) => frappe.call({ method: `stemic_control.domains.${method}`, args: { domain: d.name }, freeze: true,
                                               freeze_message: __("Working...") })
        .then(() => { frappe.show_alert({ message: msg, indicator: "green" }); frm.reload_doc(); });
    frappe.call({ method: "stemic_control.domains.status", args: { domain: d.name } }).then(({ message: s }) => {
        const server = s.server || {};
        const route = !s.sync_installed ? __("The server's domain sync is not installed (server/README.md).")
            : server.problem ? esc(server.message || server.problem)
            : server.certificate ? __("Set up on the server, with certificate {0}.", [esc(server.certificate)])
            : __("Waiting for the server to set it up.");
        if (d.status === "Verified") {
            frm.set_intro(`<b>${__("Ownership verified. To make it live:")}</b><ol style="margin:6px 0 0;padding-left:18px">
                <li>${__("DNS: a CNAME record {0} pointing to {1} (Proxied, the orange cloud, in Cloudflare).",
                         [`<code>${esc(d.hostname)}</code>`, `<code>${esc(s.platform_domain)}</code>`])}</li>
                <li>${__("Server")}: ${route}</li>
                <li>${__("Then click Check and Activate. This also happens on its own every hour.")}</li></ol>`, "blue");
            frm.add_custom_button(__("Check and Activate"), () => call("activate", __("{0} is live", [d.hostname]))).addClass("btn-primary");
        } else {
            frm.set_intro(s.primary ? __("Live, and the school's main address: its emails and links use {0}.", [esc(d.hostname)])
                : __("Live. The school's emails and links still use its own subdomain; Make Primary switches them to {0}.", [esc(d.hostname)]),
                "green");
            if (!s.primary) frm.add_custom_button(__("Make Primary"), () => frappe.confirm(
                __("Use {0} in the school's emails and links from now on?", [esc(d.hostname)]),
                () => call("make_primary", __("{0} is now the main address", [d.hostname])))).addClass("btn-primary");
        }
        frm.add_custom_button(__("Disable"), () => frappe.confirm(
            __("Stop serving {0}? The school stays reachable at its own subdomain.", [esc(d.hostname)]),
            () => call("disable", __("{0} disabled", [d.hostname]))));
    });
}
