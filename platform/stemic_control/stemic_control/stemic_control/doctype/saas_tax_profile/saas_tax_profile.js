// A school's KRA registration: what it still needs before tax invoices can be prepared for it
const KRA_PIN = /^[AP][0-9]{9}[A-Z]$/;

frappe.ui.form.on("SaaS Tax Profile", {
    setup(frm) {
        // one profile per school: offer only schools that have none yet
        frm.set_query("tenant", () => ({ filters: { name: ["not in", frm._schools_with_profiles || []] } }));
    },
    onload(frm) {
        if (!frm.is_new()) return;
        frappe.db.get_list("SaaS Tax Profile", { pluck: "name", limit: 0 }).then((names) => { frm._schools_with_profiles = names; });
    },
    refresh(frm) {
        const ready = frm.doc.enabled && !frm.is_new();
        frm.page.set_indicator(frm.is_new() ? __("Not Saved") : ready ? __("Ready") : __("Draft"), ready ? "green" : "orange");
        if (frm.doc.tenant && !frm.is_new()) {
            frm.add_custom_button(__("School"), () => frappe.set_route("Form", "SaaS Tenant", frm.doc.tenant), __("View"));
            frm.add_custom_button(__("Tax Invoices"), () => frappe.set_route("List", "SaaS eTIMS Invoice", { tenant: frm.doc.tenant }), __("View"));
        }
        render_readiness(frm);
    },
    tenant: render_readiness,
    branch_id: render_readiness,
    enabled: render_readiness,
    seller_pin(frm) {
        const pin = (frm.doc.seller_pin || "").toUpperCase().replace(/\s+/g, "");
        if (pin !== frm.doc.seller_pin) return frm.set_value("seller_pin", pin);  // runs this handler again
        render_readiness(frm);
    },
});

function render_readiness(frm) {
    const d = frm.doc, esc = frappe.utils.escape_html;
    const pin = d.seller_pin || "";
    const school = d.tenant ? frappe.utils.get_link_title("SaaS Tenant", d.tenant) || d.tenant : "";
    // each step: state (done / problem / todo), title, what it says now
    const steps = [
        [d.tenant ? "done" : "todo", __("School"), d.tenant ? esc(school) : __("Pick the school this registration belongs to")],
        [!pin ? "todo" : KRA_PIN.test(pin) ? "done" : "problem", __("KRA PIN"), !pin ? __("Not entered yet; a draft can be saved without it")
            : KRA_PIN.test(pin) ? esc(pin) : __("{0} is not a KRA PIN: P or A, nine digits, then a letter", [esc(pin)])],
        [(d.branch_id || "").trim() ? "done" : "todo", __("Branch ID"), d.branch_id ? esc(d.branch_id) : __("Usually 00 for the head office")],
        [d.enabled ? "done" : "todo", __("Ready for tax invoices"), d.enabled ? __("Tax invoices can be prepared for this school")
            : __("Tick it once the PIN and branch are confirmed")],
    ];
    const look = { done: ["✓", "var(--green-100)", "var(--green-700)"], problem: ["!", "var(--red-100)", "var(--red-600)"],
                   todo: ["", "var(--gray-100)", "var(--gray-500)"] };
    const done = steps.filter(([state]) => state === "done").length;
    const cells = steps.map(([state, title, detail], i) => {
        const [mark, bg, fg] = look[state];
        return `<div style="display:flex;gap:10px;align-items:flex-start;min-width:0">
            <span style="flex:none;width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
                         font-size:12px;font-weight:600;background:${bg};color:${fg}">${mark || i + 1}</span>
            <span style="min-width:0"><span style="font-weight:600">${title}</span><br>
                <span class="small" style="color:${state === "problem" ? "var(--red-600)" : "var(--text-muted)"}">${detail}</span></span>
        </div>`;
    }).join("");
    frm.get_field("readiness_html").$wrapper.html(`
        <div style="border:1px solid var(--border-color);border-radius:var(--border-radius-md);padding:12px 16px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:10px">
                <span style="font-weight:600">${done === steps.length ? __("Ready for tax invoices") : __("Getting this school ready for eTIMS")}</span>
                <span class="text-muted small" style="white-space:nowrap">${__("{0} of {1}", [done, steps.length])}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px 20px">${cells}</div>
            <div class="text-muted small" style="margin-top:10px">${__("Nothing is sent to KRA from here: tax invoices are prepared and reviewed first.")}</div>
        </div>`);
}
