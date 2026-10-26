// Staff Room: every teacher's (and staff member's) home screen.
frappe.pages["staff-room"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Staff Room"), single_column: true });
	wrapper.room = new StaffRoom(page, $(wrapper).find(".layout-main-section"));
	page.set_secondary_action(__("Refresh"), () => wrapper.room.load(), "refresh");
};

frappe.pages["staff-room"].on_page_show = function (wrapper) {
	if (wrapper.room && wrapper.room.loaded_at && Date.now() - wrapper.room.loaded_at > 60000) wrapper.room.load();
};

// Stroke icons for the cards and quick actions (names match the `icon` keys the API sends)
const SR_ICONS = {
	calendar: '<rect x="3" y="4.5" width="18" height="16.5" rx="2.5"/><path d="M8 2.5v4M16 2.5v4M3 10h18"/>',
	clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 11h6M9 15h4"/>',
	alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17.5h.01"/>',
	bus: '<rect x="4" y="3" width="16" height="14" rx="3"/><path d="M4 10h16M7 21v-4M17 21v-4M8 13.5h.01M16 13.5h.01"/>',
	receipt: '<path d="M5 3v18l2.5-1.5L10 21l2-1.5 2 1.5 2.5-1.5L19 21V3l-2.5 1.5L14 3l-2 1.5L10 3 7.5 4.5z"/><path d="M9 9h6M9 13h6"/>',
	grid: '<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>',
	book: '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M4 21.5A2.5 2.5 0 0 1 6.5 19H20v3H6.5"/>',
	users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 20a6.5 6.5 0 0 0-3-5.5"/>',
	bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
	shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
	plane: '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>',
	sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
	check: '<path d="M20 6 9 17l-5-5"/>',
	arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
	user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
};
const sr_icon = (name, cls = "") => `<svg class="sr-ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SR_ICONS[name] || SR_ICONS.grid}</svg>`;

class StaffRoom {
	constructor(page, $parent) {
		this.page = page;
		this.$root = $(`<div class="sd sr"><div class="sd-skeleton" style="height:180px;margin-bottom:16px"></div></div>`).appendTo($parent);
		school_dash.bind_routes(this.$root);
		this.$root.on("click", "[data-ack]", (e) => this.acknowledge(e.currentTarget));
		this.loading = false;
		this.load();
	}

	load() {
		// One request at a time; a refresh asked for meanwhile runs when the current one finishes
		if (this.loading) {
			this.queued = true;
			return;
		}
		this.loading = true;
		// xcall returns a real Promise (frappe.call's jQuery promise has no .finally)
		frappe.xcall("school_erp.api.dashboard.staff_room").then((message) => {
			this.data = message;
			this.loaded_at = Date.now();
			this.render();
		}).catch(() => frappe.show_alert({ message: __("Unable to refresh staff room"), indicator: "red" }))
			.finally(() => {
				this.loading = false;
				if (this.queued) {
					this.queued = false;
					this.load();
				}
			});
	}

	acknowledge(btn) {
		const name = btn.getAttribute("data-ack");
		btn.disabled = true;
		frappe.call("school_erp.school.doctype.school_notice.school_notice.acknowledge", { name }).then(() => {
			$(btn).replaceWith(school_dash.pill("good", __("Acknowledged")));
			const n = (this.data.notices || []).find((x) => x.name === name);
			if (n) n.acknowledged = 1;
			this.$root.find("[data-stat=unread] b").text((this.data.notices || []).filter((x) => !x.acknowledged).length);
		});
	}

	card(icon, title, body, opts = {}) {
		const S = school_dash;
		return `<section class="sr-card ${opts.cls || ""}">
			<header class="sr-card-head">
				<span class="sr-card-ic ${opts.tone || ""}">${sr_icon(icon)}</span>
				<div class="sr-card-t"><h3>${S.esc(title)}</h3>${opts.sub ? `<small>${S.esc(opts.sub)}</small>` : ""}</div>
				${opts.link ? `<span class="sr-link" data-route='${S.esc(JSON.stringify(opts.link.route))}'>${S.esc(opts.link.label)} ${sr_icon("arrow")}</span>` : ""}
			</header>
			${body}
		</section>`;
	}

	empty(icon, text, sub) {
		return `<div class="sr-empty">${sr_icon(icon)}<div>${school_dash.esc(text)}</div>${sub ? `<small>${school_dash.esc(sub)}</small>` : ""}</div>`;
	}

	render() {
		const d = this.data, S = school_dash;
		if (d.is_management) {
			this.page.clear_primary_action();
			this.page.set_primary_action(__("Management Dashboard"), () => frappe.set_route("management-dashboard"));
		}
		const html = [this.hero(d), this.alerts(d), this.quick_actions(d)];

		const left = [];
		if (d.lessons) left.push(this.lessons(d));
		if (d.my_classes && d.my_classes.length) left.push(this.classes(d));
		left.push(this.card("bell", __("Notice board"), `<div class="sr-notices">${S.notices(d.notices)}</div>`,
			{ link: { label: __("All notices"), route: ["List", "School Notice"] } }));

		const right = [];
		if (d.duty) right.push(this.duty(d));
		if (d.relieving && d.relieving.length) {
			right.push(this.card("users", __("You are relieving"), `<div class="sr-list">${d.relieving.map((r) => `
				<div class="sr-row clickable" data-route='${S.esc(JSON.stringify(["Form", "Leave Application", r.name]))}'>
					${this.avatar(r.staff_name)}<div class="sr-row-main">${S.esc(r.staff_name)}<small>${S.esc(r.leave_type)}</small></div>
					${r.now ? S.pill("warning", __("Today")) : `<span class="sr-muted">${S.esc(r.period)}</span>`}
				</div>`).join("")}</div>`, { tone: "warning" }));
		}
		if (d.leave) right.push(this.leave(d));
		if (d.away_today) {
			right.push(this.card("plane", __("Colleagues away today"), d.away_today.length
				? `<div class="sr-list">${d.away_today.map((a) => `<div class="sr-row">${this.avatar(a.staff_name)}
					<div class="sr-row-main">${S.esc(a.staff_name)}${a.reliever_name ? `<small>${__("Reliever: {0}", [S.esc(a.reliever_name)])}</small>` : ""}</div></div>`).join("")}</div>`
				: this.empty("sun", __("Everyone is in today"))));
		}

		html.push(`<div class="sr-cols"><div class="sr-col">${left.join("")}</div><div class="sr-col">${right.join("")}</div></div>`);
		this.$root.html(html.join(""));
	}

	avatar(name) {
		const initials = String(name || "?").split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
		return `<span class="sr-av">${school_dash.esc(initials)}</span>`;
	}

	hero(d) {
		const S = school_dash;
		const first = (d.greeting || "").split(", ").pop();
		const chips = [d.designation, d.staff_type && d.staff_type !== d.designation ? d.staff_type : null, d.term].filter(Boolean)
			.map((c) => `<span class="sr-chip">${S.esc(c)}</span>`).join("");
		const stats = [];
		if (d.lessons) {
			const left = d.lessons.filter((l) => l.state !== "done").length;
			stats.push([__("Lessons today"), d.lessons.length, d.lessons.length ? __("{0} still to go", [left]) : __("Free day")]);
			stats.push([__("This week"), d.week_lessons || 0, __("lessons")]);
		}
		if (d.leave && d.leave.length) {
			const annual = d.leave.find((l) => /annual/i.test(l.leave_type)) || d.leave[0];
			stats.push([__(annual.leave_type), annual.balance, __("of {0} days left", [annual.entitled])]);
		}
		const unread = (d.notices || []).filter((n) => !n.acknowledged).length;
		stats.push([__("Notices to read"), unread, __("{0} on the board", [(d.notices || []).length]), "unread"]);

		return `<div class="sr-hero">
			<div class="sr-hero-main">
				<div class="sr-hero-av">${S.esc((first || "?")[0])}</div>
				<div>
					<div class="sr-eyebrow">${S.esc(d.today || "")}</div>
					<h2>${S.esc(d.greeting)}</h2>
					<div class="sr-chips">${chips}</div>
				</div>
			</div>
			<div class="sr-stats">${stats.map(([l, v, f, key]) => `<div class="sr-stat" ${key ? `data-stat="${key}"` : ""}>
				<span>${S.esc(l)}</span><b>${S.esc(v)}</b><small>${S.esc(f)}</small></div>`).join("")}</div>
		</div>`;
	}

	alerts(d) {
		const S = school_dash, out = [];
		const alert = (tone, icon, title, text, action) => out.push(`<div class="sr-alert ${tone}">
			<span class="sr-alert-ic">${sr_icon(icon)}</span>
			<div class="sr-alert-body"><b>${S.esc(title)}</b>${text ? `<span>${S.esc(text)}</span>` : ""}</div>
			${action ? `<button class="btn btn-sm sr-alert-btn" data-route='${S.esc(JSON.stringify(action.route))}'>${S.esc(action.label)}</button>` : ""}
		</div>`);

		const now = (d.relieving || []).find((r) => r.now);
		if (now) alert("warning", "users", __("You are relieving {0} today", [now.staff_name]), now.period,
			{ label: __("View"), route: ["Form", "Leave Application", now.name] });
		if (d.duty && d.duty.on_duty_now && !d.duty.submitted) {
			alert("warning", "shield", __("You are {0} this week", [d.duty.role]), __("Today's duty report has not been sent yet."),
				{ label: d.duty.report ? __("Finish report") : __("Write report"), route: ["Form", "Duty Report", d.duty.report || "new"] });
		}
		if (d.staff_type === "Driver" && "checkin" in d) {
			if (!d.checkin || d.checkin.docstatus !== 1) {
				alert("critical", "bus", __("Morning check-in not done"), __("Check in before your first trip."),
					{ label: __("Check in"), route: ["Form", "Driver Daily Log", (d.checkin || {}).name || "new"] });
			} else if (d.checkin.has_issues) {
				alert("serious", "bus", __("Checked in, issues reported"), __("The transport office has been told."));
			}
		}
		if (!d.staff) alert("muted", "user", __("Your login is not linked to a Staff Member yet"), __("Ask the school office to link it so your lessons, duty and leave show here."));
		return out.length ? `<div class="sr-alerts">${out.join("")}</div>` : "";
	}

	quick_actions(d) {
		const S = school_dash;
		if (!(d.actions || []).length) return "";
		return `<div class="sr-actions">${d.actions.map((a, i) => `<button class="sr-action ${i === 0 ? "primary" : ""}" data-route='${S.esc(JSON.stringify(a.route))}'>
			<span class="sr-action-ic">${sr_icon(a.icon)}</span><span>${S.esc(a.label)}</span></button>`).join("")}</div>`;
	}

	lessons(d) {
		const S = school_dash;
		const weekend = [0, 6].includes(new Date().getDay());
		const body = d.lessons.length
			? `<div class="sr-timeline">${d.lessons.map((l) => `<div class="sr-lesson ${l.state}">
				<div class="sr-time">${S.esc(l.time)}<small>${S.esc(l.period_name)}</small></div>
				<div class="sr-dot"></div>
				<div class="sr-lesson-body">
					<div class="sr-subj">${S.esc(l.subject || __("Lesson"))}</div>
					<small>${S.esc(l.stream)}${l.room ? " · " + S.esc(l.room) : ""}</small>
				</div>
				${l.state === "now" ? `<span class="sr-tag now">${__("Now")}</span>` : l.state === "next" ? `<span class="sr-tag">${__("Next")}</span>` : l.state === "done" ? `<span class="sr-tag done">${sr_icon("check")}</span>` : ""}
			</div>`).join("")}</div>`
			: this.empty(weekend ? "sun" : "book", weekend ? __("No lessons today, enjoy the weekend") : __("No lessons on your timetable today"),
				__("{0} lessons this week", [d.week_lessons || 0]));
		return this.card("book", __("Your lessons today"), body,
			{ sub: d.lessons.length ? __("{0} lessons this week", [d.week_lessons || 0]) : null, link: { label: __("Timetables"), route: ["List", "Timetable"] } });
	}

	classes(d) {
		const S = school_dash;
		const cards = d.my_classes.map((c) => {
			const total = c.students || 0, g = total ? (c.girls / total) * 100 : 0;
			return `<div class="sr-class" data-route='${S.esc(JSON.stringify(["List", "Student", { stream: c.stream, status: "Active" }]))}'>
				<div class="sr-class-top"><b>${S.esc(c.stream)}</b>${"incidents" in c && c.incidents
					? `<span class="sr-tag warn" title="${__("Discipline incidents this term")}">${sr_icon("alert")}${c.incidents}</span>` : ""}</div>
				<div class="sr-class-num">${total}<small>${__("students")}</small></div>
				<div class="sr-split" role="img" aria-label="${__("{0} girls, {1} boys", [c.girls, c.boys])}"><span class="g" style="width:${g}%"></span><span class="b" style="width:${100 - g}%"></span></div>
				<div class="sr-legend"><span class="g">${__("Girls")} <b>${c.girls}</b></span><span class="b">${__("Boys")} <b>${c.boys}</b></span></div>
			</div>`;
		}).join("");
		return this.card("users", d.my_classes.length > 1 ? __("Your classes") : __("Your class"), `<div class="sr-classes">${cards}</div>`,
			{ sub: __("You are the class teacher") });
	}

	duty(d) {
		const S = school_dash, u = d.duty;
		const status = u.on_duty_now ? (u.submitted ? S.pill("good", __("Report sent")) : S.pill("warning", __("Report due"))) : S.pill("muted", __("Upcoming"));
		const body = `<div class="sr-duty">
				<div><div class="sr-duty-role">${S.esc(u.role)}</div><small>${S.esc(u.period)}</small></div>${status}
			</div>`;
		return this.card("shield", __("Duty"), body, { tone: u.on_duty_now && !u.submitted ? "warning" : "" });
	}

	leave(d) {
		const S = school_dash;
		const mine = (d.my_leave || []).map((l) => `<div class="sr-row clickable" data-route='${S.esc(JSON.stringify(["Form", "Leave Application", l.name]))}'>
			<div class="sr-row-main">${S.esc(l.leave_type)}<small>${S.esc(l.period)}</small></div>${S.pill(l.status === "Approved" ? "good" : "warning", __(l.status))}</div>`).join("");
		const bal = d.leave.map((b) => {
			const pct = b.entitled ? Math.max(0, Math.min(100, (b.balance / b.entitled) * 100)) : 0;
			return `<div class="sr-leave">
				<div class="sr-leave-head"><span>${S.esc(b.leave_type)}</span><span><b>${b.balance}</b> <span class="sr-muted">/ ${b.entitled} ${__("days")}</span></span></div>
				<div class="sr-meter ${pct <= 20 ? "low" : ""}"><span style="width:${pct}%"></span></div>
				${b.pending ? `<small class="sr-muted">${__("{0} days waiting for approval", [b.pending])}</small>` : ""}
			</div>`;
		}).join("");
		return this.card("calendar", __("Your leave"), (mine ? `<div class="sr-list sr-mine">${mine}</div>` : "") + (bal || this.empty("calendar", __("No leave types set up"))),
			{ sub: __("Days left this year"), link: { label: __("Apply"), route: ["Form", "Leave Application", "new"] } });
	}
}
