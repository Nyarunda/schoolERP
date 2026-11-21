const TENANT_COLORS_FORM = { Draft: "gray", "Pending Approval": "yellow", Approved: "cyan", Rejected: "red", Pending: "orange", Provisioning: "blue", Active: "green", Suspended: "red", Failed: "red" };

frappe.ui.form.on("SaaS Tenant", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.page.set_indicator(__(frm.doc.status), TENANT_COLORS_FORM[frm.doc.status] || "gray");
        if (frm.doc.canonical_site) frm.add_custom_button(__("Open Site"), () => open_site(frm));
        if (frm.doc.canonical_site) frm.add_custom_button(__("Backups"), () => school_backups(frm));
        if (frm.doc.status !== "Deleted" && stemic_control.is_platform_admin()) school_deletion_buttons(frm);
        if (frm.doc.canonical_site && frm.doc.status === "Active") frm.add_custom_button(__("Send Welcome Email"), () =>
            frappe.confirm(__("Email {0} the school's address and a new link to set their password?", [frappe.utils.escape_html(frm.doc.admin_email || "")]), () =>
                frappe.call({ method: "stemic_control.welcome.resend", args: { tenant: frm.doc.name }, freeze: true,
                    freeze_message: __("Sending...") }).then(({ message: r }) => {
                    frappe.show_alert({ message: __("Welcome email sent to {0}", [r.to]), indicator: "green" });
                    frm.reload_doc();
                })), __("Actions"));
        show_progress(frm);
        render_overview(frm);
        // Manual fallbacks for the automated provisioner
        if (frm.doc.status === "Pending") {
            frm.add_custom_button(__("Provision Now"), () =>
                frappe.call({ method: "stemic_control.api.provision_tenant_now", args: { tenant: frm.doc.name } })
                    .then(() => provisioning_dialog(frm)), __("Actions"));
        }
        approval_actions(frm);
        if (["Approved", "Failed"].includes(frm.doc.status) && frm.doc.approved_on) {
            frm.add_custom_button(frm.doc.status === "Failed" ? __("Retry Provisioning") : __("Queue Provisioning"), () =>
                frappe.call({
                    method: "stemic_control.api.queue_provisioning",
                    args: { tenant: frm.doc.name, request_key: `${frm.doc.name}-${Date.now()}` },
                    freeze: true,
                }).then(() => provisioning_dialog(frm)), __("Actions"));
        }
        if (["Approved", "Failed"].includes(frm.doc.status) && frm.doc.approved_on && !frm.doc.canonical_site) {
            frm.add_custom_button(__("Link Existing Site"), () => link_existing_site(frm), __("Actions"));
        }
        frm.add_custom_button(__("Claim a Domain"), () => stemic_control.claim_domain(frm.doc.name), __("Actions"));
        if (["Active", "Suspended"].includes(frm.doc.status)) {
            const next = frm.doc.status === "Active" ? "Suspended" : "Active";
            const change = (reason) => frappe.call({ method: "stemic_control.api.set_tenant_status", freeze: true,
                args: { tenant: frm.doc.name, status: next, reason }, freeze_message: next === "Suspended" ? __("Suspending...") : __("Resuming...") })
                .then(() => frm.reload_doc());
            frm.add_custom_button(next === "Suspended" ? __("Suspend") : __("Resume"), () => next === "Suspended"
                ? frappe.prompt([
                    { fieldname: "why", fieldtype: "Select", label: __("Reason shown to the school"), default: "Unpaid invoice",
                      options: ["Unpaid invoice", "Requested by the school", "Breach of the terms of service", "Other", "(Do not say)"].join("\n") },
                    { fieldname: "note", fieldtype: "Small Text", label: __("Note for the school (optional)"),
                      description: __("Shown on the school's suspended page, e.g. what to do to restore the service.") },
                ], ({ why, note }) => change([why === "(Do not say)" ? "" : why, note].filter(Boolean).join(". ")),
                __("Suspend {0}?", [frm.doc.school_name]), __("Suspend"))
                : frappe.confirm(__("Resume {0}? Its site opens again at once.", [frm.doc.school_name]), () => change()), __("Actions"));
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

// After Provision Now / Queue / Retry: say what the provisioner is doing, and what happened or went wrong
function provisioning_dialog(frm) {
    const esc = frappe.utils.escape_html;
    const d = new frappe.ui.Dialog({ title: __("Creating the site for {0}", [frm.doc.school_name]),
                                     fields: [{ fieldname: "info", fieldtype: "HTML" }] });
    const $info = d.fields_dict.info.$wrapper;
    let timer, done = false;
    const stop = () => { clearTimeout(timer); done = true; };
    d.onhide = () => { stop(); frm.reload_doc(); };
    d.show();
    const ago = (from, now) => Math.max(0, Math.round((frappe.datetime.str_to_obj(now) - frappe.datetime.str_to_obj(from)) / 1000));
    const minutes = (s) => (s < 90 ? __("{0} s", [s]) : __("{0} min", [Math.round(s / 60)]));
    const steps = (at, bad) => [__("Queued"), __("Creating the site"), __("Done")].map((label, i) => {
        const state = i < at ? "done" : i === at ? (bad ? "bad" : at === 2 ? "done" : "now") : "todo";
        const [bg, fg] = { done: ["var(--green-500)", "#fff"], now: ["var(--blue-500)", "#fff"], bad: ["var(--red-500)", "#fff"],
                           todo: ["var(--gray-200)", "var(--gray-600)"] }[state];
        return `<div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0">
            <span style="flex:none;width:22px;height:22px;border-radius:50%;background:${bg};color:${fg};font-size:11px;font-weight:600;
                         display:inline-flex;align-items:center;justify-content:center">${state === "done" ? "✓" : state === "bad" ? "!" : i + 1}</span>
            <span class="small" style="font-weight:${state === "now" || state === "bad" ? 600 : 400}">${label}</span></div>`;
    }).join("");
    const box = (tone, title, body) => `<div style="display:flex;gap:6px;margin-bottom:14px">${body.steps}</div>
        <div style="font-weight:600;color:var(--${tone}-600);margin-bottom:6px">${title}</div>${body.text || ""}`;

    const poll = () => frappe.xcall("stemic_control.api.provisioning_progress", { tenant: frm.doc.name }, "GET").then((p) => {
        if (done) return;
        const j = p.job, more = (s) => `<div class="text-muted small" style="margin-top:6px">${s}</div>`;
        const link = j ? `<a href="/app/saas-provisioning-job/${encodeURIComponent(j.name)}">${esc(j.name)}</a>` : "";
        let html, finished = false;
        if (!j) {
            html = box("gray", __("No site job yet"), { steps: steps(0), text: more(__("Queue Provisioning creates one.")) });
            finished = true;
        } else if (j.status === "Queued") {
            const waited = ago(j.queued_on, p.now);
            // the worker already ran it (its background job ended) yet the site job is still Queued: it never started building
            const passed_over = ["finished", "failed", "stopped", "canceled"].includes(j.worker_job) && waited > 10;
            const stuck = passed_over || (waited > 60 && (p.workers === 0 || !p.local_provisioner));
            html = box(stuck ? "orange" : "blue", stuck ? __("Still waiting for the provisioner") : __("Waiting for the provisioner to pick it up"), {
                steps: steps(0), text: more(__("Job {0}, queued {1} ago.", [link, minutes(waited)]))
                    + (!p.local_provisioner ? more(__("The local provisioner is switched off (stemic_local_provisioner), so an external provisioner must take this job."))
                        : passed_over ? more(__("The provisioner ran it ({0}) but did not start building. Check Error Log, then use Actions > Provision Now.", [esc(j.worker_job)]))
                            : p.workers === 0 ? more(__("No background worker is running, so nothing will pick it up. Start one: {0}", ["<code>bench start</code>"]))
                                : waited > 60 ? more(__("A worker is running but has not taken it yet; it may be busy with another job.")) : ""),
            });
        } else if (j.status === "Running") {
            html = box("blue", __("Creating the site: database, ERPNext and School ERP"), {
                steps: steps(1), text: more(__("Running for {0}. This usually takes 3 to 8 minutes; you can close this and come back.", [minutes(ago(j.updated_on, p.now))]))
                    + more(__("Job {0}{1}", [link, j.environment ? ` · ${esc(j.environment)}` : ""])),
            });
        } else if (j.status === "Succeeded") {
            html = box("green", __("The site is ready"), { steps: steps(2), text: more(__("{0} is live. Open it from Open Site.", [`<b>${esc(p.site || "")}</b>`])) });
            finished = true;
            if (p.site) d.set_primary_action(__("Open Site"), () => { d.hide(); open_site(frm); });
        } else if (j.refused) {
            html = box("red", __("The provisioner refused to build it"), {
                steps: steps(0, true), text: `<ul style="margin:0;padding-left:18px">${j.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`
                    + more(__("Nothing was created. Fix the above, then use Actions > Queue Provisioning. Job {0}.", [link])),
            });
            finished = true;
        } else {
            html = box("red", __("Creating the site failed"), {
                steps: steps(1, true), text: (j.error ? `<div style="color:var(--red-600)">${esc(j.error)}</div>` : "")
                    + (j.cleanup ? more(esc(j.cleanup)) : "")
                    + more(__("The full error is on job {0}; fix it, then use Actions > Retry Provisioning.", [link])),
            });
            finished = true;
        }
        $info.html(html);
        if (finished) stop(); else timer = setTimeout(poll, 3000);
    }).catch(() => { $info.html(`<div style="color:var(--red-600)">${__("Could not read the provisioning status.")}</div>`); stop(); });
    poll();
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

// The school's site as it is running now: where it answers, its database, apps, use, backups and the commands for it
function open_site(frm) {
    const esc = frappe.utils.escape_html, site = frm.doc.canonical_site;
    const d = new frappe.ui.Dialog({ title: __("{0}: site", [frm.doc.school_name]), size: "large",
                                     fields: [{ fieldname: "info", fieldtype: "HTML" }] });
    const $info = d.fields_dict.info.$wrapper.html(`<div class="text-muted">${__("Checking {0}…", [esc(site)])}</div>`);
    d.show();
    frappe.xcall("stemic_control.site_runtime.site_status", { tenant: frm.doc.name }, "GET").then((s) => {
        const live = s.served_at || [], db = s.database || {};
        const fallback = /\.localhost$/.test(site) ? null : `https://${frm.doc.primary_domain || site}`;
        const url = live.length ? live[0].url : fallback;
        if (url) d.set_primary_action(__("Open in Browser"), () => window.open(url));
        d.set_secondary_action_label(__("Show Password"));
        d.set_secondary_action(() => frappe.call({ method: "stemic_control.api.site_access", args: { tenant: frm.doc.name } })
            .then(({ message }) => $info.find(".sc-pass").text(message.password || __("(not stored)"))));

        const row = (label, value) => `<div style="display:flex;gap:12px;padding:5px 0;border-top:1px solid var(--border-color)">
            <div class="text-muted" style="flex:0 0 130px">${label}</div><div style="min-width:0;overflow-wrap:anywhere">${value}</div></div>`;
        const section = (title, rows) => `<div style="margin-top:16px"><div style="font-weight:600;margin-bottom:4px">${title}</div>${rows}</div>`;
        const muted = (text) => `<span class="text-muted">${text}</span>`;
        // action: run it here (a SaaS Site Operation in a background worker) as well as copy it
        const cmd = (label, command, action) => `<div style="margin-top:6px"><div class="text-muted small">${label}</div>
            <div style="display:flex;gap:6px;align-items:center"><code style="flex:1;min-width:0;overflow-x:auto;white-space:nowrap;padding:4px 6px">${esc(command)}</code>
            ${action ? `<button class="btn btn-xs btn-primary sc-run" data-action="${esc(action)}">${__("Run")}</button>` : ""}
            <button class="btn btn-xs btn-default sc-copy" data-copy="${esc(command)}">${__("Copy")}</button></div></div>`;
        const bench = s.bench || "~/frappe-bench", on = `cd ${bench} && bench --site ${site}`;
        const free_port = Math.max(8002, ...(s.servers || []).map((x) => x.port + 1));

        const running = live.length
            ? live.map((x) => row(`<span class="indicator-pill green">${__("Running")}</span>`,
                `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.url)}</a><div class="text-muted small">${esc(__("via {0}", [x.via]))}</div>`)).join("")
            : row(`<span class="indicator-pill red">${__("Not answering")}</span>`, s.on_this_bench
                ? __("No server on this machine answers for it. Start one with the command below.")
                : __("It is not on this bench and did not answer at its public address."));
        let html = section(__("Running"), running) + section(__("Login"), row(__("User"), "Administrator")
            + row(__("Password"), `<code class="sc-pass">••••••••</code> ${muted(__("(Show Password below)"))}`
                + (s.on_this_bench ? ` <button class="btn btn-xs btn-default sc-run" data-action="Reset Admin Password">${__("Reset")}</button>` : "")));
        if (s.on_this_bench) {
            html += section(__("Database"), row(__("Name"), `<code>${esc(db.name || "")}</code>`)
                + (db.error ? row(__("Problem"), `<span style="color:var(--red-600)">${esc(db.error)}</span>`)
                    : row(__("Size"), __("{0} MB in {1} tables", [db.size_mb, db.tables]))));
            if (db.apps) html += section(__("Apps"), db.apps.map((a) => row(esc(a.app), `${esc(a.version || "")} ${muted(esc(a.branch || ""))}`)).join(""));
            if (!db.error) html += section(__("Use"), row(__("Users"), db.users ?? "–") + row(__("Students"), db.students ?? "–")
                + row(__("Last login"), db.last_login ? frappe.datetime.str_to_user(db.last_login) : muted(__("Nobody yet"))));
            html += section(__("Health"), row(__("Scheduler"), s.scheduler === "on" ? __("On") : `<span style="color:var(--orange-600)">${__("Paused")}</span>`)
                + row(__("Maintenance"), s.maintenance_mode ? `<span style="color:var(--orange-600)">${__("On: users are locked out")}</span>` : __("Off"))
                + row(__("Last backup"), s.last_backup ? `${esc(s.last_backup.on)} · ${s.last_backup.size_mb} MB` : `<span style="color:var(--orange-600)">${__("None yet")}</span>`)
                + row(__("Folder"), `<code>${esc(s.folder)}</code>`));
            html += section(__("Commands"), (live.length ? "" : cmd(__("Serve it on its own port"), `${on} serve --port ${free_port}`))
                + cmd(__("Console (in a terminal: it is interactive)"), `${on} console`)
                + cmd(__("Back up (with files)"), `${on} backup --with-files`, "Backup")
                + cmd(__("Update after a code change"), `${on} migrate`, "Migrate")
                + cmd(__("Clear cache"), `${on} clear-cache`, "Clear Cache"))
                + `<div class="sc-ops"></div>`;
        }
        $info.html(`<div style="font-size:var(--text-md)"><div style="font-weight:600;font-size:var(--text-lg)">${esc(site)}</div>${html}</div>`);
        $info.find(".sc-copy").on("click", (e) => frappe.utils.copy_to_clipboard($(e.currentTarget).attr("data-copy")));
        $info.find(".sc-run").on("click", (e) => {
            const action = $(e.currentTarget).attr("data-action");
            frappe.confirm(__("Run {0} on {1} now? It runs in the background; you can close this dialog.", [__(action), esc(site)]), () =>
                frappe.xcall("stemic_control.site_runtime.run_operation", { tenant: frm.doc.name, action })
                    .then(() => { frappe.show_alert({ message: __("{0} queued", [__(action)]), indicator: "blue" }); load_operations(frm, d, $info); }));
        });
        if (s.on_this_bench) load_operations(frm, d, $info);
    }).catch(() => $info.html(`<div style="color:var(--red-600)">${__("Could not read the site's status.")}</div>`));
}

// A school ERP site already on this bench (made by hand) given to an approved school instead of building one
function link_existing_site(frm) {
    frappe.xcall("stemic_control.site_runtime.unlinked_sites", {}, "GET").then((sites) => {
        if (!sites.length) return frappe.msgprint(__("There is no School ERP site on this bench that another school is not already using."));
        frappe.prompt([{ fieldname: "site", fieldtype: "Select", label: __("Site"), options: sites, reqd: 1,
                         description: __("It must answer with School ERP installed. Its Administrator password is not known here: reset it afterwards from Open Site.") }],
            ({ site }) => frappe.xcall("stemic_control.site_runtime.link_existing_site", { tenant: frm.doc.name, site })
                .then(() => { frappe.show_alert({ message: __("{0} linked", [site]), indicator: "green" }); frm.reload_doc(); }),
            __("Link an existing site"), __("Link"));
    });
}

// What was run on the site from here, newest first; refreshes while something is queued or running
function load_operations(frm, d, $info) {
    const esc = frappe.utils.escape_html;
    clearTimeout(d._sc_ops);
    frappe.xcall("stemic_control.site_runtime.recent_operations", { tenant: frm.doc.name }, "GET").then((ops) => {
        if (!d.$wrapper.is(":visible")) return;
        const color = { Queued: "gray", Running: "blue", Succeeded: "green", Failed: "red" };
        const busy = ops.some((o) => ["Queued", "Running"].includes(o.status));
        $info.find(".sc-run").prop("disabled", busy);
        $info.find(".sc-ops").html(!ops.length ? "" : `<div style="margin-top:16px"><div style="font-weight:600;margin-bottom:4px">${__("Recent operations")}</div>
            ${ops.map((o) => `<div style="display:flex;gap:12px;padding:5px 0;border-top:1px solid var(--border-color)">
                <div style="flex:0 0 130px"><span class="indicator-pill ${color[o.status] || "gray"}">${__(o.status)}</span></div>
                <div style="min-width:0;overflow-wrap:anywhere"><a href="/app/saas-site-operation/${encodeURIComponent(o.name)}">${esc(__(o.action))}</a>
                    <span class="text-muted small"> · ${esc(frappe.datetime.str_to_user(o.creation))} · ${esc(o.requested_by || "")}</span>
                    ${o.summary ? `<div class="small" style="color:${o.status === "Failed" ? "var(--red-600)" : "var(--text-muted)"}">${esc(o.summary)}</div>` : ""}</div>
            </div>`).join("")}</div>`);
        if (busy) d._sc_ops = setTimeout(() => load_operations(frm, d, $info), 4000);
    });
}

// Backups of this school: list, download, pin, restore (strict: typed site name, safety backup first)
function school_backups(frm) {
    const esc = frappe.utils.escape_html, site = frm.doc.canonical_site;
    const d = new frappe.ui.Dialog({ title: __("Backups of {0}", [site]), size: "extra-large",
        fields: [{ fieldname: "list", fieldtype: "HTML" }],
        primary_action_label: __("Back Up Now"),
        primary_action: () => frappe.xcall("stemic_control.site_runtime.run_operation", { tenant: frm.doc.name, action: "Backup" })
            .then(() => { frappe.show_alert({ message: __("Backup queued: it appears here when it is done"), indicator: "blue" }); }),
    });
    const where = (b) => [b.on_server ? __("This server") : null,
        { Uploaded: __("Off-server"), Pending: __("Off-server: pending"), Failed: __("Off-server: failed") }[b.offsite_status]]
        .filter(Boolean).join(" + ");
    const link = (b, part, label) => `<a href="/api/method/stemic_control.backups.download?backup=${encodeURIComponent(b.name)}&part=${part}" target="_blank" rel="noopener">${label}</a>`;
    const load = () => frappe.xcall("stemic_control.backups.list_backups", { tenant: frm.doc.name }, "GET").then((rows) => {
        if (!rows.length) return d.fields_dict.list.$wrapper.html(`<p class="text-muted">${__("No backups yet. Back Up Now takes one; nightly backups run at the hour set in Stemic Settings > Backups.")}</p>`);
        d.fields_dict.list.$wrapper.html(`<table class="table table-bordered table-sm"><thead><tr>
            <th>${__("Taken")}</th><th>${__("Kind")}</th><th>${__("Size")}</th><th>${__("Where")}</th><th>${__("Download")}</th><th></th></tr></thead><tbody>` +
            rows.map((b) => `<tr><td>${esc(frappe.datetime.str_to_user(b.taken_on))}${b.pinned ? ` <span class="indicator-pill blue">${__("Pinned")}</span>` : ""}</td>
                <td>${esc(__(b.kind))}</td><td>${b.size_mb || 0} MB</td><td>${esc(where(b))}</td>
                <td>${link(b, "database", __("Database"))}${b.public_file ? " · " + link(b, "public", __("Files")) : ""}${b.private_file ? " · " + link(b, "private", __("Private files")) : ""}</td>
                <td style="white-space:nowrap"><button class="btn btn-xs btn-default sc-pin" data-name="${esc(b.name)}">${b.pinned ? __("Unpin") : __("Pin")}</button>
                <button class="btn btn-xs btn-danger sc-restore" data-name="${esc(b.name)}" data-when="${esc(frappe.datetime.str_to_user(b.taken_on))}">${__("Restore")}</button></td></tr>`).join("") +
            `</tbody></table><p class="text-muted small">${__("Pinned backups are never removed by the retention rules.")}</p>`);
        d.$wrapper.find(".sc-pin").on("click", (e) => frappe.xcall("stemic_control.backups.toggle_pin", { backup: $(e.currentTarget).data("name") }).then(load));
        d.$wrapper.find(".sc-restore").on("click", (e) => restore_backup(frm, $(e.currentTarget).data("name"), $(e.currentTarget).data("when"), d));
    });
    d.show();
    load();
}

function restore_backup(frm, backup, when, list_dialog) {
    const site = frm.doc.canonical_site, esc = frappe.utils.escape_html;
    const d = new frappe.ui.Dialog({ title: __("Restore {0}", [site]), fields: [
        { fieldtype: "HTML", options: `<div class="alert alert-danger">${__("This replaces everything in {0} with the backup of <b>{1}</b>. Anything entered after that time is lost.", [esc(site), esc(when)])}
            <ul style="margin:8px 0 0"><li>${__("A safety backup of the site as it is now is taken first (and pinned).")}</li>
            <li>${__("The school is in maintenance mode while it runs.")}</li>
            <li>${__("The school's admin is emailed when it is done.")}</li></ul></div>` },
        { fieldname: "confirm_site", fieldtype: "Data", label: __("Type the site name to confirm: {0}", [site]), reqd: 1 },
    ], primary_action_label: __("Restore"), primary_action: ({ confirm_site }) => {
        if ((confirm_site || "").trim().toLowerCase() !== site.toLowerCase()) return frappe.msgprint(__("Type {0} exactly", [esc(site)]));
        frappe.xcall("stemic_control.backups.request_restore", { backup, confirm_site }).then((r) => {
            d.hide(); list_dialog.hide();
            frappe.msgprint({ title: __("Restore started"), indicator: "orange",
                message: __("Restore {0} is running in the background. Follow it under Site Operations; platform admins are alerted when it finishes.", [esc(r.operation)]) });
        });
    } });
    d.get_primary_btn().removeClass("btn-primary").addClass("btn-danger");
    d.show();
}

// Deleting a school: typed confirmation, 7-day grace (school suspended), then site, database, backups and records go
function school_deletion_buttons(frm) {
    const esc = frappe.utils.escape_html;
    frappe.db.get_value("SaaS Deletion", { slug: frm.doc.name, status: ["in", ["Scheduled", "Running", "Failed"]] },
        ["name", "status", "scheduled_for", "error"]).then(({ message: d }) => {
        if (!d || !d.name) {
            frm.add_custom_button(__("Delete School"), () => delete_school(frm), __("Actions"));
            return;
        }
        const when = frappe.datetime.str_to_user(d.scheduled_for);
        frm.dashboard.set_headline(d.status === "Failed"
            ? `<span style="color:var(--red-600)">${__("Deleting this school failed: {0}", [esc((d.error || "").split("\n")[0])])}</span>`
            : `<span style="color:var(--red-600)">${__("This school will be deleted on {0} ({1}).", [esc(when), esc(d.name)])}</span>`);
        if (d.status !== "Running") {
            frm.add_custom_button(__("Cancel Deletion"), () => frappe.confirm(__("Keep this school? It is put back as it was before (resumed if it was active)."),
                () => frappe.xcall("stemic_control.deletion.cancel", { tenant: frm.doc.name }).then(() => frm.reload_doc())), __("Actions"));
            frm.add_custom_button(d.status === "Failed" ? __("Retry Deletion") : __("Delete Now"), () =>
                frappe.confirm(__("Delete {0} now? This cannot be undone.", [esc(frm.doc.school_name)]), () =>
                    frappe.xcall("stemic_control.deletion.delete_now", { deletion: d.name }).then(() => {
                        frappe.show_alert({ message: __("Deletion started"), indicator: "red" }); frm.reload_doc(); })), __("Actions"));
        }
    });
}

function delete_school(frm) {
    const esc = frappe.utils.escape_html;
    frappe.xcall("stemic_control.deletion.preview", { tenant: frm.doc.name }, "GET").then((p) => {
        const li = (n, label) => n ? `<li>${n} ${label}</li>` : "";
        const kept = p.tax_records ? `<div class="alert alert-warning" style="margin-top:8px">${__("Kept: {0} tax record(s) (eTIMS){1}. Tax invoices are fiscal records and cannot be deleted; the school record stays, marked Deleted.",
            [p.tax_records, p.filed_with_kra ? __(", and {0} invoice(s) already with KRA with their payments", [p.filed_with_kra]) : ""])}</div>` : "";
        const d = new frappe.ui.Dialog({ title: __("Delete {0}", [p.school]), fields: [
            { fieldtype: "HTML", options: `<div class="alert alert-danger"><b>${__("This permanently deletes")}</b><ul style="margin:6px 0 0">
                ${p.site ? `<li>${__("the site {0} and its database", [esc(p.site)])}${p.database_mb ? ` (${p.database_mb} MB${p.students != null ? ", " + __("{0} students", [p.students]) : ""})` : ""}</li>` : ""}
                ${li(p.backups, __("backup(s), on this server and off-server"))}${li(p.domains, __("domain(s)"))}${li(p.invoices, __("invoice(s)"))}
                ${li(p.payments, __("payment(s)"))}${li(p.commissions, __("commission(s)"))}${li(p.licenses, __("licence(s)"))}
                <li>${__("the school record and its history")}</li></ul></div>${kept}
                <p>${__("The school is suspended now and deleted in {0} days; until then you can cancel. One final copy is kept for {1} days.", [p.grace_days, p.final_copy_days])}</p>` },
            { fieldname: "reason", fieldtype: "Small Text", label: __("Reason") },
            { fieldname: "confirm", fieldtype: "Data", reqd: 1, label: __("Type {0} to confirm", [p.confirm_words]) },
        ], primary_action_label: __("Schedule Deletion"), primary_action: (v) => {
            if (v.confirm.trim() !== p.confirm_words) return frappe.msgprint(__("Type {0} exactly", [esc(p.confirm_words)]));
            frappe.xcall("stemic_control.deletion.schedule", { tenant: frm.doc.name, confirm: v.confirm, reason: v.reason }).then((r) => {
                d.hide();
                frappe.msgprint({ title: __("Deletion scheduled"), indicator: "red", message: __("{0} is suspended and will be deleted on {1}.", [esc(p.school), frappe.datetime.str_to_user(r.scheduled_for)]) });
                frm.reload_doc();
            });
        } });
        d.get_primary_btn().removeClass("btn-primary").addClass("btn-danger");
        d.show();
    });
}
