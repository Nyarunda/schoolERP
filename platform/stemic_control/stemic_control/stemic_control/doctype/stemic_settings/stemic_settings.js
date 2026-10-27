// Settings fields that site_config.json can override (stemic_control.config.SETTINGS)
const STEMIC_SERVER_KEYS = {
    platform_domain: "stemic_platform_domain", site_domain: "stemic_site_domain", site_apps: "stemic_site_apps",
    bench_path: "stemic_bench_path", local_provisioner: "stemic_local_provisioner", dns_over_https: "stemic_dns_over_https",
};

frappe.ui.form.on("Stemic Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Re-check Setup"), () => render_setup(frm));
        render_setup(frm);
    },
    after_save: render_setup,
});

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
