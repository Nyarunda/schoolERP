// A school with several branches (each its own site): branches, what each owes, one statement, one payment.
frappe.ui.form.on("SaaS School Group", {
    refresh(frm) {
        if (frm.is_new()) return;
        const esc = frappe.utils.escape_html, money = (v) => format_currency(v, "KES");
        frm.add_custom_button(__("Add Branch"), () => frappe.prompt({ fieldname: "tenant", label: __("School (branch site)"), fieldtype: "Link",
            options: "SaaS Tenant", reqd: 1 }, ({ tenant }) => frappe.db.set_value("SaaS Tenant", tenant, "school_group", frm.doc.name)
            .then(() => frm.reload_doc()), __("Add a branch")));
        frm.add_custom_button(__("New Branch Site"), () => stemic_control.onboard_school && stemic_control.onboard_school());
        frappe.xcall("stemic_control.groups.group_overview", { group: frm.doc.name }, "GET").then((g) => {
            const rows = g.branches.map((b) => `<tr><td><a href="${frappe.utils.get_form_link("SaaS Tenant", b.name)}">${esc(b.school_name)}</a>
                ${b.branch_name ? `<small class="text-muted"> ${esc(b.branch_name)}</small>` : ""}</td><td>${esc(b.canonical_site || "—")}</td>
                <td>${esc(__(b.status))}</td><td>${esc(b.plan || "—")}</td><td class="text-right">${money(b.owed)}</td></tr>`).join("");
            frm.get_field("branches_html").$wrapper.html(g.branches.length
                ? `<table class="table table-sm table-bordered"><thead><tr><th>${__("Branch")}</th><th>${__("Site")}</th><th>${__("Status")}</th>
                    <th>${__("Plan")}</th><th class="text-right">${__("Owes")}</th></tr></thead><tbody>${rows}</tbody>
                    <tfoot><tr><th colspan="4">${__("Group total")}</th><th class="text-right">${money(g.owed)}</th></tr></tfoot></table>`
                : `<p class="text-muted">${__("No branches yet: Add Branch links an existing school; New Branch Site onboards one.")}</p>`);
            if (!g.invoices.length) return;
            frm.add_custom_button(__("Email Statement"), () => frappe.xcall("stemic_control.groups.email_statement", { group: frm.doc.name })
                .then((r) => frappe.show_alert({ message: __("Statement of {0} sent to {1}", [money(r.total), r.sent_to]), indicator: "green" })), __("Billing"));
            frm.add_custom_button(__("Record Group Payment"), () => frappe.prompt([
                { fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1, default: g.owed },
                { fieldname: "mode", label: __("Mode"), fieldtype: "Select", options: "M-Pesa\nBank Transfer\nCheque\nCash\nCard\nOther", default: "M-Pesa", reqd: 1 },
                { fieldname: "reference", label: __("Reference"), fieldtype: "Data", reqd: 1 },
                { fieldname: "payment_date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
            ], (v) => frappe.xcall("stemic_control.groups.record_group_payment", { group: frm.doc.name, ...v }).then((r) => {
                frappe.msgprint({ title: __("Payment recorded"), indicator: "green", message: r.allocated.map((a) =>
                    `${esc(a.invoice)}: ${money(a.amount)}`).join("<br>") });
                frm.reload_doc();
            }), __("Record a payment for the whole group ({0} owed)", [money(g.owed)]), __("Record")), __("Billing"));
        });
    },
});
