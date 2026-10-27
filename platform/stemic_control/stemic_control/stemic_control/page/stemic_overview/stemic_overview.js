frappe.pages["stemic-overview"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper, title: __("Stemic Schools"), single_column: true
    });
    page.set_primary_action(__("New School"), () => frappe.new_doc("SaaS Tenant"), "add");
    const root = document.createElement("div");
    root.className = "stemic-overview";
    wrapper.querySelector(".layout-main-section").appendChild(root);

    const groups = {
        home: [
            ["total_schools", "Total Schools", "SaaS Tenant", {}, "Registered school tenants"],
            ["active_schools", "Active Schools", "SaaS Tenant", {status:"Active"}, "Administratively active"],
            ["active_subscriptions", "Active Subscriptions", "SaaS Subscription", {status:"Active"}, "Current subscription records"],
            ["pending_provisioning", "Pending Provisioning", "SaaS Provisioning Job", {status:["in",["Queued","Running"]]}, "Awaiting site operations"]
        ],
        schools: [
            ["total_schools","Total Schools","SaaS Tenant",{},"Registered"],
            ["active_schools","Active Schools","SaaS Tenant",{status:"Active"},"Operational status not verified"],
            ["trial_schools","Trial Schools","SaaS Subscription",{status:"Trial"},"Trial subscriptions"],
            ["pending_provisioning","Pending Provisioning","SaaS Provisioning Job",{status:["in",["Queued","Running"]]},"Queued or running jobs"],
            ["failed_provisioning","Failed Provisioning","SaaS Provisioning Job",{status:"Failed"},"Needs investigation"],
            ["pending_domains","Pending Domains","SaaS Domain",{status:"Pending Verification"},"DNS ownership outstanding"]
        ],
        billing: [
            ["active_subscriptions","Active Subscriptions","SaaS Subscription",{status:"Active"},"Billing status only"],
            ["trial_subscriptions","Trial Subscriptions","SaaS Subscription",{status:"Trial"},"In evaluation"],
            ["past_due","Past Due","SaaS Subscription",{status:"Past Due"},"Requires attention"],
            ["expiring_soon","Expiring in 30 Days","SaaS Subscription",null,"Upcoming renewals"]
        ],
        tax: [
            ["draft","Needs Review","SaaS eTIMS Invoice",{status:"Draft"},"Prepared invoices awaiting finance review"],
            ["ready","Ready for Integration","SaaS eTIMS Invoice",{status:"Ready"},"Not yet submitted to KRA"],
            ["pending","Pending Submission","SaaS eTIMS Invoice",{status:"Pending Submission"},"Awaiting provider processing"],
            ["submitted","Submitted to KRA","SaaS eTIMS Invoice",{status:"Submitted"},"Use provider acknowledgements, not local assumptions"],
            ["rejected","Rejected","SaaS eTIMS Invoice",{status:"Rejected"},"Investigate provider error"],
            ["profiles","Enabled Tax Profiles","SaaS Tax Profile",{enabled:1},"School seller tax configurations"]
        ],
        agents: [
            ["total_agents","Total Agents","SaaS Agent",{},"Registered agents"],
            ["active_agents","Active Agents","SaaS Agent",{status:"Active"},"Currently enabled"],
            ["referred_schools","Referred Schools","SaaS Tenant",null,"Attributed schools"],
            ["referred_active_schools","Active Referrals","SaaS Tenant",null,"Active tenant records"]
        ]
    };
    let selected = "home";
    let metrics = null;
    let tax = null;
    let busy = false;
    let loadError = false;
    let attention = null;  // operations_queue: what needs an operator (null = not loaded)
    const tabs = [["home","Overview"],["schools","Schools"],["billing","Billing"],["agents","Agents"],["tax","Kenya Tax & eTIMS"]];

    function render() {
        root.replaceChildren();
        const description = document.createElement("p");
        description.className = "stemic-intro";
        description.textContent = __("Manage schools, subscriptions and provisioning from one control plane.");
        root.append(description);
        if (loadError) {
            const warning = document.createElement("div");
            warning.className = "alert alert-warning";
            warning.setAttribute("role", "alert");
            warning.textContent = __("Metrics could not be loaded. Use Refresh to try again.");
            root.append(warning);
        }
        const nav = document.createElement("div");
        nav.className = "stemic-tabs";
        nav.setAttribute("role","tablist");
        for (const [id,label] of tabs) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "stemic-tab" + (selected === id ? " selected" : "");
            btn.textContent = __(label);
            btn.setAttribute("role","tab");
            btn.setAttribute("aria-selected", String(selected === id));
            btn.addEventListener("click", () => { selected = id; render(); });
            nav.append(btn);
        }
        root.append(nav);
        if (selected === "tax") {
            const action = document.createElement("button");
            action.type = "button";
            action.className = "btn btn-default btn-sm stemic-tab-action";
            action.textContent = __("Configure School Tax Profile");
            action.addEventListener("click", () => frappe.set_route("List", "SaaS Tax Profile"));
            root.append(action);
        }
        const section = document.createElement("div");
        section.className = "stemic-card-grid";
        for (const [key,label,doctype,filters,helper] of groups[selected]) {
            const card = document.createElement("button");
            card.type = "button";
            card.className = "stemic-kpi-card";
            card.setAttribute("aria-label", __(label) + ": " + ((selected === "tax" ? tax?.[key] : metrics?.[selected]?.[key]) ?? __("Not available")));
            const heading = document.createElement("span");
            heading.className = "stemic-kpi-label";
            heading.textContent = __(label);
            const value = document.createElement("strong");
            value.className = "stemic-kpi-value";
            value.textContent = busy || !metrics ? "—" : String((selected === "tax" ? tax?.[key] : metrics?.[selected]?.[key]) ?? "—");
            const hint = document.createElement("span");
            hint.className = "stemic-kpi-hint";
            hint.textContent = __(helper);
            card.append(heading,value,hint);
            if (filters !== null) {
                card.addEventListener("click", () => {
                    frappe.route_options = {...filters};
                    frappe.set_route("List",doctype);
                });
            } else {
                card.type = "button";
                card.setAttribute("aria-disabled", "true");
                card.title = __("Summary only — detailed report not yet available");
            }
            section.append(card);
        }
        root.append(section);
        if (selected === "home") root.append(attention_feed());
        if (selected === "tax") {
            const disclaimer = document.createElement("p");
            disclaimer.className = "stemic-note";
            disclaimer.textContent = __("Preparation only. This integration has not submitted an invoice to KRA. Configure a certified OSCU/VSCU pathway and complete KRA testing before enabling live submissions.");
            root.append(disclaimer);
        }
        const note = document.createElement("p");
        note.className = "stemic-note";
        note.textContent = __("Figures are counts from admin records, not independently verified infrastructure health or collected revenue.");
        root.append(note);
    }
    // "Needs attention": a few newest items per group, each naming the school and opening the record to act on
    function attention_feed() {
        const wrap = document.createElement("section");
        wrap.className = "stemic-attention";
        const heading = document.createElement("h3");
        heading.className = "stemic-attention-title";
        heading.textContent = __("Needs attention");
        wrap.append(heading);
        if (!attention) {
            const note = document.createElement("p");
            note.className = "text-muted";
            note.textContent = busy ? __("Loading...") : __("Could not load the attention list. Use Refresh to try again.");
            wrap.append(note);
            return wrap;
        }
        const open = attention.groups.filter((g) => g.count);
        if (!open.length) {
            const clear = document.createElement("p");
            clear.className = "stemic-attention-clear";
            clear.textContent = __("Nothing needs attention: no failed sites, overdue payments, pending domains or sites being created.");
            wrap.append(clear);
            return wrap;
        }
        const grid = document.createElement("div");
        grid.className = "stemic-attention-grid";
        for (const group of open) {
            const box = document.createElement("div");
            box.className = `stemic-attention-group ${group.severity}`;
            const head = document.createElement("div");
            head.className = "stemic-attention-head";
            const title = document.createElement("strong");
            title.textContent = `${__(group.label)} (${group.count})`;
            const all = document.createElement("button");
            all.type = "button";
            all.className = "btn btn-link btn-xs";
            all.textContent = __("View all");
            all.addEventListener("click", () => {
                frappe.route_options = { ...group.filters };
                frappe.set_route("List", group.doctype);
            });
            head.append(title, all);
            box.append(head);
            for (const item of group.items) {
                const row = document.createElement("button");
                row.type = "button";
                row.className = "stemic-attention-item";
                const school = document.createElement("strong");
                school.textContent = item.school;
                const detail = document.createElement("span");
                detail.textContent = item.detail;
                const when = document.createElement("small");
                when.textContent = frappe.datetime.prettyDate(item.modified);
                row.append(school, detail, when);
                row.addEventListener("click", () => frappe.set_route("Form", item.doctype, item.name));
                box.append(row);
            }
            grid.append(box);
        }
        wrap.append(grid);
        return wrap;
    }
    async function refresh() {
        if (busy) return;
        busy = true; render();
        try {
            const response = await frappe.call({ method: "stemic_control.api.dashboard_metrics", type: "GET" });
            metrics = response.message;
            loadError = false;
            try {  // the KPI cards still work if this list cannot load
                attention = (await frappe.call({ method: "stemic_control.api.operations_queue", type: "GET" })).message;
            } catch (e) {
                attention = null;
            }
            try {
                const taxReply = await frappe.call({method:"stemic_control.etims.compliance_overview", type:"GET"});
                tax = taxReply.message;
            } catch (error) {
                tax = null;
            }
        } catch (error) {
            loadError = true;
            frappe.msgprint({title: __("Dashboard unavailable"), message: __("Unable to load platform metrics."), indicator: "red"});
        } finally {
            busy = false; render();
        }
    }
    page.set_secondary_action(__("Refresh"), refresh, "refresh");
    refresh();
};
