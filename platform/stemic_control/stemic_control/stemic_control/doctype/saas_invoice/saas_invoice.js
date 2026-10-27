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
        if (frm.doc.docstatus === 1 && frm.doc.status !== "Cancelled" && stemic_control.is_platform_admin()) etims_button(frm);
        if (!frm.is_new()) {
            frm.add_custom_button(__("Payments"), () => frappe.set_route("List", "SaaS Payment", { invoice: frm.doc.name }), __("View"));
            frm.add_custom_button(__("Subscription"), () => frappe.set_route("Form", "SaaS Subscription", frm.doc.subscription), __("View"));
        }
        render_summary(frm);
    },
    subscription(frm) {
        if (frm.doc.subscription) frappe.db.get_value("SaaS Subscription", frm.doc.subscription, "tenant").then(({ message }) => frm.set_value("tenant", message.tenant));
    },
});

// Stemic's tax invoice for KRA is prepared from this invoice (never from typed amounts): open it, or prepare it
function etims_button(frm) {
    frappe.db.get_value("Stemic Tax Settings", "Stemic Tax Settings", "enabled").then(({ message }) => {
        if (!message || !cint(message.enabled)) return;
        frappe.db.get_value("SaaS eTIMS Invoice", { saas_invoice: frm.doc.name }, ["name", "status"]).then(({ message: tax }) => {
            if (tax && tax.name) {
                frm.add_custom_button(__("Tax Invoice ({0})", [__(tax.status)]), () => frappe.set_route("Form", "SaaS eTIMS Invoice", tax.name), __("View"));
            } else {
                frm.add_custom_button(__("Prepare eTIMS"), () => frappe.confirm(
                    __("Prepare Stemic's tax invoice for {0}? Amounts, buyer and period are taken from this invoice.", [frm.doc.name]),
                    () => frappe.call({ method: "stemic_control.etims.prepare_from_saas_invoice", args: { invoice: frm.doc.name }, freeze: true })
                        .then(({ message: r }) => frappe.set_route("Form", "SaaS eTIMS Invoice", r.name))), __("Billing"));
            }
        });
    });
}

// The card at the top: what is owed and by when, how far it is paid, the period it covers and the payments so far
function render_summary(frm) {
    const $box = frm.get_field("summary_html").$wrapper;
    if (frm.is_new()) return $box.empty();
    const d = frm.doc, esc = frappe.utils.escape_html, money = stemic_control.money, day = (x) => frappe.datetime.str_to_user(x);
    const total = flt(d.total), paid = flt(d.paid_amount), owed = flt(d.outstanding);
    const share = total > 0 ? Math.min(100, Math.round((paid / total) * 100)) : 0;
    const left = d.due_date ? frappe.datetime.get_diff(d.due_date, frappe.datetime.get_today()) : null;
    const tone = { Paid: "green", Overdue: "red", Cancelled: "gray", Draft: "gray" }[d.status] || "orange";

    // the one line that says where this invoice stands
    const headline = d.docstatus === 0 ? __("Draft: submit it to send it to the school")
        : d.docstatus === 2 ? __("Cancelled")
        : owed <= 0 ? __("Paid in full")
        : d.status === "Overdue" ? __("{0} overdue by {1} days", [money(owed), Math.abs(left)])
        : left === 0 ? __("{0} due today", [money(owed)])
        : __("{0} due in {1} days", [money(owed), left]);

    const fact = (label, value) => `<div style="min-width:0"><div class="text-muted small">${label}</div>
        <div style="font-weight:600;overflow-wrap:anywhere">${value}</div></div>`;
    $box.html(`
        <div class="saas-invoice-summary" style="border:1px solid var(--border-color);border-radius:var(--border-radius-md);padding:14px 16px;margin-bottom:8px">
            <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 16px;align-items:baseline">
                <div style="font-size:var(--text-lg);font-weight:600;color:var(--${tone === "gray" ? "text-color" : tone + "-600"})">${headline}</div>
                <div class="text-muted small">${__("Due {0}", [day(d.due_date)])}</div>
            </div>
            ${d.docstatus === 1 ? `
            <div style="margin:12px 0 6px;height:8px;border-radius:4px;background:var(--gray-100);overflow:hidden"
                 role="progressbar" aria-valuenow="${share}" aria-valuemin="0" aria-valuemax="100" aria-label="${__("Paid")}">
                <div style="height:100%;width:${share}%;background:var(--${share >= 100 ? "green" : "blue"}-500)"></div>
            </div>
            <div class="text-muted small">${__("{0} of {1} paid ({2}%)", [money(paid), money(total), share])}</div>` : ""}
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px 20px;margin-top:14px">
                ${fact(__("Total"), money(total))}
                ${fact(__("Still owed"), money(d.docstatus === 1 ? owed : total))}
                ${fact(__("Period"), `${day(d.period_start)} – ${day(d.period_end)}`)}
                ${fact(__("Plan"), `${esc(d.plan || "")}${d.months ? ` · ${__("{0} months", [d.months])}` : ""}`)}
            </div>
            <div class="saas-invoice-payments" style="margin-top:14px"></div>
        </div>`);
    if (d.docstatus !== 0) load_payments(frm, $box.find(".saas-invoice-payments"));
}

function load_payments(frm, $list) {
    const esc = frappe.utils.escape_html, money = stemic_control.money;
    frappe.db.get_list("SaaS Payment", {
        filters: { invoice: frm.doc.name, docstatus: ["!=", 0] },
        fields: ["name", "payment_date", "mode", "reference", "amount", "docstatus"], order_by: "payment_date desc, creation desc", limit: 50,
    }).then((rows) => {
        if (!rows.length) return $list.html(`<div class="text-muted small">${__("No payments recorded yet.")}</div>`);
        $list.html(`<div class="text-muted small" style="margin-bottom:4px">${__("Payments")}</div>` + rows.map((p) => `
            <a href="/app/saas-payment/${encodeURIComponent(p.name)}" style="display:flex;flex-wrap:wrap;gap:4px 12px;justify-content:space-between;
               padding:6px 0;border-top:1px solid var(--border-color);color:inherit;text-decoration:none;${p.docstatus === 2 ? "opacity:.55" : ""}">
                <span>${frappe.datetime.str_to_user(p.payment_date)} · ${esc(__(p.mode || ""))}${p.reference ? ` · <code>${esc(p.reference)}</code>` : ""}</span>
                <span style="font-weight:600;${p.docstatus === 2 ? "text-decoration:line-through" : ""}">${money(p.amount)}${p.docstatus === 2 ? ` · ${__("cancelled")}` : ""}</span>
            </a>`).join(""));
    });
}
