frappe.ui.form.on("SaaS Plan", {
    refresh(frm) {
        frm.page.set_indicator(frm.doc.enabled ? __("Enabled") : __("Disabled"), frm.doc.enabled ? "green" : "gray");
        render_modules(frm);
        render_plan_summary(frm);
        if (!frm.is_new()) {
            frm.add_custom_button(__("Subscriptions"), () => frappe.set_route("List", "SaaS Subscription", { plan: frm.doc.name }), __("View"));
        }
    },
    monthly_price: render_plan_summary,
    student_limit: render_plan_summary,
});

function plan_codes(frm) {
    try {
        return JSON.parse(frm.doc.modules || "[]");
    } catch (e) {
        return [];
    }
}

function render_modules(frm) {
    const $w = frm.get_field("modules_html").$wrapper;
    frappe.call({ method: "stemic_control.api.plan_catalogue", type: "GET" }).then(({ message: catalogue }) => {
        const on = new Set(plan_codes(frm));
        const esc = frappe.utils.escape_html;
        $w.html(`<div class="scx">
            <div class="scx-h">${__("Tick what schools on this plan get")}<span class="scx-count"></span></div>
            <div class="scx-mods">
                <label class="scx-mod on locked"><input type="checkbox" checked disabled>
                    <div><b>${__("Core")}</b><small>${__("Students, classes, streams, teachers, years and terms. Always included.")}</small></div></label>
                ${catalogue.map((m) => `<label class="scx-mod ${on.has(m.code) ? "on" : ""}">
                    <input type="checkbox" data-code="${esc(m.code)}" ${on.has(m.code) ? "checked" : ""}>
                    <div><b>${esc(__(m.label))}</b><small>${esc(stemic_control.MODULE_HELP[m.code] || "")}</small></div></label>`).join("")}
            </div>
            <div class="text-muted small">${__("Changes reach a school the next time its license is issued.")}</div></div>`);
        const count = () => $w.find(".scx-count").text(__("{0} of {1} modules", [$w.find("input[data-code]:checked").length, catalogue.length]));
        count();
        $w.find("input[data-code]").on("change", function () {
            $(this).closest(".scx-mod").toggleClass("on", this.checked);
            const picked = $w.find("input[data-code]:checked").map((_, el) => el.dataset.code).get();
            frm.set_value("modules", JSON.stringify(picked));
            count();
            render_plan_summary(frm);
        });
    });
}

function render_plan_summary(frm) {
    const $w = frm.get_field("summary_html").$wrapper;
    const n = plan_codes(frm).length;
    const limit = frm.doc.student_limit ? __("Up to {0} students", [frm.doc.student_limit]) : __("Any number of students");
    const tiles = (s) => `<div class="scx-row">
        ${stemic_control.tile(__("Price"), stemic_control.money(frm.doc.monthly_price), __("per school, per month"))}
        ${stemic_control.tile(__("Includes"), __("Core + {0} modules", [n]), limit)}
        ${s ? stemic_control.tile(__("Schools on this plan"), s.total,
              ["Active", "Trial", "Past Due", "Grace", "Suspended"].filter((k) => s.by_status[k]).map((k) => `${s.by_status[k]} ${__(k)}`).join(" · ") || __("None yet")) : ""}
        ${s ? stemic_control.tile(__("Monthly revenue"), stemic_control.money(s.mrr), __("from Active subscriptions")) : ""}
    </div>`;
    const disabled = !frm.is_new() && !frm.doc.enabled
        ? stemic_control.hero("gray", "eye-off", __("Disabled"), __("New subscriptions cannot pick this plan. Schools already on it keep it until they renew onto another plan.")) : "";
    if (frm.is_new()) return $w.html(`<div class="scx">${tiles(null)}</div>`);
    frappe.call({ method: "stemic_control.api.plan_summary", args: { plan: frm.doc.name }, type: "GET" })
        .then(({ message: s }) => $w.html(`<div class="scx">${disabled}${tiles(s)}</div>`));
}
