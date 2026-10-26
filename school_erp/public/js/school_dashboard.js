// Shared helpers for the School dashboards (Management Dashboard, Staff Room).
frappe.provide("school_dash");

(function () {
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	school_dash.esc = esc;

	school_dash.is_dark = () => document.documentElement.getAttribute("data-theme") === "dark";

	// Validated categorical slots (light / dark steps of the same hues)
	school_dash.series = () => (school_dash.is_dark() ? ["#3987e5", "#d95926"] : ["#2a78d6", "#eb6834"]);

	school_dash.money = (v, currency) => format_currency(v || 0, currency, 0);

	// 1,250,000 -> 1.25M ; keeps tiles readable on phones
	school_dash.short = (v) => {
		v = Number(v || 0);
		const a = Math.abs(v);
		if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 1 : 2).replace(/\.0+$/, "") + "M";
		if (a >= 1e4) return Math.round(v / 1e3) + "K";
		return format_number(v, null, 0);
	};

	school_dash.go = (route) => {
		if (!route) return;
		const [kind, ...rest] = route;
		if (kind === "Form" && rest[1] === "new") {
			frappe.route_options = null;
			frappe.new_doc(rest[0]);
		} else if (kind === "List" && rest[1]) {
			frappe.route_options = rest[1];
			frappe.set_route("List", rest[0]);
		} else {
			frappe.route_options = null;
			frappe.set_route(kind, ...rest);
		}
	};

	school_dash.card = (title, body, opts = {}) => `
		<div class="sd-card ${opts.cls || ""}">
			<div class="sd-card-head">
				<div><div class="sd-card-title">${esc(title)}</div>${opts.sub ? `<div class="sd-card-sub">${esc(opts.sub)}</div>` : ""}</div>
				${opts.link ? `<span class="sd-link" data-route='${esc(JSON.stringify(opts.link.route))}'>${esc(opts.link.label)}</span>` : ""}
			</div>
			${body}
		</div>`;

	school_dash.kpi = ({ label, value, of, foot, bar, route, title }) => `
		<div class="sd-card sd-kpi" ${route ? `data-route='${esc(JSON.stringify(route))}'` : ""} title="${esc(title || "")}">
			<div class="sd-kpi-label">${esc(label)}</div>
			<div class="sd-kpi-value">${esc(value)}${of != null ? `<span class="sd-kpi-of"> / ${esc(of)}</span>` : ""}</div>
			${foot ? `<div class="sd-kpi-foot">${foot}</div>` : ""}
			${bar != null ? `<div class="sd-bar" role="img" aria-label="${Math.round(Number(bar) || 0)}%"><span style="width:${Math.max(0, Math.min(100, Number(bar) || 0))}%"></span></div>` : ""}
		</div>`;

	const ICON = { good: "✓", warning: "!", serious: "!", critical: "‼", muted: "•" };
	school_dash.pill = (tone, label) => `<span class="sd-pill ${tone}"><span aria-hidden="true">${ICON[tone] || "•"}</span>${esc(label)}</span>`;

	school_dash.barlist = (rows, fmt) => {
		if (!rows || !rows.length) return `<div class="sd-empty">${__("Nothing recorded yet")}</div>`;
		const max = Math.max(...rows.map((r) => r.value || 0)) || 1;
		return `<div class="sd-barlist">${rows.map((r) => `
			<div class="sd-bl-row" title="${esc(r.label)}: ${esc(fmt ? fmt(r.value) : r.value)}">
				<div class="sd-bl-label">${esc(r.label || __("Not set"))}</div>
				<div class="sd-bl-track"><div class="sd-bl-fill" style="width:${((r.value || 0) / max) * 100}%"></div></div>
				<div class="sd-num">${esc(fmt ? fmt(r.value) : r.value)}</div>
			</div>`).join("")}</div>`;
	};

	school_dash.chart = (el, type, labels, datasets, opts = {}) => {
		if (!el || !labels || !labels.length) return;
		el.innerHTML = "";
		return new frappe.Chart(el, {
			type,
			height: opts.height || 230,
			data: { labels, datasets },
			colors: opts.colors || school_dash.series(),
			axisOptions: { xIsSeries: type === "line" ? 1 : 0, shortenYAxisNumbers: 1, xAxisMode: "tick", yAxisMode: "span" },
			lineOptions: { regionFill: 1, hideDots: 1, spline: 0 },
			barOptions: { spaceRatio: 0.45 },
			tooltipOptions: { formatTooltipY: (v) => (opts.money ? school_dash.money(v, opts.currency) : format_number(v)) },
		});
	};

	// clicks on [data-route] anywhere inside a dashboard
	school_dash.bind_routes = ($root) => {
		$root.on("click", "[data-route]", function (e) {
			e.preventDefault();
			try { school_dash.go(JSON.parse(this.getAttribute("data-route"))); } catch (err) { /* ignore */ }
		});
	};

	// Used by forms on a Frappe Workflow: ask why before "Reject", store it, then let the workflow continue
	school_dash.reason_before_reject = (frm, field) => {
		if (frm.selected_workflow_action !== "Reject") return Promise.resolve();
		return new Promise((resolve, reject) => {
			let done = false;
			const d = frappe.prompt(
				{ fieldname: "reason", label: __("Reason for rejecting"), fieldtype: "Small Text", reqd: 1, default: frm.doc[field] },
				(v) => frappe.call({
					method: "school_erp.setup.workflows.save_rejection_reason",
					args: { doctype: frm.doctype, name: frm.docname, reason: v.reason },
				}).then(() => { done = true; frm.doc[field] = v.reason; resolve(); }, reject),
				__("Reject"), __("Reject"),
			);
			d.onhide = () => { if (!done) setTimeout(() => !done && reject(), 300); };
		});
	};

	school_dash.notices = (rows, { management = false } = {}) => {
		if (!rows || !rows.length) return `<div class="sd-empty">${__("No notices right now")}</div>`;
		return rows.map((n) => {
			const tone = n.priority === "Urgent" ? "critical" : n.priority === "Important" ? "warning" : null;
			const reach = management && n.audience_count
				? `<span>${__("{0} of {1} acknowledged", [n.acknowledged_count || 0, n.audience_count])}</span>` : "";
			const ack = !management
				? (n.acknowledged ? school_dash.pill("good", __("Acknowledged")) : `<button class="sd-ack" data-ack="${esc(n.name)}">${__("Got it")}</button>`)
				: "";
			return `<div class="sd-notice ${n.priority === "Urgent" ? "urgent" : n.priority === "Important" ? "important" : ""}">
				<div class="sd-notice-title">${n.pinned ? "📌 " : ""}<span class="sd-link" style="font-size:14px;color:inherit" data-route='${esc(JSON.stringify(["Form", "School Notice", n.name]))}'>${esc(n.title)}</span>
					${tone ? school_dash.pill(tone, __(n.priority)) : ""}</div>
				<div class="sd-notice-text">${esc(n.text)}</div>
				<div class="sd-notice-meta"><span>${esc(n.date)}${n.by ? " · " + esc(n.by) : ""}</span><span>${esc(__(n.audience))}</span>${reach}${ack}</div>
			</div>`;
		}).join("");
	};
})();
