// Shared admin-site helpers (loaded on every desk page of the admin site only).
frappe.provide("stemic_control");

(() => {
    let info = null;
    const platform = () => info
        ? Promise.resolve(info)
        : frappe.call({ method: "stemic_control.api.platform_info", type: "GET" }).then(({ message }) => (info = message));
    const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

    // Claim a hostname for a school through the API (which picks the type, checks the name and issues the DNS token).
    stemic_control.claim_domain = (tenant) => platform().then(({ platform_domain }) => {
        const d = new frappe.ui.Dialog({
            title: __("Claim a Domain"),
            size: "large",
            fields: [
                { fieldname: "tenant", fieldtype: "Link", options: "SaaS Tenant", label: __("School"), reqd: 1, default: tenant,
                  onchange: () => update() },
                { fieldname: "kind", fieldtype: "HTML" },
                { fieldname: "hostname", fieldtype: "Data", label: __("Custom hostname"), placeholder: "portal.yourschool.ac.ke",
                  description: __("A hostname the school controls, e.g. portal.greenhill.ac.ke. Not a URL: no https:// or paths."),
                  onchange: () => update() },
                { fieldname: "preview", fieldtype: "HTML" },
            ],
            primary_action_label: __("Claim Domain"),
            primary_action: (v) => {
                const host = kind === "sub" ? subdomain() : (v.hostname || "").trim().toLowerCase();
                if (!host) return frappe.msgprint(__("Enter the custom hostname"));
                d.get_primary_btn().prop("disabled", true);
                frappe.call({ method: "stemic_control.api.request_domain", args: { tenant: v.tenant, hostname: host } })
                    .then(({ message: m }) => {
                        d.hide();
                        frappe.show_alert({ message: m.status === "Verified" ? __("{0} is ready", [m.hostname]) : __("{0} claimed: publish the DNS record", [m.hostname]),
                                            indicator: m.status === "Verified" ? "green" : "orange" }, 7);
                        frappe.set_route("Form", "SaaS Domain", m.domain);
                    })
                    .always(() => d.get_primary_btn().prop("disabled", false));
            },
        });
        let kind = "sub";
        const subdomain = () => (d.get_value("tenant") ? `${d.get_value("tenant")}.${platform_domain}` : "");

        const choice = (key, icon, title, text) => `<button type="button" class="sc-choice ${kind === key ? "on" : ""}" data-kind="${key}">
            <span class="sc-choice-ic">${frappe.utils.icon(icon, "md")}</span>
            <span><b>${esc(title)}</b><small>${esc(text)}</small></span></button>`;

        function update() {
            d.fields_dict.kind.$wrapper.html(`<div class="sc-choices">
                ${choice("sub", "globe", __("School subdomain"), __("{0}: ready immediately", ["<slug>." + platform_domain]))}
                ${choice("custom", "link", __("Custom domain"), __("The school's own name: verified by a DNS record"))}
            </div>`);
            d.set_df_property("hostname", "hidden", kind !== "custom");
            const host = kind === "sub" ? subdomain() : (d.get_value("hostname") || "").trim().toLowerCase();
            const steps = kind === "sub"
                ? [__("The platform owns {0}, so the subdomain is verified at once.", [platform_domain]),
                   __("It goes live when the school's site is provisioned.")]
                : [__("We give you a TXT record: _stemic-verification.{0}", [host || "<hostname>"]),
                   __("The school adds it at its DNS provider."),
                   __("Press Verify DNS on the domain once it has propagated (minutes to a few hours).")];
            d.fields_dict.preview.$wrapper.html(`<div class="sc-preview">
                <div class="sc-preview-host">${host ? esc(host) : `<span class="text-muted">${kind === "sub" ? __("Pick a school") : __("Type a hostname")}</span>`}
                    <span class="sc-badge ${kind === "sub" ? "ok" : "wait"}">${kind === "sub" ? __("Verified on claim") : __("Needs DNS verification")}</span></div>
                <ol>${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
            </div>`);
            d.fields_dict.kind.$wrapper.find("[data-kind]").on("click", function () {
                kind = this.dataset.kind;
                update();
                if (kind === "custom") d.fields_dict.hostname.$input.focus();
            });
        }
        d.show();
        update();
        return d;
    });
})();

// Shared pieces for the Plan, Subscription and License forms
Object.assign(stemic_control, {
    MODULE_HELP: {
        fees: __("Fee structures, termly billing, receipts and statements"),
        timetable: __("Class timetables, subjects, periods and double lessons"),
        transport: __("Bus routes and transport fees"),
        lunch: __("Lunch programme fees"),
        activities: __("Games, clubs and activity fees"),
        messaging: __("Bulk SMS and email to parents"),
        mpesa: __("Paybill and Till payments posted automatically"),
        staff: __("Staff records, leave, duty rosters and reports"),
        welfare: __("Discipline incidents and complaints"),
        expenses: __("School expenses with approvals"),
        transport_ops: __("Vehicles, fuel and drivers' daily logs"),
        exams: __("Exams, mark sheets, merit lists and report cards"),
        portal: __("Parent portal and M-Pesa prompts to pay"),
    },
    hero(color, icon, title, text, extra = "") {
        return `<div class="scx-hero ${color}"><div class="scx-ic">${frappe.utils.icon(icon, "md")}</div>
            <div><h4>${title}</h4><p>${text}</p>${extra}</div></div>`;
    },
    tile(label, value, note = "", bar = null) {
        const b = bar ? `<div class="scx-bar" style="--scx-bar:var(--${bar.color}-500)"><i style="width:${bar.pct}%"></i></div>
            ${bar.from ? `<div class="scx-ends"><span>${bar.from}</span><span>${bar.to}</span></div>` : ""}` : "";
        return `<div class="scx-tile"><span>${label}</span><b>${value}</b>${b}${note ? `<small>${note}</small>` : ""}</div>`;
    },
    is_platform_admin() {
        return frappe.user.has_role(["System Manager", "Stemic Platform Admin"]);
    },
    money(v) {
        return format_currency(v || 0, frappe.boot.sysdefaults.currency, 0);
    },
});
