// Staff Room: every teacher's (and staff member's) home screen.
frappe.pages["staff-room"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Staff Room"), single_column: true });
	wrapper.room = new StaffRoom(page, $(wrapper).find(".layout-main-section"));
	page.set_secondary_action(__("Refresh"), () => wrapper.room.load(), "refresh");
};

frappe.pages["staff-room"].on_page_show = function (wrapper) {
	if (wrapper.room && wrapper.room.loaded_at && Date.now() - wrapper.room.loaded_at > 60000) wrapper.room.load();
};

class StaffRoom {
	constructor(page, $parent) {
		this.page = page;
		this.$root = $(`<div class="sd"><div class="sd-skeleton" style="height:140px;margin-bottom:16px"></div></div>`).appendTo($parent);
		school_dash.bind_routes(this.$root);
		this.$root.on("click", "[data-ack]", (e) => this.acknowledge(e.currentTarget));
		this.load();
	}

	load() {
		frappe.call("school_erp.api.dashboard.staff_room").then(({ message }) => {
			this.data = message;
			this.loaded_at = Date.now();
			this.render();
		});
	}

	acknowledge(btn) {
		const name = btn.getAttribute("data-ack");
		btn.disabled = true;
		frappe.call("school_erp.school.doctype.school_notice.school_notice.acknowledge", { name }).then(() => {
			$(btn).replaceWith(school_dash.pill("good", __("Acknowledged")));
		});
	}

	render() {
		const d = this.data, S = school_dash, m = new Set(d.modules);
		if (d.is_management) {
			this.page.clear_primary_action();
			this.page.set_primary_action(__("Management Dashboard"), () => frappe.set_route("management-dashboard"));
		}
		const html = [];

		// ---------------------------------------------------------- welcome + quick actions
		const sub = [d.today, d.term, d.designation].filter(Boolean).map(S.esc).join(" · ");
		const actions = (d.actions || []).map((a, i) => `<span class="sd-action ${i === 0 ? "primary" : ""}" data-route='${S.esc(JSON.stringify(a.route))}'>${S.esc(a.label)}</span>`).join("");
		let banner = "";
		if (d.relieving && d.relieving.some((r) => r.now)) {
			const r = d.relieving.find((x) => x.now);
			banner = `<div style="margin-top:12px">${S.pill("warning", __("You are relieving {0} today ({1})", [r.staff_name, r.period]))}</div>`;
		}
		if (d.duty && d.duty.on_duty_now && !d.duty.submitted) {
			banner += `<div style="margin-top:8px">${S.pill("warning", __("You are {0} this week. Remember today's duty report.", [d.duty.role]))}</div>`;
		}
		if (d.staff_type === "Driver" && "checkin" in d) {
			banner += `<div style="margin-top:8px">${d.checkin && d.checkin.docstatus === 1
				? S.pill(d.checkin.has_issues ? "serious" : "good", d.checkin.has_issues ? __("Checked in, issues reported") : __("Checked in for today"))
				: S.pill("critical", __("Morning check-in not done"))}</div>`;
		}
		if (!d.staff) {
			banner += `<div style="margin-top:8px">${S.pill("muted", __("Your login is not linked to a Staff Member yet. Ask the school office."))}</div>`;
		}
		html.push(`<div class="sd-welcome"><h2>${S.esc(d.greeting)}</h2><div class="sd-card-sub">${sub}</div>${banner}<div class="sd-actions">${actions}</div></div>`);

		// ---------------------------------------------------------- left column
		const left = [];
		if (d.lessons) {
			const lessons = d.lessons.length
				? d.lessons.map((l) => `<div class="sd-lesson ${l.state}">
					<div class="sd-time">${S.esc(l.time)}<br><small>${S.esc(l.period_name)}</small></div>
					<div class="sd-subj">${S.esc(l.subject || __("Lesson"))}<small>${S.esc(l.stream)}${l.room ? " · " + S.esc(l.room) : ""}</small></div>
					<div>${l.state === "now" ? S.pill("good", __("Now")) : l.state === "next" ? S.pill("muted", __("Next")) : ""}</div>
				</div>`).join("")
				: `<div class="sd-empty">${__("No lessons on your timetable today")}</div>`;
			left.push(S.card(__("Your lessons today"), lessons, { sub: __("{0} lessons this week", [d.week_lessons || 0]), link: { label: __("Timetables"), route: ["List", "Timetable"] } }));
		}
		if (d.my_classes && d.my_classes.length) {
			const rows = d.my_classes.map((c) => `<tr><td><span class="sd-link" style="color:inherit" data-route='${S.esc(JSON.stringify(["List", "Student", { stream: c.stream, status: "Active" }]))}'>${S.esc(c.stream)}</span></td>
				<td class="r">${c.students}</td><td class="r">${c.girls}</td><td class="r">${c.boys}</td>${"incidents" in c ? `<td class="r">${c.incidents}</td>` : ""}</tr>`).join("");
			const inc = "incidents" in d.my_classes[0];
			left.push(S.card(__("Your class"), `<table class="sd-table"><tr><th>${__("Stream")}</th><th class="r">${__("Students")}</th><th class="r">${__("Girls")}</th><th class="r">${__("Boys")}</th>${inc ? `<th class="r">${__("Incidents")}</th>` : ""}</tr>${rows}</table>`, { sub: __("You are the class teacher") }));
		}
		left.push(S.card(__("Notice board"), S.notices(d.notices), { link: { label: __("All notices"), route: ["List", "School Notice"] } }));

		// ---------------------------------------------------------- right column
		const right = [];
		if (d.duty) {
			const body = `<div class="sd-row"><div class="sd-row-main">${S.esc(d.duty.role)}<small>${S.esc(d.duty.period)}</small></div>
				${d.duty.on_duty_now ? (d.duty.submitted ? S.pill("good", __("Today's report sent")) : S.pill("warning", __("Report due today"))) : S.pill("muted", __("Upcoming"))}</div>
				${d.duty.on_duty_now && !d.duty.submitted ? `<div class="sd-actions"><span class="sd-action primary" data-route='${S.esc(JSON.stringify(["Form", "Duty Report", d.duty.report || "new"]))}'>${d.duty.report ? __("Finish duty report") : __("Write duty report")}</span></div>` : ""}`;
			right.push(S.card(__("Duty"), body));
		}
		if (d.relieving && d.relieving.length) {
			right.push(S.card(__("You are relieving"), `<div class="sd-list">${d.relieving.map((r) => `<div class="sd-row clickable" data-route='${S.esc(JSON.stringify(["Form", "Leave Application", r.name]))}'>
				<div class="sd-row-main">${S.esc(r.staff_name)}<small>${S.esc(r.leave_type)}</small></div><span class="sd-num">${S.esc(r.period)}</span></div>`).join("")}</div>`));
		}
		if (d.leave) {
			const bal = d.leave.map((b) => {
				const used = b.taken + b.pending, pct = b.entitled ? (used / b.entitled) * 100 : 0;
				return `<div class="sd-leave-row"><div class="sd-leave-head"><span>${S.esc(b.leave_type)}</span><span class="sd-num">${b.balance} ${__("left")} <span style="color:var(--text-muted);font-weight:400">/ ${b.entitled}</span></span></div>
					<div class="sd-bar"><span style="width:${Math.min(100, pct)}%"></span></div></div>`;
			}).join("");
			const mine = (d.my_leave || []).map((l) => `<div class="sd-row clickable" data-route='${S.esc(JSON.stringify(["Form", "Leave Application", l.name]))}'>
				<div class="sd-row-main">${S.esc(l.leave_type)}<small>${S.esc(l.period)}</small></div>${S.pill(l.status === "Approved" ? "good" : "warning", __(l.status))}</div>`).join("");
			right.push(S.card(__("Your leave"), (mine ? `<div class="sd-list" style="margin-bottom:10px">${mine}</div>` : "") + (bal || `<div class="sd-empty">${__("No leave types set up")}</div>`),
				{ sub: __("This year"), link: { label: __("Apply"), route: ["Form", "Leave Application", "new"] } }));
		}
		if (d.away_today) {
			right.push(S.card(__("Colleagues away today"), d.away_today.length
				? `<div class="sd-list">${d.away_today.map((a) => `<div class="sd-row"><div class="sd-row-main">${S.esc(a.staff_name)}</div><small style="color:var(--text-muted)">${a.reliever_name ? __("Reliever: {0}", [S.esc(a.reliever_name)]) : ""}</small></div>`).join("")}</div>`
				: `<div class="sd-empty">${__("Everyone is in today")}</div>`));
		}

		html.push(`<div class="sd-grid sd-room"><div class="sd-grid" style="align-content:start">${left.join("")}</div><div class="sd-grid" style="align-content:start">${right.join("")}</div></div>`);
		this.$root.html(html.join(""));
	}
}
