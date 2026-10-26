// Management Dashboard: one screen for the Head Teacher, Bursar and admins.
frappe.pages["management-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Management Dashboard"), single_column: true });
	const dash = new ManagementDashboard(page, $(wrapper).find(".layout-main-section"));
	wrapper.dashboard = dash;
	page.set_primary_action(__("Post a Notice"), () => frappe.new_doc("School Notice"), "add");
	page.set_secondary_action(__("Refresh"), () => dash.load(), "refresh");
	page.add_menu_item(__("Staff Room"), () => frappe.set_route("staff-room"));
	page.add_menu_item(__("School Settings"), () => frappe.set_route("Form", "School Settings"));
};

frappe.pages["management-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.dashboard && wrapper.dashboard.loaded_at && Date.now() - wrapper.dashboard.loaded_at > 60000) wrapper.dashboard.load();
};

class ManagementDashboard {
	constructor(page, $parent) {
		this.page = page;
		this.$root = $(`<div class="sd"><div class="sd-grid sd-kpis">${'<div class="sd-skeleton"></div>'.repeat(4)}</div></div>`).appendTo($parent);
		school_dash.bind_routes(this.$root);
		this.$root.on("change", ".sd-term", (e) => this.load(e.target.value));
		this.loading = false;
		this.load();
		frappe.realtime.on("paybill_unmatched", () => this.load(this.term));
	}

	load(term) {
		if (this.loading) return;
		this.loading = true;
		frappe.call("school_erp.api.dashboard.management", { term: term || this.term }).then(({ message }) => {
			this.data = message;
			this.term = message.term;
			this.loaded_at = Date.now();
			this.render();
		}).catch(() => frappe.show_alert({message: __("Unable to refresh management dashboard"), indicator: "red"}))
			.finally(() => { this.loading = false; });
	}

	render() {
		const d = this.data, S = school_dash, cur = d.currency, m = new Set(d.modules);
		const money = (v) => S.money(v, cur);
		const html = [];

		html.push(`
			<div class="sd-hero">
				<div><h2>${S.esc(d.school)}</h2><div class="sd-card-sub">${S.esc(d.today)}</div></div>
				<div class="sd-hero-tools">
					${d.license.status !== "valid" && d.license.status !== "unlicensed" ? S.pill(d.license.status === "grace" ? "warning" : "critical", d.license.message) : ""}
					${d.terms.length ? `<select class="sd-term" aria-label="${__("Term")}">${d.terms.map((t) => `<option ${t === d.term ? "selected" : ""}>${S.esc(t)}</option>`).join("")}</select>` : ""}
				</div>
			</div>`);

		// ---------------------------------------------------------- KPI tiles
		const k = [];
		k.push(S.kpi({
			label: __("Students"), value: format_number(d.students.total, null, 0), route: ["List", "Student", { status: "Active" }],
			foot: __("{0} girls · {1} boys", [d.students.girls, d.students.boys]) + (d.students.new_this_term ? ` · +${d.students.new_this_term} ${__("new")}` : ""),
		}));
		if (d.fees) {
			const f = d.fees;
			k.push(S.kpi({
				label: __("Collected this term"), value: S.short(f.collected), title: money(f.collected), route: ["query-report", "Fee Collection"],
				foot: f.rate != null ? __("{0}% of {1} billed", [f.rate, S.short(f.billed)]) : __("Not billed yet"), bar: f.rate,
			}));
			k.push(S.kpi({
				label: __("Outstanding this term"), value: S.short(f.outstanding), title: money(f.outstanding), route: ["query-report", "Fee Balances"],
				foot: __("{0} students owe · {1} all terms", [f.defaulters, S.short(f.all_outstanding)]),
			}));
			k.push(S.kpi({
				label: __("Collected today"), value: S.short(f.today), title: money(f.today), route: ["List", "Fee Payment", { posting_date: frappe.datetime.get_today() }],
				foot: __("{0} payments · {1} this week", [f.today_count, S.short(f.week)]),
			}));
		}
		if (d.staff) {
			k.push(S.kpi({
				label: __("Staff in today"), value: `${d.staff.present} / ${d.staff.total}`,
				route: ["query-report", "Staff On Leave"], foot: d.staff.on_leave.length ? __("{0} on leave", [d.staff.on_leave.length]) : __("Nobody on leave"),
				bar: d.staff.total ? (d.staff.present / d.staff.total) * 100 : null,
			}));
		}
		if (d.transport) {
			const t = d.transport;
			k.push(S.kpi({
				label: __("Drivers checked in"), value: `${t.checked_in} / ${t.routes}`,
				route: ["query-report", "Driver Check-in Register"], foot: t.issues ? S.pill("serious", __("{0} with vehicle issues", [t.issues])) : __("No vehicle issues"),
				bar: t.routes ? (t.checked_in / t.routes) * 100 : null,
			}));
		}
		if (d.welfare) {
			k.push(S.kpi({
				label: __("Open complaints"), value: d.welfare.open_complaints, route: ["List", "Complaint", { status: "Open" }],
				foot: d.welfare.urgent_complaints ? S.pill("critical", __("{0} urgent / high", [d.welfare.urgent_complaints])) : __("{0} discipline cases this week", [d.welfare.incidents_week]),
			}));
		}
		if (d.expenses) {
			k.push(S.kpi({
				label: __("Expenses this month"), value: S.short(d.expenses.month_spent), title: money(d.expenses.month_spent), route: ["query-report", "Expense Register"],
				foot: d.expenses.pending_first + d.expenses.pending_final ? __("{0} awaiting approval ({1})", [d.expenses.pending_first + d.expenses.pending_final, S.short(d.expenses.pending_amount)]) : __("Nothing awaiting approval"),
			}));
		}
		html.push(`<div class="sd-grid sd-kpis">${k.join("")}</div>`);

		// ---------------------------------------------------------- attention + collections trend
		const att = d.attention.length
			? `<div class="sd-list">${d.attention.map((a) => `
				<div class="sd-row clickable" data-route='${S.esc(JSON.stringify(a.route))}'>
					<div class="sd-row-main">${S.esc(a.label)}${a.hint ? `<small>${S.esc(a.hint)}</small>` : ""}</div>
					${S.pill(a.tone, String(a.count))}
				</div>`).join("")}</div>`
			: `<div class="sd-allclear">${S.pill("good", __("All clear"))}<span style="color:var(--text-muted);font-weight:400">${__("Nothing needs your attention right now.")}</span></div>`;
		html.push(`<div class="sd-grid sd-two">
			${S.card(__("Needs your attention"), att, { sub: __("Click an item to act on it") })}
			${d.fees ? S.card(__("Fee collections, last 4 weeks"), `<div class="sd-chart" data-chart="daily"></div>`, { sub: money(d.fees.daily.values.reduce((a, b) => a + b, 0)), link: { label: __("Collection report"), route: ["query-report", "Fee Collection"] } }) : S.card(__("Notice board"), S.notices(d.notices, { management: true }))}
		</div>`);

		// ---------------------------------------------------------- money charts
		if (d.cashflow || (d.fees && d.fees.by_class.length)) {
			const legend = "";  // Frappe Charts draws the legend for multi-series charts
			html.push(`<div class="sd-grid sd-halves">
				${d.cashflow ? S.card(d.expenses ? __("Fees collected vs expenses") : __("Fees collected by month"), legend + `<div class="sd-chart" data-chart="cashflow"></div>`, { link: { label: __("Details"), route: ["query-report", "Income vs Expenses"] } }) : ""}
				${d.fees ? S.card(__("Outstanding by class"), S.barlist(d.fees.by_class.map((r) => ({ label: r.label, value: r.value })), (v) => S.short(v)), { sub: this.term || "", link: { label: __("Who owes"), route: ["query-report", "Fee Balances"] } }) : ""}
			</div>`);
		}

		// ---------------------------------------------------------- today: staff, duty, transport, welfare
		const today_cards = [];
		if (d.staff) {
			const away = d.staff.on_leave.length
				? `<table class="sd-table"><tr><th>${__("Away")}</th><th>${__("Reliever")}</th><th class="r">${__("Back")}</th></tr>${d.staff.on_leave.map((a) => `
					<tr><td><span class="sd-link" style="color:inherit" data-route='${S.esc(JSON.stringify(["Form", "Leave Application", a.name]))}'>${S.esc(a.staff_name)}</span><br><small style="color:var(--text-muted)">${S.esc(a.leave_type)}</small></td>
					<td>${S.esc(a.reliever_name || "—")}</td><td class="r">${S.esc(a.back)}</td></tr>`).join("")}</table>`
				: `<div class="sd-empty">${__("Everyone is in today")}</div>`;
			const duty = d.staff.duty.length
				? d.staff.duty.map((x) => `<div class="sd-row ${x.report ? "clickable" : ""}" ${x.report ? `data-route='${S.esc(JSON.stringify(["Form", "Duty Report", x.report]))}'` : ""}>
					<div class="sd-row-main">${S.esc(x.staff)}<small>${__("Teacher on duty")}</small></div>
					${x.status === "Submitted" ? S.pill(x.rating === "Poor" ? "serious" : "good", __("Report in") + (x.rating ? ` · ${__(x.rating)}` : "")) : S.pill("muted", __(x.status))}
				</div>`).join("")
				: `<div class="sd-empty">${__("No duty roster for today")}</div>`;
			today_cards.push(S.card(__("Staff away today"), away, { link: { label: __("Leave balance"), route: ["query-report", "Leave Balance"] } }));
			today_cards.push(S.card(__("Teacher on duty"), `<div class="sd-list">${duty}</div>`, { link: { label: __("Register"), route: ["query-report", "Duty Reports Register"] } }));
		}
		if (d.transport && d.transport.rows.length) {
			const rows = d.transport.rows.map((r) => `<tr class="${r.log ? "" : ""}">
				<td>${S.esc(r.route)}<br><small style="color:var(--text-muted)">${S.esc(r.driver || "")}</small></td>
				<td class="r">${r.checked_in ? (r.issues ? S.pill("serious", r.checked_in + " · " + __("issues")) : S.pill("good", r.checked_in)) : S.pill("critical", __("Not in"))}</td></tr>`).join("");
			today_cards.push(S.card(__("Morning check-ins"), `<table class="sd-table">${rows}</table>`, { link: { label: __("Register"), route: ["query-report", "Driver Check-in Register"] } }));
		}
		if (today_cards.length) {
			html.push(`<div class="sd-grid ${today_cards.length >= 3 ? "sd-thirds" : today_cards.length === 2 ? "sd-halves" : ""}">${today_cards.join("")}</div>`);
		}

		// ---------------------------------------------------------- students & discipline, then notices
		const people = [S.card(__("Students by class"), S.barlist(d.students.by_class), { sub: __("{0} boarders", [d.students.boarders]), link: { label: __("Enrolment report"), route: ["query-report", "Class Enrolment"] } })];
		if (d.welfare) {
			people.push(S.card(__("Discipline this term"), S.barlist(d.welfare.by_category), {
				sub: d.welfare.serious_open ? __("{0} serious cases still open", [d.welfare.serious_open]) : "",
				link: { label: __("Summary"), route: ["query-report", "Discipline Summary"] },
			}));
		}
		html.push(`<div class="sd-grid ${people.length === 2 ? "sd-halves" : ""}" style="margin-bottom:var(--sd-gap)">${people.join("")}</div>`);
		if (d.fees) {
			html.push(S.card(__("Notice board"), S.notices(d.notices, { management: true }), { sub: __("What staff are seeing, and who has acknowledged it"), link: { label: __("All notices"), route: ["List", "School Notice"] } }));
		}

		this.$root.html(html.join(""));

		if (d.fees) S.chart(this.$root.find('[data-chart="daily"]')[0], "line", d.fees.daily.labels, [{ name: __("Collected"), values: d.fees.daily.values }], { money: true, currency: cur, colors: [S.series()[0]] });
		if (d.cashflow) {
			const ds = [{ name: __("Fees collected"), values: d.cashflow.collected }];
			if (d.expenses) ds.push({ name: __("Expenses"), values: d.cashflow.expenses });
			S.chart(this.$root.find('[data-chart="cashflow"]')[0], "bar", d.cashflow.labels, ds, { money: true, currency: cur });
		}
	}
}
