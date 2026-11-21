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
        health: __("Learner health records, sick bay visits with parent SMS, visitor book and gate passes"),
        library: __("Book catalogue with copies, issue and return, renewals, overdue SMS and fines billed to fees"),
        pocket_money: __("Learners' pocket money: deposits, canteen purchases, daily limits, balance on the parent portal"),
        boarding: __("Dormitories, bed allocation, exeat passes with gate check-out/in and parent SMS"),
        homework: __("Homework per stream and subject, hand-in tracking, on the parent portal"),
        admissions: __("Online application form, interviews, offers and one-click admission"),
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
    // "KES 9,500", as on invoices and messages (Frappe's own symbol for KES is "Sh")
    money(v, currency) {
        return `${currency || frappe.boot.sysdefaults.currency || "KES"} ${format_number(v || 0, null, 0)}`;
    },
});

// Record money received against an invoice (Subscription and Invoice forms)
stemic_control.record_payment = function (invoice, outstanding, after) {
    const d = new frappe.ui.Dialog({
        title: __("Record Payment for {0}", [invoice]),
        fields: [
            { fieldname: "amount", fieldtype: "Currency", label: __("Amount"), default: outstanding, reqd: 1,
              description: __("Still owed: {0}", [stemic_control.money(outstanding)]) },
            { fieldname: "mode", fieldtype: "Select", label: __("Paid By"), options: "M-Pesa\nBank Transfer\nCheque\nCash\nCard\nOther", default: "M-Pesa", reqd: 1 },
            { fieldname: "reference", fieldtype: "Data", label: __("Reference"), reqd: 1, description: __("M-Pesa code, bank reference or cheque number") },
            { fieldname: "payment_date", fieldtype: "Date", label: __("Date"), default: frappe.datetime.get_today(), reqd: 1 },
        ],
        primary_action_label: __("Record"),
        primary_action(v) {
            d.hide();
            frappe.call({ method: "stemic_control.billing.record_payment", args: { invoice, ...v }, freeze: true }).then(({ message: r }) => {
                frappe.show_alert({ indicator: "green", message: r.invoice_status === "Paid"
                    ? __("Paid in full. The subscription now runs to {0}.", [frappe.datetime.str_to_user(r.ends_on)])
                    : __("Recorded. {0} still owed.", [stemic_control.money(r.outstanding)]) }, 8);
                after && after(r);
            });
        },
    });
    d.show();
};

// Onboard a School: one form that registers the school, starts its trial (or records its first payment), claims its
// address, approves it and queues its site (stemic_control.wizard.onboard_school). Every step keeps its usual checks.
stemic_control.onboard_school = function (defaults = {}) {
    const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
    frappe.xcall("stemic_control.wizard.options", {}, "GET").then((o) => {
        if (!o.plans.length) {
            return frappe.msgprint({ title: __("No plans yet"), indicator: "orange",
                message: __("Create at least one plan first (Billing > Plans): every school starts on a plan."),
                primary_action: { label: __("New Plan"), action: () => frappe.new_doc("SaaS Plan") } });
        }
        const money = (v) => stemic_control.money(v, o.currency);
        const state = { plan: defaults.plan || o.defaults.plan, start: o.defaults.start, when: o.defaults.when,
                        slug_touched: false, slug: null, slug_ok: false, timer: null };
        const START = [
            ["Free trial", "clock", __("Free trial"), __("Site now, invoice before the trial ends")],
            ["Paid", "check", __("Paid now"), __("Record the first payment")],
            ["Internal / Demo", "tool", __("Internal / demo"), __("No billing")],
        ];
        const WHEN = [
            ["build", __("Approve and build the site now")],
            ["approval", __("Send to another admin to approve")],
            ["draft", __("Save as a draft")],
        ];
        const d = new frappe.ui.Dialog({
            title: __("Onboard a School"),
            size: "large",
            fields: [
                { fieldtype: "Section Break", label: __("The school") },
                { fieldname: "school_name", fieldtype: "Data", label: __("School name"), reqd: 1, default: defaults.school_name,
                  placeholder: "Greenhill Academy", onchange: () => { if (!state.slug_touched) check_slug(); } },
                { fieldname: "admin_email", fieldtype: "Data", options: "Email", label: __("Head or admin email"), reqd: 1,
                  description: __("Gets the login and the set-password link when the site is ready.") },
                { fieldtype: "Column Break" },
                { fieldname: "slug", fieldtype: "Data", label: __("Address"), description: "&nbsp;",
                  onchange: () => { state.slug_touched = !!d.get_value("slug"); check_slug(); } },
                { fieldname: "platform_domain", fieldtype: "Select", label: __("On domain"),
                  options: (o.platform_domains || [o.platform_domain]).join("\n"), default: o.platform_domain,
                  hidden: (o.platform_domains || []).length < 2, onchange: () => check_slug() },
                { fieldname: "contact_phone", fieldtype: "Data", options: "Phone", label: __("Phone"),
                  description: __("For SMS notices, if SMS is on.") },
                { fieldtype: "Section Break", label: __("Plan") },
                { fieldname: "plan_html", fieldtype: "HTML" },
                { fieldtype: "Section Break", label: __("How they start") },
                { fieldname: "start_html", fieldtype: "HTML" },
                { fieldtype: "Section Break" },
                { fieldname: "trial_days", fieldtype: "Int", label: __("Trial length (days)"), default: o.defaults.trial_days,
                  depends_on: "eval:doc.start === 'Free trial'", onchange: () => summary() },
                { fieldname: "months", fieldtype: "Select", label: __("Months paid for"), options: "1\n3\n6\n12\n24",
                  default: String([1, 3, 6, 12, 24].includes(o.defaults.months) ? o.defaults.months : 12),
                  depends_on: "eval:doc.start === 'Paid'", onchange: () => summary() },
                { fieldname: "payment_mode", fieldtype: "Select", label: __("Paid by"), options: o.pay_modes.join("\n"),
                  default: "M-Pesa", depends_on: "eval:doc.start === 'Paid'" },
                { fieldtype: "Column Break" },
                { fieldname: "payment_ref", fieldtype: "Data", label: __("Payment reference"), placeholder: "QAB12CD34E",
                  depends_on: "eval:doc.start === 'Paid'", mandatory_depends_on: "eval:doc.start === 'Paid'",
                  description: __("M-Pesa code, bank reference or cheque number.") },
                { fieldname: "amount", fieldtype: "Currency", label: __("Amount received"), depends_on: "eval:doc.start === 'Paid'",
                  description: __("Blank means the full invoice.") },
                { fieldname: "agent", fieldtype: "Select", label: __("Sales agent"),
                  options: [{ value: "", label: __("None (direct)") }, ...o.agents.map((a) => ({ value: a.name, label: a.agent_name }))] },
                { fieldname: "start", fieldtype: "Data", hidden: 1, default: state.start },
                { fieldtype: "Section Break", label: __("Own domain (optional)"), collapsible: 1 },
                { fieldname: "custom_domain", fieldtype: "Data", label: __("The school's own domain"), placeholder: "portal.greenhill.ac.ke",
                  description: __("You will get a DNS record for the school to add. It can also be added later.") },
                { fieldtype: "Section Break", label: __("When I press Onboard") },
                { fieldname: "when_html", fieldtype: "HTML" },
                { fieldname: "summary_html", fieldtype: "HTML" },
            ],
            primary_action_label: __("Onboard School"),
            primary_action: (v) => submit(v),
        });

        function check_slug() {
            clearTimeout(state.timer);
            state.timer = setTimeout(() => {
                const typed = d.get_value("slug"), name = d.get_value("school_name");
                if (!typed && !name) return;
                frappe.xcall("stemic_control.wizard.check_slug", { slug: state.slug_touched ? typed : null, school_name: name,
                    domain: d.get_value("platform_domain") || o.platform_domain }, "GET")
                    .then((r) => {
                        state.slug = r.slug; state.slug_ok = r.ok;
                        if (!state.slug_touched && d.get_value("slug") !== r.slug) d.fields_dict.slug.set_input(r.slug);
                        const $d = d.fields_dict.slug.$wrapper.find(".help-box");
                        $d.html(r.ok
                            ? `<span style="color:var(--green-600)">${frappe.utils.icon("check", "xs")} ${esc(r.host)}</span>`
                            : `<span style="color:var(--red-600)">${esc(r.problem)}</span>` + (r.alternative
                                ? ` · <a href="#" class="sc-alt">${__("Use {0}", [esc(r.alternative)])}</a>` : ""));
                        $d.find(".sc-alt").on("click", (e) => { e.preventDefault(); state.slug_touched = true;
                            d.fields_dict.slug.set_input(r.alternative); check_slug(); });
                        summary();
                    });
            }, 300);
        }

        function cards(field, items, current, cls = "") {
            d.fields_dict[field].$wrapper.html(`<div class="sc-choices ${cls}">${items.map(([key, icon, title, text]) =>
                `<button type="button" class="sc-choice ${key === current ? "on" : ""}" data-key="${esc(key)}">
                    ${icon ? `<span class="sc-choice-ic">${frappe.utils.icon(icon, "md")}</span>` : ""}
                    <span><b>${title}</b><small>${text}</small></span></button>`).join("")}</div>`);
        }

        function render() {
            cards("plan_html", o.plans.map((p) => [p.name, "", esc(p.name),
                `${money(p.monthly_price)} ${__("a month")}${p.student_limit ? ` · ${__("up to {0} students", [p.student_limit])}` : ""}
                 <br>${esc((p.modules || []).join(", ") || __("Core only"))}`]), state.plan, "sc-plans");
            cards("start_html", START, state.start, "sc-three");
            cards("when_html", WHEN.map(([k, t]) => [k, "", t, ""]), state.when, "sc-three sc-slim");
            d.fields_dict.plan_html.$wrapper.find("[data-key]").on("click", function () { state.plan = this.dataset.key; render(); });
            d.fields_dict.start_html.$wrapper.find("[data-key]").on("click", function () {
                state.start = this.dataset.key; d.set_value("start", state.start); render(); });
            d.fields_dict.when_html.$wrapper.find("[data-key]").on("click", function () { state.when = this.dataset.key; render(); });
            summary();
        }

        function summary() {
            const plan = o.plans.find((p) => p.name === state.plan) || {};
            const dom = d.get_value("platform_domain") || o.platform_domain;
            const host = state.slug ? `${state.slug}.${dom}` : `<${__("address")}>.${dom}`;
            const steps = [__("Register the school and reserve {0}", [`<b>${esc(host)}</b>`])];
            if (state.start === "Free trial") steps.push(__("Start a {0}-day free trial of {1}", [cint(d.get_value("trial_days")) || 30, esc(plan.name || "")]));
            else if (state.start === "Paid") {
                const m = cint(d.get_value("months")) || 12;
                steps.push(__("Invoice {0} month(s) of {1} ({2}) and record the payment", [m, esc(plan.name || ""), money((plan.monthly_price || 0) * m)]));
            } else steps.push(__("Give it {0} as an internal / demo school, with no billing", [esc(plan.name || "")]));
            if (state.when !== "draft") steps.push(__("Send it for approval"));
            const warn = [];
            if (state.when === "build") {
                steps.push(__("Approve it and build its site (3 to 8 minutes, in the background)"));
                steps.push(__("When the site is ready, email the head the login link"));
                if (o.auto_license) steps.push(o.can_sign ? __("...and the licence key for the plan")
                    : __("...but no licence key: signing is not set up here"));
                if (o.environment_problem) warn.push(__("This server may not build sites yet ({0}), so the school will be approved but its site not queued.", [esc(o.environment_problem)]));
            }
            if (state.start === "Free trial") steps.push(__("Invoice it before the trial ends and remind the head 3 days before"));
            d.fields_dict.summary_html.$wrapper.html(`<div class="sc-preview" style="margin-top:6px">
                <div style="font-weight:600;margin-bottom:4px">${__("What will happen")}</div>
                <ol>${steps.map((s) => `<li>${s}</li>`).join("")}</ol>
                ${warn.map((w) => `<div style="color:var(--orange-600);font-size:13px;margin-top:8px">${w}</div>`).join("")}</div>`);
        }

        function submit(v) {
            if (!state.slug_ok) return frappe.msgprint(__("Choose a free address for the school first."));
            d.get_primary_btn().prop("disabled", true);
            frappe.call({ method: "stemic_control.wizard.onboard_school", freeze: true, freeze_message: __("Onboarding {0}...", [esc(v.school_name)]),
                args: { ...v, slug: state.slug, plan: state.plan, start: state.start, when: state.when } })
                .then(({ message: r }) => { d.hide(); done(r); })
                .always(() => d.get_primary_btn().prop("disabled", false));
        }

        function done(r) {
            const ok = `<ul class="sc-done">${r.steps.map((s) => `<li>${frappe.utils.icon("check", "xs")} ${esc(s)}</li>`).join("")}</ul>`;
            const warn = r.warnings.map((w) => `<div class="sc-warn">${esc(w)}</div>`).join("");
            const next = r.job ? __("The site is being built. The school's page shows its progress and refreshes by itself.")
                : r.status === "Pending Approval" ? __("Another platform admin can now approve it from the school's page.")
                : r.status === "Draft" ? __("Saved as a draft. Send it for approval from the school's page when ready.")
                : __("Open the school to finish.");
            const dd = new frappe.ui.Dialog({ title: __("{0} is onboarded", [esc(d.get_value("school_name"))]),
                fields: [{ fieldname: "info", fieldtype: "HTML" }],
                primary_action_label: __("Open School"), primary_action: () => { dd.hide(); frappe.set_route("Form", "SaaS Tenant", r.tenant); } });
            dd.fields_dict.info.$wrapper.html(`${ok}${warn}<p style="margin:12px 0 0">${next}</p>`);
            dd.set_secondary_action_label(__("Onboard another"));
            dd.set_secondary_action(() => { dd.hide(); stemic_control.onboard_school(); });
            dd.show();
            stemic_control.trigger_refresh && stemic_control.trigger_refresh();
        }

        d.show();
        render();
        if (defaults.school_name) check_slug();
    });
};

// ----------------------------------------------------------------------------- service: batches and health
stemic_control.batch_started = function (r) {
    const esc = frappe.utils.escape_html;
    const skipped = (r.skipped || []).map((s) => `<li>${esc(s.site)}: ${esc(s.why)}</li>`).join("");
    const elsewhere = (r.not_here || []).length ? `<p class="text-muted">${__("Not on this server (skipped): {0}", [esc(r.not_here.join(", "))])}</p>` : "";
    frappe.msgprint({ title: __("Started"), indicator: r.queued ? "blue" : "orange",
        message: `<p>${__("{0} school(s) queued, one at a time (batch {1}).", [r.queued, esc(r.batch)])}</p>`
            + (skipped ? `<p>${__("Skipped")}:</p><ul>${skipped}</ul>` : "") + elsewhere
            + (r.queued ? `<p><a href="#" class="sc-batch">${__("Follow this batch")}</a></p>` : "") });
    $(".sc-batch").on("click", (e) => { e.preventDefault(); stemic_control.batch_report(r.batch); });
};

stemic_control.batch_report = function (batch) {
    const esc = frappe.utils.escape_html;
    frappe.xcall("stemic_control.service.batch_status", { batch }, "GET").then((rows) => frappe.msgprint({ title: __("Batch {0}", [esc(batch)]),
        wide: true, message: `<table class="table table-sm table-bordered"><tr><th>${__("School")}</th><th>${__("Action")}</th><th>${__("Status")}</th><th>${__("Result")}</th></tr>`
            + rows.map((o) => `<tr><td>${esc(o.site)}</td><td>${esc(__(o.action))}</td><td>${esc(__(o.status))}</td><td class="small">${esc(o.summary || "")}</td></tr>`).join("")
            + "</table>" }));
};

stemic_control.update_all_schools = function () {
    frappe.confirm(__("Update (migrate) every live school on this server now, one at a time?"), () =>
        frappe.xcall("stemic_control.service.update_all_schools").then(stemic_control.batch_started));
};

stemic_control.service_health = function () {
    const esc = frappe.utils.escape_html;
    frappe.xcall("stemic_control.service.service_health", {}, "GET").then((h) => {
        const pill = (ok, yes, no) => `<span class="indicator-pill ${ok ? "green" : ok === false ? "red" : "gray"}">${ok ? yes : ok === false ? no : __("Not checked yet")}</span>`;
        const machinery = h.machinery.length
            ? `<ul>${h.machinery.map((p) => `<li style="color:var(--red-600)">${esc(p.message)} <span class="text-muted">${esc(p.fix)}</span></li>`).join("")}</ul>`
            : `<p style="color:var(--green-600)">${__("Workers, scheduler and queues are running.")}</p>`;
        const disk = `<p>${__("Disk")}: ${__("{0} GB free of {1} GB", [h.disk.free_gb, h.disk.total_gb])} ${h.disk.problem ? `<span style="color:var(--red-600)">(${esc(h.disk.problem)})</span>` : ""}</p>`;
        const rows = h.schools.map((s) => `<tr><td>${esc(s.site)}</td><td>${pill(s.answering, __("Answering"), __("Not answering"))}</td>
            <td>${s.cert_days == null ? "–" : `<span style="color:var(--${s.cert_days < 14 ? "red" : "green"}-600)">${__("{0} days", [s.cert_days])}</span>`}</td>
            <td>${s.last_backup ? esc(frappe.datetime.str_to_user(s.last_backup)) : `<span style="color:var(--orange-600)">${__("None")}</span>`}</td>
            <td class="small">${s.last_operation ? esc(__(s.last_operation.action) + ": " + __(s.last_operation.status)) : "–"}</td></tr>`).join("");
        frappe.msgprint({ title: __("Service Health"), wide: true, indicator: h.machinery.length || h.disk.problem ? "orange" : "green",
            message: `<h5>${__("Machinery")}</h5>${machinery}${disk}`
                + (h.batches_running.length ? `<p>${__("Batches running")}: ${h.batches_running.map(esc).join(", ")}</p>` : "")
                + `<h5>${__("Schools")}</h5><table class="table table-sm table-bordered"><tr><th>${__("Site")}</th><th>${__("Site check")}</th>`
                + `<th>${__("Certificate")}</th><th>${__("Last backup")}</th><th>${__("Last operation")}</th></tr>${rows}</table>`
                + `<p class="text-muted small">${__("Sites are checked every 15 minutes and certificates daily. Code version {0}.", [esc(h.code_version || "?")])}</p>` });
    });
};
