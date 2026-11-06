// Stemic Overview: the Control Center's front page. Overview = money, the onboarding pipeline, the last 12 months,
// what renews or ends soon, plans, agents, setup and what needs attention. The other tabs keep their KPI cards.
frappe.pages["stemic-overview"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Stemic Schools"), single_column: true });
    page.set_primary_action(__("Onboard a School"), () => stemic_control.onboard_school(), "add");
    page.add_menu_item(__("New school (blank form)"), () => frappe.new_doc("SaaS Tenant"));
    page.add_menu_item(__("Setup Check"), () => frappe.set_route("Form", "Stemic Settings"));
    const root = document.createElement("div");
    root.className = "stemic-overview";
    wrapper.querySelector(".layout-main-section").appendChild(root);

    const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
    const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];  // categorical, fixed order (dataviz palette)
    const groups = {
        schools: [
            ["total_schools", "Total Schools", "SaaS Tenant", {}, "Registered"],
            ["active_schools", "Active Schools", "SaaS Tenant", { status: "Active" }, "Operational status not verified"],
            ["trial_schools", "Trial Schools", "SaaS Subscription", { status: "Trial" }, "Trial subscriptions"],
            ["pending_provisioning", "Pending Provisioning", "SaaS Provisioning Job", { status: ["in", ["Queued", "Running"]] }, "Queued or running jobs"],
            ["failed_provisioning", "Failed Provisioning", "SaaS Provisioning Job", { status: "Failed" }, "Needs investigation"],
            ["pending_domains", "Pending Domains", "SaaS Domain", { status: "Pending Verification" }, "DNS ownership outstanding"],
        ],
        billing: [
            ["active_subscriptions", "Active Subscriptions", "SaaS Subscription", { status: "Active" }, "Billing status only"],
            ["trial_subscriptions", "Trial Subscriptions", "SaaS Subscription", { status: "Trial" }, "In evaluation"],
            ["past_due", "Past Due", "SaaS Subscription", { status: "Past Due" }, "Requires attention"],
            ["expiring_soon", "Expiring in 30 Days", "SaaS Subscription", null, "Upcoming renewals"],
        ],
        tax: [
            ["draft", "Needs Review", "SaaS eTIMS Invoice", { status: "Draft" }, "Prepared invoices awaiting finance review"],
            ["ready", "Ready for Integration", "SaaS eTIMS Invoice", { status: "Ready" }, "Not yet submitted to KRA"],
            ["pending", "Pending Submission", "SaaS eTIMS Invoice", { status: "Pending Submission" }, "Awaiting provider processing"],
            ["submitted", "Submitted to KRA", "SaaS eTIMS Invoice", { status: "Submitted" }, "Use provider acknowledgements, not local assumptions"],
            ["rejected", "Rejected", "SaaS eTIMS Invoice", { status: "Rejected" }, "Investigate provider error"],
            ["profiles", "Enabled Tax Profiles", "SaaS Tax Profile", { enabled: 1 }, "School seller tax configurations"],
        ],
        agents: [
            ["total_agents", "Total Agents", "SaaS Agent", {}, "Registered agents"],
            ["active_agents", "Active Agents", "SaaS Agent", { status: "Active" }, "Currently enabled"],
            ["referred_schools", "Referred Schools", "SaaS Tenant", { agent: ["is", "set"] }, "Attributed schools"],
            ["referred_active_schools", "Active Referrals", "SaaS Tenant", { agent: ["is", "set"], status: "Active" }, "Active tenant records"],
        ],
    };
    const tabs = [["home", "Overview"], ["schools", "Schools"], ["billing", "Billing"], ["agents", "Agents"], ["tax", "Kenya Tax & eTIMS"]];
    let selected = "home", metrics = null, tax = null, ov = null, attention = null, busy = false, loadError = false;
    try { selected = localStorage.getItem("stemic-overview-tab") || "home"; } catch (e) { /* private window */ }
    if (!tabs.some(([id]) => id === selected)) selected = "home";

    const money = (v) => stemic_control.money(v, ov ? ov.currency : "KES");
    const short = (v) => {  // KES 1.2M, 340K: for tiles where the full figure would wrap
        const n = Math.abs(v || 0), cur = ov ? ov.currency : "KES";
        if (n >= 1e6) return `${cur} ${(v / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`;
        if (n >= 1e4) return `${cur} ${Math.round(v / 1e3)}K`;
        return money(v);
    };
    const go = (doctype, filters) => { frappe.route_options = { ...(filters || {}) }; frappe.set_route("List", doctype); };

    function el(html) {
        const t = document.createElement("template");
        t.innerHTML = html.trim();
        return t.content.firstElementChild;
    }

    function render() {
        root.replaceChildren();
        if (loadError) root.append(el(`<div class="alert alert-warning" role="alert">${__("Figures could not be loaded. Use Refresh to try again.")}</div>`));
        const nav = el(`<div class="stemic-tabs" role="tablist"></div>`);
        for (const [id, label] of tabs) {
            const btn = el(`<button type="button" role="tab" class="stemic-tab${selected === id ? " selected" : ""}" aria-selected="${selected === id}">${__(label)}</button>`);
            btn.addEventListener("click", () => {
                selected = id;
                try { localStorage.setItem("stemic-overview-tab", id); } catch (e) { /* ignore */ }
                render();
            });
            nav.append(btn);
        }
        root.append(nav);
        if (selected === "home") return render_home();
        if (selected === "tax") {
            const action = el(`<button type="button" class="btn btn-default btn-sm stemic-tab-action">${__("Configure School Tax Profile")}</button>`);
            action.addEventListener("click", () => frappe.set_route("List", "SaaS Tax Profile"));
            root.append(action);
        }
        root.append(kpi_cards(groups[selected], selected === "tax" ? tax : metrics?.[selected]));
        if (selected === "billing" && ov) {
            root.append(two(chart_card("collections"), plans_card()));
            root.append(renewals_card());
        }
        if (selected === "agents" && ov) root.append(agents_card(true));
        if (selected === "schools" && ov) root.append(two(pipeline_card(), chart_card("schools")));
        if (selected === "tax") root.append(el(`<p class="stemic-note">${__("Preparation only. This integration has not submitted an invoice to KRA. Configure a certified OSCU/VSCU pathway and complete KRA testing before enabling live submissions.")}</p>`));
        draw_charts();
    }

    function kpi_cards(list, values) {
        const grid = el(`<div class="stemic-card-grid"></div>`);
        for (const [key, label, doctype, filters, helper] of list) {
            const value = busy && !values ? "—" : (values?.[key] ?? "—");
            const card = el(`<button type="button" class="stemic-kpi-card" aria-label="${esc(__(label))}: ${esc(value)}">
                <span class="stemic-kpi-label">${__(label)}</span><strong class="stemic-kpi-value">${esc(value)}</strong>
                <span class="stemic-kpi-hint">${__(helper)}</span></button>`);
            if (filters) card.addEventListener("click", () => go(doctype, filters));
            else { card.setAttribute("aria-disabled", "true"); card.title = __("Summary only"); }
            grid.append(card);
        }
        return grid;
    }

    // ------------------------------------------------------------------ Overview tab
    function render_home() {
        if (!ov) {
            root.append(el(`<div class="so-loading">${busy ? __("Loading...") : __("Could not load the overview. Use Refresh to try again.")}</div>`));
            return;
        }
        if (ov.setup && ov.setup.todo.length) root.append(setup_card());
        root.append(money_row());
        root.append(pipeline_card());
        root.append(two(chart_card("collections"), chart_card("schools")));
        root.append(two(renewals_card(), attention_card()));
        root.append(two(plans_card(), agents_card(false)));
        root.append(el(`<p class="stemic-note">${__("Money is from submitted invoices and payments in this Control Center. Monthly recurring revenue is the plan price of every Active subscription.")}</p>`));
        draw_charts();
    }

    function setup_card() {
        const s = ov.setup, pct = Math.round((s.ready / Math.max(1, s.total)) * 100);
        const box = el(`<section class="so-setup">
            <div class="so-setup-head">
                <div><strong>${__("Finish setting up the Control Center")}</strong>
                    <span>${__("{0} of {1} checks ready", [s.ready, s.total])}</span></div>
                <button type="button" class="btn btn-default btn-sm">${__("Open Setup Check")}</button>
            </div>
            <div class="so-meter" role="meter" aria-valuemin="0" aria-valuemax="${s.total}" aria-valuenow="${s.ready}"
                 aria-label="${esc(__("Setup checks ready"))}"><i style="width:${pct}%"></i></div>
            <ul>${s.todo.map((t) => `<li><b>${esc(t.label)}</b> <span>${esc(t.fix || t.detail)}</span></li>`).join("")}
                ${s.more ? `<li class="text-muted">${__("and {0} more", [s.more])}</li>` : ""}</ul>
        </section>`);
        box.querySelector("button").addEventListener("click", () => frappe.set_route("Form", "Stemic Settings"));
        return box;
    }

    function money_row() {
        const m = ov.money, change = m.collected_last ? Math.round(((m.collected - m.collected_last) / m.collected_last) * 100) : null;
        const tiles = [
            [__("Monthly recurring revenue"), short(m.mrr), __("{0} a year · {1} active subscriptions", [short(m.arr), m.active_subscriptions]),
                () => go("SaaS Subscription", { status: "Active" }), m.mrr],
            [__("Collected this month"), short(m.collected), change === null ? __("Nothing collected last month")
                : `<span class="${change >= 0 ? "so-up" : "so-down"}">${change >= 0 ? "▲" : "▼"} ${Math.abs(change)}%</span> ${__("vs {0} last month", [short(m.collected_last)])}`,
                () => go("SaaS Payment", { docstatus: 1 }), m.collected],
            [__("Owed by schools"), short(m.owed), m.overdue ? `<span class="so-down">${__("{0} overdue", [short(m.overdue)])}</span>` : __("Nothing overdue"),
                () => go("SaaS Invoice", { docstatus: 1, status: ["in", ["Unpaid", "Partly Paid", "Overdue"]] }), m.owed],
            [__("Schools live"), `${ov.schools.live}<small> / ${ov.schools.total}</small>`, __("{0} on a free trial", [m.trials]),
                () => go("SaaS Tenant", { status: "Active" })],
            [__("Agents' commission due"), short(m.commission_due), __("Earned, not paid out yet"), () => go("SaaS Commission", { status: "Due" }), m.commission_due],
        ];
        const row = el(`<div class="so-money"></div>`);
        for (const [label, value, note, click, exact] of tiles) {
            const t = el(`<button type="button" class="so-tile"><span>${label}</span><b>${value}</b><small>${note}</small></button>`);
            if (exact !== undefined) t.title = `${label}: ${money(exact)}`;
            t.addEventListener("click", click);
            row.append(t);
        }
        return row;
    }

    function pipeline_card() {
        const card = el(`<section class="so-card"><div class="so-card-head"><h3>${__("Onboarding pipeline")}</h3>
            <button type="button" class="btn btn-primary btn-xs">${__("Onboard a School")}</button></div>
            <div class="so-pipe"></div><div class="so-stuck"></div></section>`);
        card.querySelector(".btn").addEventListener("click", () => stemic_control.onboard_school());
        const pipe = card.querySelector(".so-pipe");
        ov.pipeline.forEach((stage, i) => {
            const s = el(`<button type="button" class="so-stage ${stage.count ? "" : "empty"} ${i === ov.pipeline.length - 1 ? "live" : ""}">
                <b>${stage.count}</b><span>${__(stage.label)}</span><small>${__(stage.hint)}</small></button>`);
            s.addEventListener("click", () => go("SaaS Tenant", { status: ["in", stage.statuses] }));
            pipe.append(s);
        });
        const stuck = card.querySelector(".so-stuck");
        for (const s of ov.stuck) {
            const chip = el(`<button type="button" class="so-chip ${s.label === "Failed" ? "bad" : "warn"}">${esc(__(s.label))}: ${s.count}</button>`);
            chip.addEventListener("click", () => go("SaaS Tenant", { status: s.label }));
            stuck.append(chip);
        }
        if (!ov.stuck.length) stuck.remove();
        return card;
    }

    function chart_card(kind) {
        const title = kind === "collections" ? __("Invoiced and collected, last 12 months") : __("New schools, last 12 months");
        const series = kind === "collections" ? [__("Invoiced"), __("Collected")] : [__("Registered"), __("Went live")];
        const values = kind === "collections" ? [ov.invoiced, ov.collections] : [ov.new_schools, ov.went_live];
        const total = values[1].reduce((a, b) => a + b, 0);
        const card = el(`<section class="so-card"><div class="so-card-head"><h3>${title}</h3>
            <span class="so-sub">${kind === "collections" ? __("{0} collected", [short(total)]) : __("{0} went live", [total])}</span></div>
            <div class="so-chart" data-chart="${kind}"></div>
            <details class="so-table-view"><summary>${__("Show as a table")}</summary>
                <table class="so-table"><thead><tr><th>${__("Month")}</th>${series.map((s) => `<th class="num">${esc(s)}</th>`).join("")}</tr></thead>
                <tbody>${ov.months.map((m, i) => `<tr><td>${esc(m)}</td>${values.map((v) => `<td class="num">${kind === "collections" ? money(v[i]) : v[i]}</td>`).join("")}</tr>`).join("")}</tbody></table>
            </details></section>`);
        card._chart = { kind, series, values };
        return card;
    }

    function draw_charts() {
        if (!frappe.Chart) return;
        root.querySelectorAll(".so-chart").forEach((node) => {
            const { kind, series, values } = node.closest(".so-card")._chart;
            const has = values.some((v) => v.some((x) => x));
            if (!has) {
                node.innerHTML = `<div class="so-empty">${kind === "collections" ? __("No invoices or payments in the last 12 months yet.") : __("No schools registered in the last 12 months.")}</div>`;
                return;
            }
            new frappe.Chart(node, {
                type: "bar", height: 230, colors: SERIES.slice(0, series.length),
                data: { labels: ov.months, datasets: series.map((name, i) => ({ name, values: values[i] })) },
                axisOptions: { xIsSeries: 1, shortenYAxisNumbers: 1 },
                barOptions: { spaceRatio: 0.45 },
                tooltipOptions: { formatTooltipY: (v) => (kind === "collections" ? money(v) : v) },
            });
        });
    }

    function renewals_card() {
        const rows = ov.renewals;
        const card = el(`<section class="so-card"><div class="so-card-head"><h3>${__("Renewals and trials ending, next 30 days")}</h3>
            <span class="so-sub">${rows.length ? __("{0} school(s)", [rows.length]) : ""}</span></div></section>`);
        if (!rows.length) {
            card.append(el(`<div class="so-empty">${__("Nothing ends in the next 30 days.")}</div>`));
            return card;
        }
        const table = el(`<table class="so-table so-click"><thead><tr><th>${__("School")}</th><th>${__("Ends")}</th>
            <th>${__("Invoice")}</th></tr></thead><tbody></tbody></table>`);
        for (const r of rows) {
            const soon = r.days_left <= 7;
            const tr = el(`<tr><td><b>${esc(r.school_name || r.tenant)}</b><small>${esc(__(r.kind))} · ${esc(r.plan)}</small></td>
                <td class="${soon ? "so-down" : ""}">${r.days_left === 0 ? __("Today") : __("in {0} days", [r.days_left])}<small>${frappe.datetime.str_to_user(r.ends_on)}</small></td>
                <td>${r.invoice ? `${esc(r.invoice)}<small>${money(r.outstanding)} ${__("owed")}</small>`
                    : `<span class="text-muted">${__("Not invoiced")}</span><small>${money((r.monthly_price || 0) * 12)} ${__("a year")}</small>`}</td></tr>`);
            tr.addEventListener("click", () => frappe.set_route("Form", "SaaS Subscription", r.name));
            table.tBodies[0].append(tr);
        }
        card.append(table);
        return card;
    }

    function plans_card() {
        const card = el(`<section class="so-card"><div class="so-card-head"><h3>${__("Plans")}</h3>
            <button type="button" class="btn btn-default btn-xs">${__("Manage")}</button></div></section>`);
        card.querySelector(".btn").addEventListener("click", () => frappe.set_route("List", "SaaS Plan"));
        if (!ov.plans.length) {
            card.append(el(`<div class="so-empty">${__("No plans yet. Every school starts on a plan.")}</div>`));
            return card;
        }
        const top = Math.max(1, ...ov.plans.map((p) => p.mrr));
        const table = el(`<table class="so-table so-click"><thead><tr><th>${__("Plan")}</th><th class="num">${__("Active")}</th>
            <th class="num">${__("Trial")}</th><th class="num">${__("Late")}</th><th>${__("Monthly revenue")}</th></tr></thead><tbody></tbody></table>`);
        for (const p of ov.plans) {
            const tr = el(`<tr><td><b>${esc(p.name)}</b><small>${money(p.monthly_price)} ${__("a month")}</small></td>
                <td class="num">${p.active}</td><td class="num">${p.trial}</td><td class="num ${p.late ? "so-down" : ""}">${p.late}</td>
                <td><div class="so-bar"><i style="width:${Math.round((p.mrr / top) * 100)}%"></i></div><small>${money(p.mrr)}</small></td></tr>`);
            tr.addEventListener("click", () => frappe.set_route("Form", "SaaS Plan", p.name));
            table.tBodies[0].append(tr);
        }
        card.append(table);
        return card;
    }

    function agents_card(full) {
        const card = el(`<section class="so-card"><div class="so-card-head"><h3>${__("Agents this year")}</h3>
            <button type="button" class="btn btn-default btn-xs">${__("Commission statement")}</button></div></section>`);
        card.querySelector(".btn").addEventListener("click", () => frappe.set_route("query-report", "Agent Commission Statement"));
        const rows = full ? ov.agents : ov.agents.slice(0, 5);
        if (!rows.length) {
            card.append(el(`<div class="so-empty">${__("No active agents. Schools you bring in yourself show as direct.")}</div>`));
            return card;
        }
        const table = el(`<table class="so-table so-click"><thead><tr><th>${__("Agent")}</th><th class="num">${__("Schools")}</th>
            <th class="num">${__("Collected")}</th><th class="num">${__("Due to them")}</th></tr></thead><tbody></tbody></table>`);
        for (const a of rows) {
            const tr = el(`<tr><td><b>${esc(a.agent_name)}</b><small>${__("{0}% commission", [a.commission_rate || 0])}</small></td>
                <td class="num">${a.schools}<small>${__("{0} live", [a.live])}</small></td>
                <td class="num">${money(a.collected)}</td><td class="num">${money(a.due)}</td></tr>`);
            tr.addEventListener("click", () => frappe.set_route("Form", "SaaS Agent", a.name));
            table.tBodies[0].append(tr);
        }
        card.append(table);
        return card;
    }

    // "Needs attention": a few newest items per group, each naming the school and opening the record to act on
    function attention_card() {
        const card = el(`<section class="so-card"><div class="so-card-head"><h3>${__("Needs attention")}</h3></div></section>`);
        if (!attention) {
            card.append(el(`<div class="so-empty">${busy ? __("Loading...") : __("Could not load the attention list.")}</div>`));
            return card;
        }
        const open = attention.groups.filter((g) => g.count);
        if (!open.length) {
            card.append(el(`<div class="so-empty so-clear">${frappe.utils.icon("check", "sm")} ${__("Nothing needs attention: no failed sites, overdue payments, pending domains or approvals.")}</div>`));
            return card;
        }
        for (const group of open) {
            const box = el(`<div class="stemic-attention-group ${group.severity}"><div class="stemic-attention-head">
                <strong>${esc(__(group.label))} (${group.count})</strong>
                <button type="button" class="btn btn-link btn-xs">${__("View all")}</button></div></div>`);
            box.querySelector(".btn").addEventListener("click", () => go(group.doctype, group.filters));
            for (const item of group.items) {
                const row = el(`<button type="button" class="stemic-attention-item"><strong>${esc(item.school)}</strong>
                    <span>${esc(item.detail)}</span><small>${esc(frappe.datetime.prettyDate(item.modified))}</small></button>`);
                row.addEventListener("click", () => frappe.set_route("Form", item.doctype, item.name));
                box.append(row);
            }
            card.append(box);
        }
        return card;
    }

    function two(a, b) {
        const row = el(`<div class="so-two"></div>`);
        row.append(a, b);
        return row;
    }

    async function refresh() {
        if (busy) return;
        busy = true; render();
        const get = (method) => frappe.xcall(method, {}, "GET").catch(() => null);
        const [m, o, a, t] = await Promise.all([get("stemic_control.api.dashboard_metrics"), get("stemic_control.dashboard.overview"),
                                                get("stemic_control.api.operations_queue"), get("stemic_control.etims.compliance_overview")]);
        metrics = m; ov = o; attention = a; tax = t;
        loadError = !m && !o;
        busy = false; render();
    }
    stemic_control.trigger_refresh = refresh;
    page.set_secondary_action(__("Refresh"), refresh, "refresh");
    refresh();
};
