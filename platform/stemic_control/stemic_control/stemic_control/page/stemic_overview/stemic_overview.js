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
        agents: [
            ["total_agents","Total Agents","SaaS Agent",{},"Registered agents"],
            ["active_agents","Active Agents","SaaS Agent",{status:"Active"},"Currently enabled"],
            ["referred_schools","Referred Schools","SaaS Tenant",null,"Attributed schools"],
            ["referred_active_schools","Active Referrals","SaaS Tenant",null,"Active tenant records"]
        ]
    };
    let selected = "home";
    let metrics = null;
    let busy = false;
    let operations = [];
    let loadError = false;
    const tabs = [["home","Overview"],["schools","Schools"],["billing","Billing"],["agents","Agents"]];

    function render() {
        root.replaceChildren();
        const description = document.createElement("p");
        description.className = "stemic-intro";
        description.textContent = __("Manage schools, subscriptions and provisioning from one control plane.");
        root.append(description);
        const shortcuts = document.createElement("div");
        shortcuts.className = "stemic-quick-actions";
        for (const [label, action] of [
            [__("New School"), () => frappe.new_doc("SaaS Tenant")],
            [__("All Schools"), () => frappe.set_route("List", "SaaS Tenant")],
            [__("Provisioning Jobs"), () => frappe.set_route("List", "SaaS Provisioning Job")],
            [__("Domains"), () => frappe.set_route("List", "SaaS Domain")],
            [__("Subscriptions"), () => frappe.set_route("List", "SaaS Subscription")],
            [__("Agents"), () => frappe.set_route("List", "SaaS Agent")]
        ]) {
            const button = document.createElement("button");
            button.className = "btn btn-default btn-sm";
            button.type = "button";
            button.textContent = label;
            button.addEventListener("click", action);
            shortcuts.append(button);
        }
        root.append(shortcuts);
        if (loadError) {
            const message = document.createElement("p");
            message.className = "alert alert-warning";
            message.setAttribute("role", "alert");
            message.textContent = __("Dashboard metrics could not be loaded. Select Refresh to try again.");
            root.append(message);
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
        const section = document.createElement("div");
        section.className = "stemic-card-grid";
        for (const [key,label,doctype,filters,helper] of groups[selected]) {
            const card = document.createElement("button");
            card.type = "button";
            card.className = "stemic-kpi-card";
            const heading = document.createElement("span");
            heading.className = "stemic-kpi-label";
            heading.textContent = __(label);
            const value = document.createElement("strong");
            value.className = "stemic-kpi-value";
            value.textContent = busy || !metrics ? "—" : String(metrics[selected][key] ?? "—");
            const hint = document.createElement("span");
            hint.className = "stemic-kpi-hint";
            hint.textContent = __(helper);
            card.append(heading,value,hint);
            if (filters !== null) {
                card.addEventListener("click", () => {
                    frappe.route_options = filters;
                    frappe.set_route("List",doctype);
                });
            } else {
                card.disabled = true;
                card.title = __("A matching filtered list is not available yet");
            }
            section.append(card);
        }
        root.append(section);
        if (selected === "home") {
            const heading = document.createElement("h3");
            heading.className = "stemic-operations-heading";
            heading.textContent = __("Needs Attention");
            root.append(heading);
            const feed = document.createElement("div");
            feed.className = "stemic-operations-feed";
            if (!operations.length) {
                const empty = document.createElement("p");
                empty.className = "text-muted";
                empty.textContent = __("No provisioning, DNS or past-due exceptions currently listed.");
                feed.append(empty);
            }
            for (const item of operations) {
                const action = document.createElement("button");
                action.type = "button";
                action.className = "stemic-operations-item";
                const name = document.createElement("strong");
                name.textContent = item.label;
                const detail = document.createElement("span");
                detail.textContent = item.name;
                const indicator = document.createElement("span");
                indicator.className = item.severity === "critical" ? "stemic-risk-critical" : "stemic-risk-warning";
                indicator.textContent = item.severity === "critical" ? __("Requires action") : __("Review");
                action.append(name, detail, indicator);
                action.addEventListener("click", () => frappe.set_route("Form", item.doctype, item.name));
                feed.append(action);
            }
            root.append(feed);
        }
        const note = document.createElement("p");
        note.className = "stemic-note";
        note.textContent = __("Figures are counts from admin records, not independently verified infrastructure health or collected revenue.");
        root.append(note);
    }
    async function refresh() {
        if (busy) return;
        busy = true; render();
        try {
            const response = await frappe.call({ method: "stemic_control.api.dashboard_metrics", type: "GET" });
            metrics = response.message;
            loadError = false;
            const queue = await frappe.call({method: "stemic_control.api.operations_queue", type: "GET"});
            operations = queue.message?.items || [];
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
