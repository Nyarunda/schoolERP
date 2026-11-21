// Settings fields that site_config.json can override (stemic_control.config.SETTINGS)
const STEMIC_SERVER_KEYS = {
    platform_domain: "stemic_platform_domain", site_domain: "stemic_site_domain", site_apps: "stemic_site_apps",
    bench_path: "stemic_bench_path", local_provisioner: "stemic_local_provisioner", dns_over_https: "stemic_dns_over_https",
};

frappe.ui.form.on("Stemic Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Re-check Setup"), () => render_setup(frm));
        frm.add_custom_button(__("Check Domains"), () => check_platform_domains());
        if (frm.doc.notify_schools_by_sms) frm.add_custom_button(__("Send Test SMS"), () =>
            frappe.prompt({ fieldname: "number", fieldtype: "Data", label: __("Phone number"), reqd: 1, default: frm.doc.sms_test_number },
                ({ number }) => frappe.call({ method: "stemic_control.communications.send_test_sms", args: { number },
                    freeze: true, freeze_message: __("Sending...") }).then(({ message: r }) => r.sent
                    ? frappe.msgprint({ title: __("Sent"), indicator: "green", message: __("The gateway accepted it. Check the phone.") })
                    : frappe.msgprint({ title: __("Not sent"), indicator: "red", message: frappe.utils.escape_html(r.error || __("Refused")) })),
                __("Send Test SMS"), __("Send")));
        if (frm.doc.notify_schools_by_sms) frm.add_custom_button(__("Use Africa's Talking"), () => use_africas_talking(frm), __("SMS"));
        render_setup(frm);
        render_accounting(frm);
        render_preview(frm);
        show_payment_example(frm);
        company_choices(frm);
    },
    after_save(frm) {
        render_setup(frm);
        render_accounting(frm);
        render_preview(frm);
    },
    payment_instructions: show_payment_example,
    notify_schools_by_sms: (frm) => frm.refresh(),
});

// What {invoice} becomes, under Payment Instructions
function show_payment_example(frm) {
    const text = (frm.doc.payment_instructions || "").trim();
    const base = __("Shown on every invoice, reminder and welcome email, and in invoice SMS. Write {invoice} where the invoice number goes.");
    frm.set_df_property("payment_instructions", "description", text
        ? `${base}<br><b>${__("Schools will see")}:</b> ${frappe.utils.escape_html(text.replaceAll("{invoice}", "SINV-2026-00012"))}`
        : base);
}

// Fill the SMS gateway in for Africa's Talking; only the username, API key and sender ID are left to enter
function use_africas_talking(frm) {
    frappe.prompt([
        { fieldname: "username", fieldtype: "Data", label: __("Africa's Talking username"), reqd: 1,
          description: __("Your app's username (not 'sandbox' for real messages).") },
        { fieldname: "sender", fieldtype: "Data", label: __("Sender ID (optional)"),
          description: __("Your approved sender name, e.g. STEMIC. Blank uses Africa's Talking's shared short code.") },
    ], ({ username, sender }) => {
        frm.set_value({
            sms_url: "https://api.africastalking.com/version1/messaging", sms_http_method: "POST", sms_body_format: "Form",
            sms_recipient_param: "to", sms_message_param: "message", sms_number_format: "+2547XXXXXXXX",
            sms_sender_param: sender ? "from" : "", sms_sender_id: sender || "", sms_api_key_param: "apiKey",
            sms_api_key_in: "Header", sms_api_key_prefix: "", sms_parameters: `username=${username}\nheader:Accept=application/json`,
            sms_success_field: "SMSMessageData.Recipients.0.statusCode", sms_success_values: "100,101,102", sms_success_text: "",
        });
        frappe.msgprint(__("Filled in. Paste your Africa's Talking API key into API Key, save, then use Send Test SMS."));
    }, __("Use Africa's Talking"), __("Fill in"));
}

// Accounting: choose the company from ERPNext's list instead of typing it
function company_choices(frm) {
    frappe.call({ method: "stemic_control.accounting.overview", type: "GET" }).then(({ message: a }) => {
        if (!a || !a.erpnext) return;
        frappe.db.get_list("Company", { pluck: "name", limit: 50 }).then((names) =>
            frm.set_df_property("accounting_company", "options", names));
    });
}

// Communications: each email and its SMS with sample data, as schools will get them
function render_preview(frm) {
    const $w = frm.get_field("preview_html").$wrapper;
    if (!$w.find(".scx-preview").length) {
        $w.html(`<div class="scx-preview">
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
                <b>${__("Preview")}</b>
                <select class="form-control input-xs" style="max-width:220px" data-event></select>
                <span class="text-muted small">${__("Sample data, your branding, payment instructions and footer. Nothing is sent.")}</span>
            </div>
            <div class="small text-muted" data-subject style="margin-bottom:6px"></div>
            <iframe data-email style="width:100%;height:560px;border:1px solid var(--border-color);border-radius:8px;background:#fff"></iframe>
            <div class="small" data-sms style="margin-top:8px"></div>
        </div>`);
        $w.find("[data-event]").on("change", () => load_preview(frm));
    }
    load_preview(frm);
}

function load_preview(frm) {
    const $w = frm.get_field("preview_html").$wrapper;
    const $select = $w.find("[data-event]");
    frappe.call({ method: "stemic_control.communications.preview", type: "GET", args: { event: $select.val() || "Welcome" } })
        .then(({ message: p }) => {
            const esc = frappe.utils.escape_html;
            if (!$select.children().length) {
                $select.html(p.events.map((e) => `<option>${esc(e)}</option>`).join(""));
            }
            $w.find("[data-subject]").html(`${__("Subject")}: <b>${esc(p.subject)}</b>`);
            $w.find("[data-email]").attr("srcdoc", p.html);
            $w.find("[data-sms]").html(frm.doc.notify_schools_by_sms
                ? `${__("SMS")}: <code style="white-space:pre-wrap">${esc(p.sms)}</code> <span class="text-muted">(${p.sms.length} ${__("characters")})</span>`
                : `<span class="text-muted">${__("SMS is off: schools get the email only.")}</span>`);
        });
}

// Accounting tab: Stemic's own books in ERPNext on this site (stemic_control.accounting)
function render_accounting(frm) {
    const $w = frm.get_field("accounting_html").$wrapper;
    frappe.call({ method: "stemic_control.accounting.overview", type: "GET" }).then(({ message: a }) => {
        const esc = frappe.utils.escape_html;
        if (!a.erpnext) {
            $w.html(`<p class="text-muted">${__("ERPNext is not installed on this site, so invoices and payments stay in the Control Center. Install it to keep Stemic's books here.")}</p>`);
            return;
        }
        const rows = (map) => Object.entries(map || {}).map(([label, acc]) =>
            `<tr><td>${esc(label)}</td><td>${acc ? esc(acc) : `<span class="text-danger">${__("not set up")}</span>`}</td></tr>`).join("");
        $w.html(`<div class="scx-tile">
            <p>${a.enabled ? __("Posting to {0}.", [esc(a.company)]) : __("Not posting yet.")}
               ${a.unposted_invoices ? __("{0} submitted invoice(s) from before posting started are not in the books.", [a.unposted_invoices]) : ""}</p>
            ${a.company_exists ? `<table class="table table-sm"><tbody>${rows(a.accounts)}</tbody></table>
                <b>${__("Income by plan")}</b><table class="table table-sm"><tbody>${rows(a.plans)}</tbody></table>`
                : `<p class="text-muted">${__("Enter the ERPNext company that keeps Stemic's books, save, then Set Up Accounts.")}</p>`}
            <button class="btn btn-default btn-sm" data-setup-accounts>${__("Set Up Accounts")}</button>
        </div>`);
        $w.find("[data-setup-accounts]").on("click", () => {
            if (frm.is_dirty()) {
                frappe.msgprint(__("Save first."));
                return;
            }
            frappe.call({ method: "stemic_control.accounting.setup_accounts", type: "POST", freeze: true,
                freeze_message: __("Setting up accounts...") }).then(() => {
                frappe.show_alert({ message: __("Accounts ready"), indicator: "green" });
                render_accounting(frm);
                render_setup(frm);
            });
        });
    });
}

function render_setup(frm) {
    const $w = frm.get_field("setup_html").$wrapper;
    $w.html(`<p class="text-muted">${__("Checking...")}</p>`);
    frappe.call({ method: "stemic_control.setup_check.status", type: "GET" }).then(({ message: s }) => {
        const esc = frappe.utils.escape_html;
        const mark = (ok) => ok === true ? ["check", "green"] : ok === false ? ["triangle-alert", "red"] : ["info", "blue"];
        const areas = [...new Set(s.items.map((i) => i.area))];
        const problems = s.items.filter((i) => i.ok === false).length;
        $w.html(`<div class="scx">
            ${stemic_control.hero(s.ready ? "green" : "orange", s.ready ? "check" : "triangle-alert",
                s.ready ? __("Ready") : __("{0} thing(s) need attention", [problems]),
                s.ready ? __("This control plane can provision, license and bill schools.") : __("Fix the items marked below, then use Re-check Setup."))}
            ${areas.map((area) => `<div class="scx-tile">
                <span>${esc(__(area))}</span>
                ${s.items.filter((i) => i.area === area).map((i) => {
                    const [icon, color] = mark(i.ok);
                    return `<div style="display:flex;gap:10px;align-items:flex-start;margin-top:8px">
                        <span style="flex:none;color:var(--${color}-500)">${frappe.utils.icon(icon, "sm")}</span>
                        <div><b style="font-size:var(--text-sm)">${esc(__(i.label))}</b>
                            <small style="display:block">${esc(i.detail || "")}</small>
                            ${i.fix ? `<small style="display:block;color:var(--${color}-600)">${esc(i.fix)}</small>` : ""}</div></div>`;
                }).join("")}</div>`).join("")}
        </div>`);
        // A value set in site_config.json wins over this screen: show it read-only and say why
        for (const [field, key] of Object.entries(STEMIC_SERVER_KEYS)) {
            const fromServer = s.sources[key] === "site_config";
            frm.set_df_property(field, "read_only", fromServer ? 1 : 0);
            const df = frappe.meta.get_docfield("Stemic Settings", field, frm.doc.name);
            const base = (df._base_description = df._base_description ?? (df.description || ""));
            frm.set_df_property(field, "description", fromServer
                ? `${base} <b>${__("Set on the server (site_config.json: {0}); change it there.", [key])}</b>` : base);
        }
    });
}

// Stemic Settings > Check Domains: can schools live on each platform domain? (wildcard DNS, certificate on the server)
function check_platform_domains() {
    const esc = frappe.utils.escape_html;
    frappe.call({ method: "stemic_control.domains.platform_domain_health", type: "GET", freeze: true,
        freeze_message: __("Checking each domain...") }).then(({ message: rows }) => {
        const colour = { ready: "var(--green-600)", no_dns: "var(--red-600)", no_certificate: "var(--red-600)",
            no_connection: "var(--orange-600)", unexpected: "var(--orange-600)" };
        const body = rows.map((r) => `<tr>
            <td style="padding:6px 8px;white-space:nowrap"><b>${esc(r.domain)}</b>${r.default ? ` <span class="text-muted">(${__("default")})</span>` : ""}
                <div class="text-muted small">${r.offered ? __("Offered for new schools") : __("Not offered")} · ${__("{0} school(s)", [r.schools])}</div></td>
            <td style="padding:6px 8px;color:${colour[r.state]}">${esc(r.message)}</td></tr>`).join("");
        frappe.msgprint({ title: __("Platform domains"), wide: true,
            message: `<table style="width:100%">${body}</table>` });
    });
}
