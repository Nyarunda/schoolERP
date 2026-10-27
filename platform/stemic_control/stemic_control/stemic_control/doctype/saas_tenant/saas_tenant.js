const TENANT_COLORS_FORM = { Draft: "gray", "Pending Approval": "yellow", Approved: "cyan", Rejected: "red", Pending: "orange", Provisioning: "blue", Active: "green", Suspended: "red", Failed: "red" };

frappe.ui.form.on("SaaS Tenant", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.page.set_indicator(__(frm.doc.status), TENANT_COLORS_FORM[frm.doc.status] || "gray");
        if (frm.doc.canonical_site) frm.add_custom_button(__("Open Site"), () => open_site(frm));
        show_progress(frm);
        render_overview(frm);
        // Manual fallbacks for the automated provisioner
        if (frm.doc.status === "Pending") {
            frm.add_custom_button(__("Provision Now"), () =>
                frappe.call({ method: "stemic_control.api.provision_tenant_now", args: { tenant: frm.doc.name } }).then(() => {
                    frappe.show_alert({ message: __("Handed to the provisioner"), indicator: "blue" });
                    setTimeout(() => frm.reload_doc(), 4000);
                }), __("Actions"));
        }
        approval_actions(frm);
        if (["Approved", "Failed"].includes(frm.doc.status) && frm.doc.approved_on) {
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

// Draft -> Pending Approval -> Approved: who may move the school on, and why it cannot be provisioned yet
function approval_actions(frm) {
    const act = (label, method, args, message) => frm.add_custom_button(label, () =>
        frappe.call({ method: `stemic_control.onboarding.${method}`, args: { tenant: frm.doc.name, ...args }, freeze: true })
            .then(() => { frappe.show_alert({ message, indicator: "green" }); frm.reload_doc(); }), __("Approval"));
    const ask = (label, method, field, message) => frm.add_custom_button(label, () =>
        frappe.prompt({ fieldname: field, fieldtype: "Small Text", label: field === "reason" ? __("Reason") : __("Note"),
                        reqd: field === "reason" }, (values) =>
            frappe.call({ method: `stemic_control.onboarding.${method}`, args: { tenant: frm.doc.name, ...values }, freeze: true })
                .then(() => { frappe.show_alert({ message, indicator: "green" }); frm.reload_doc(); }), label), __("Approval"));
    if (frm.doc.status === "Draft" || (frm.doc.status === "Failed" && !frm.doc.approved_on)) {
        act(__("Submit for Approval"), "submit_for_approval", {}, __("Sent for approval"));
    }
    if (frm.doc.status === "Pending Approval") ask(__("Approve"), "approve_tenant", "note", __("Approved"));
    if (["Pending Approval", "Approved", "Failed"].includes(frm.doc.status)) ask(__("Reject"), "reject_tenant", "reason", __("Rejected"));
}

// Pending / Provisioning: refresh until it settles (the overview card says what is happening)
function show_progress(frm) {
    clearTimeout(frm._stemic_poll);
    if (["Pending", "Provisioning"].includes(frm.doc.status)) {
        frm._stemic_poll = setTimeout(() => {
            if (frappe.get_route()[0] === "Form" && cur_frm === frm && !frm.is_dirty()) frm.reload_doc();
        }, 15000);
    }
}

// The card at the top: where the school is on its way to a live site, what to do next, and what it has
const STAGES = [["Draft", __("Registered")], ["Pending Approval", __("Approval")], ["Approved", __("Approved")],
                ["Provisioning", __("Site")], ["Active", __("Live")]];
const STAGE_OF = { Draft: 0, "Pending Approval": 1, Approved: 2, Rejected: 1, Pending: 3, Provisioning: 3, Failed: 3, Active: 4, Suspended: 4 };

async function render_overview(frm) {
    const $box = frm.get_field("overview_html").$wrapper;
    if (frm.is_new()) return $box.empty();
    const d = frm.doc, esc = frappe.utils.escape_html, day = (x) => (x ? frappe.datetime.str_to_user(x) : "");
    const [ready, sub, job, domains] = await Promise.all([
        ["Draft", "Pending Approval", "Approved", "Pending", "Failed"].includes(d.status)
            ? frappe.xcall("stemic_control.onboarding.status", { tenant: d.name }, "GET").catch(() => null) : null,
        d.subscription ? frappe.db.get_value("SaaS Subscription", d.subscription, ["plan", "status", "ends_on", "billing_exception"])
            .then((r) => r.message) : null,
        frappe.db.get_list("SaaS Provisioning Job", { filters: { tenant: d.name }, fields: ["name", "status", "attempts", "last_error", "modified"],
                                                      order_by: "creation desc", limit: 1 }).then((r) => r[0]),
        frappe.db.get_list("SaaS Domain", { filters: { tenant: d.name }, fields: ["name", "status"], limit: 10 }),
    ]);
    if (frm.doc.name !== d.name) return;  // moved to another school meanwhile
    const problems = ready ? [...ready.problems, ...(ready.environment_problem ? [ready.environment_problem] : [])] : [];

    // the next step, in one line, and its tone
    const failed_reason = job && job.status === "Failed" ? (job.last_error || "").split("\n").find((l) => l.trim()) || "" : "";
    const next = {
        Draft: [__("Send it for approval when the school's details are checked"), "gray"],
        "Pending Approval": [__("Waiting for a platform admin to approve or reject it"), "orange"],
        Approved: problems.length ? [__("Approved, but not ready to provision yet"), "orange"] : [__("Ready: queue the site from Actions"), "green"],
        Rejected: [__("Rejected. Move it back to Draft to start again"), "red"],
        Pending: problems.length ? [__("A site job is queued, but the provisioner will refuse it"), "orange"]
            : [__("Waiting for the provisioner to pick up the site job. This page refreshes by itself"), "blue"],
        Provisioning: [__("Creating the site (database, ERPNext and School ERP). Usually 3 to 8 minutes"), "blue"],
        Failed: [d.approved_on ? __("The site could not be created. Fix the cause, then Actions > Retry Provisioning")
            : __("The site could not be created, and the school has no approval: send it for approval first"), "red"],
        Active: [d.canonical_site ? __("Live at {0}", [esc(d.primary_domain || d.canonical_site)]) : __("Live"), "green"],
        Suspended: [__("Suspended: the school cannot use its site. Resume it from Actions"), "red"],
    }[d.status] || [esc(d.status), "gray"];

    const at = STAGE_OF[d.status] ?? 0, broken = ["Rejected", "Failed", "Suspended"].includes(d.status);
    // approval steps count as done only with a recorded approval (schools live before approvals existed excepted)
    const approved = !!d.approved_on || ["Active", "Suspended"].includes(d.status);
    const steps = STAGES.map(([, label], i) => {
        let state = i < at || (i === at && d.status === "Active") ? "done" : i === at ? (broken ? "bad" : "now") : "todo";
        if (state === "done" && (i === 1 || i === 2) && !approved) state = "todo";
        const [bg, fg] = { done: ["var(--green-500)", "#fff"], now: ["var(--blue-500)", "#fff"], bad: ["var(--red-500)", "#fff"],
                           todo: ["var(--gray-200)", "var(--gray-600)"] }[state];
        return `<div style="flex:1;min-width:0;text-align:center">
            <div style="display:flex;align-items:center">
                <span style="flex:1;height:2px;background:${i === 0 ? "transparent" : i <= at && (approved || i === 1) ? "var(--green-500)" : "var(--gray-200)"}"></span>
                <span style="flex:none;width:22px;height:22px;border-radius:50%;background:${bg};color:${fg};font-size:11px;font-weight:600;
                             display:inline-flex;align-items:center;justify-content:center">${state === "done" ? "✓" : state === "bad" ? "!" : i + 1}</span>
                <span style="flex:1;height:2px;background:${i === STAGES.length - 1 ? "transparent" : i < at && (approved || i === 0) ? "var(--green-500)" : "var(--gray-200)"}"></span>
            </div>
            <div style="margin-top:4px;font-size:11.5px;line-height:1.25;overflow-wrap:anywhere;color:${state === "todo" ? "var(--text-muted)" : "var(--text-color)"};
                 font-weight:${state === "now" || state === "bad" ? 600 : 400}">
                ${state === "bad" ? __(d.status) : label}</div>
        </div>`;
    }).join("");

    const fact = (label, value) => `<div style="min-width:0"><div class="text-muted small">${label}</div>
        <div style="font-weight:600;overflow-wrap:anywhere">${value}</div></div>`;
    const sub_text = sub ? `${esc(sub.plan)} · ${__(sub.status)}${sub.ends_on ? ` · ${__("to {0}", [day(sub.ends_on)])}` : ""}`
        + (sub.billing_exception ? ` · ${__(sub.billing_exception)}` : "") : `<span class="text-muted">${__("None yet")}</span>`;
    const live_domains = domains.filter((x) => x.status === "Active").length;
    const list = (items, tone) => `<ul style="margin:6px 0 0;padding-left:18px;color:var(--${tone}-600)">${items.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;

    $box.html(`
        <div style="border:1px solid var(--border-color);border-radius:var(--border-radius-md);padding:14px 16px;margin-bottom:8px">
            <div style="display:flex;gap:4px;margin-bottom:12px" aria-label="${__("Onboarding progress")}">${steps}</div>
            <div style="font-weight:600;color:var(--${next[1] === "gray" ? "text-color" : next[1] + "-600"})">${next[0]}</div>
            ${problems.length && d.status !== "Draft" ? list(problems, "orange") : ""}
            ${failed_reason && d.status === "Failed" ? `<div class="small" style="margin-top:6px;color:var(--red-600)">
                ${esc(job.name)}${job.attempts ? ` · ${__("{0} attempt(s)", [job.attempts])}` : ""}: ${esc(failed_reason.slice(0, 200))}</div>` : ""}
            ${d.status === "Rejected" && d.approval_note ? `<div class="small text-muted" style="margin-top:6px">${__("Reason")}: ${esc(d.approval_note)}</div>` : ""}
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px 20px;margin-top:14px">
                ${fact(__("Subscription"), sub_text)}
                ${fact(__("Site"), d.canonical_site ? esc(d.canonical_site) : `<span class="text-muted">${__("Not created")}</span>`)}
                ${fact(__("Domains"), domains.length ? __("{0} of {1} live", [live_domains, domains.length]) : `<span class="text-muted">${__("None claimed")}</span>`)}
                ${fact(__("Sales agent"), d.agent ? esc(frappe.utils.get_link_title("SaaS Agent", d.agent) || d.agent) : `<span class="text-muted">${__("Direct")}</span>`)}
            </div>
            ${d.approved_on ? `<div class="small text-muted" style="margin-top:10px">${__("Approved by {0} on {1}", [esc(d.approved_by), day(d.approved_on)])}</div>` : ""}
        </div>`);
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
