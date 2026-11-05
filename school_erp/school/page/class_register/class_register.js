// Class Register: take the day's attendance for a stream from a phone in under a minute.
// Everyone starts Present; tap Absent / Late / Excused for the few who aren't, then Save.

frappe.pages["class-register"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Class Register"), single_column: true });
	wrapper.register = new ClassRegister(page, wrapper);
};

frappe.pages["class-register"].on_page_show = function (wrapper) {
	const opts = frappe.route_options || {};
	frappe.route_options = null;
	wrapper.register && wrapper.register.show(opts);
};

const CR_STATUS = [
	{ key: "Present", short: __("P"), label: __("Present") },
	{ key: "Absent", short: __("A"), label: __("Absent") },
	{ key: "Late", short: __("L"), label: __("Late") },
	{ key: "Excused", short: __("E"), label: __("Excused") },
];

class ClassRegister {
	constructor(page, wrapper) {
		this.page = page;
		this.$body = $(`<div class="cr-wrap"></div>`).appendTo(page.main);
		this.inject_css();
		this.stream = this.page.add_field({
			fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream",
			get_query: () => ({ filters: { is_active: 1 } }), change: () => this.load(),
		});
		this.date = this.page.add_field({
			fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today(), change: () => this.load(),
		});
		this.page.set_primary_action(__("Save"), () => this.save(), "check");
		this.page.add_inner_button(__("All present"), () => this.set_all("Present"));
		this.page.add_menu_item(__("Today's registers (all classes)"), () => frappe.set_route("query-report", "Daily Attendance"));
		this.page.add_menu_item(__("Attendance Register report"), () => frappe.set_route("query-report", "Attendance Register"));
		this.$body.on("click", "[data-set]", (e) => {
			const $b = $(e.currentTarget);
			this.set_status(cint($b.attr("data-i")), $b.attr("data-set"));
		});
		this.$body.on("click", "[data-note]", (e) => this.edit_note(cint($(e.currentTarget).attr("data-note"))));
		$(wrapper).on("keydown", (e) => {
			if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); this.save(); }
		});
	}

	show(opts) {
		if (opts.date) this.date.set_value(opts.date);
		if (opts.stream) return this.stream.set_value(opts.stream);
		if (this.stream.get_value()) return this.load();
		frappe.call("school_erp.api.attendance.my_streams").then(({ message: m }) => {
			const first = (m.mine || [])[0];
			if (first) this.stream.set_value(first);
			else this.render_empty(__("Choose a stream above to take its register."));
		});
	}

	load() {
		const stream = this.stream.get_value(), date = this.date.get_value();
		if (!stream || !date) return;
		if (this.dirty && !confirm(__("Discard the changes you have not saved?"))) return;
		this.dirty = false;
		frappe.call({ method: "school_erp.api.attendance.register", args: { stream, date } }).then(({ message: d }) => {
			this.data = d;
			this.render();
		});
	}

	render_empty(text) {
		this.$body.html(`<div class="cr-empty">${frappe.utils.escape_html(text)}</div>`);
	}

	counts() {
		const c = { Present: 0, Absent: 0, Late: 0, Excused: 0 };
		(this.data.students || []).forEach((s) => (c[s.status] = (c[s.status] || 0) + 1));
		return c;
	}

	render() {
		const d = this.data, esc = frappe.utils.escape_html;
		if (!d.students.length) return this.render_empty(__("No active students in {0}.", [d.stream]));
		const saved = d.saved.name
			? `<span class="cr-saved">${frappe.utils.icon("check", "xs")} ${__("Taken by {0}, {1}", [esc(d.saved.taken_by), esc(d.saved.taken_at)])}</span>`
			: `<span class="cr-saved todo">${__("Not taken yet")}</span>`;
		const locked = !d.can_edit ? `<div class="cr-locked">${esc(d.saved.locked || __("You can view this register but not change it."))}</div>` : "";
		this.$body.html(`
			<div class="cr-head">
				<div><div class="cr-title">${esc(d.stream)}</div><div class="cr-sub">${esc(d.date_label)} · ${saved}</div></div>
				<div class="cr-counts"></div>
			</div>
			${locked}
			<div class="cr-list ${d.can_edit ? "" : "ro"}">${d.students.map((s, i) => this.row(s, i)).join("")}</div>
			${d.can_edit ? `<button class="btn btn-primary cr-save">${__("Save register")}</button>` : ""}`);
		this.$body.find(".cr-save").on("click", () => this.save());
		this.page.btn_primary.toggle(!!d.can_edit);
		this.update_counts();
	}

	row(s, i) {
		const esc = frappe.utils.escape_html;
		const av = s.photo ? `<img src="${esc(s.photo)}" alt="">` : esc((s.first_name || s.name || "?").charAt(0));
		return `<div class="cr-row st-${s.status.toLowerCase()}" data-row="${i}">
			<div class="cr-av">${av}</div>
			<div class="cr-name" data-note="${i}" title="${__("Add a note")}">${esc(s.name)}
				<small>${esc(s.student)}${s.note ? " · " + esc(s.note) : ""}${s.moved ? " · " + __("moved out") : ""}</small></div>
			<div class="cr-seg" role="radiogroup" aria-label="${esc(s.name)}">${CR_STATUS.map((o) =>
				`<button type="button" class="cr-b b-${o.key.toLowerCase()} ${s.status === o.key ? "on" : ""}" data-i="${i}" data-set="${o.key}"
					role="radio" aria-checked="${s.status === o.key}" title="${o.label}">${o.short}</button>`).join("")}</div>
		</div>`;
	}

	set_status(i, status) {
		if (!this.data.can_edit) return;
		const s = this.data.students[i];
		s.status = status;
		this.dirty = true;
		this.$body.find(`[data-row="${i}"]`).replaceWith(this.row(s, i));
		this.update_counts();
	}

	set_all(status) {
		if (!this.data || !this.data.can_edit) return;
		this.data.students.forEach((s) => (s.status = status));
		this.dirty = true;
		this.render();
	}

	edit_note(i) {
		if (!this.data.can_edit) return;
		const s = this.data.students[i];
		frappe.prompt({ fieldname: "note", fieldtype: "Data", label: __("Note for {0}", [s.name]), default: s.note,
			description: __("e.g. sick, came at 9:10, school trip") }, (v) => {
			s.note = v.note || "";
			this.dirty = true;
			this.$body.find(`[data-row="${i}"]`).replaceWith(this.row(s, i));
		}, __("Note"), __("Done"));
	}

	update_counts() {
		const c = this.counts(), total = this.data.students.length;
		const pct = total ? Math.round(((c.Present + c.Late) / total) * 1000) / 10 : 0;
		this.$body.find(".cr-counts").html(`
			<span class="cr-pct">${pct}%</span>
			<span class="cr-c present">${__("P")} ${c.Present}</span><span class="cr-c absent">${__("A")} ${c.Absent}</span>
			<span class="cr-c late">${__("L")} ${c.Late}</span><span class="cr-c excused">${__("E")} ${c.Excused}</span>`);
	}

	save() {
		const d = this.data;
		if (!d || !d.can_edit) return;
		frappe.call({
			method: "school_erp.api.attendance.save_register", freeze: true, freeze_message: __("Saving register..."),
			args: { stream: d.stream, date: d.date, rows: d.students.map((s) => ({ student: s.student, status: s.status, note: s.note })) },
		}).then(({ message: r }) => {
			this.dirty = false;
			frappe.show_alert({
				message: __("Register saved: {0} present, {1} absent", [r.present + r.late, r.absent]) +
					(r.notified ? "<br>" + __("{0} parent(s) are being told by SMS", [r.notified]) : ""),
				indicator: "green",
			}, 6);
			this.load();
		});
	}

	inject_css() {
		if (document.getElementById("cr-css")) return;
		$(`<style id="cr-css">
			.cr-wrap { max-width: 760px; margin: 0 auto; padding-bottom: 80px; }
			.cr-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap; margin: 4px 0 12px; }
			.cr-title { font-size: 20px; font-weight: 700; color: var(--text-color); }
			.cr-sub { color: var(--text-muted); font-size: 13px; margin-top: 2px; }
			.cr-saved { color: var(--green-600); } .cr-saved.todo { color: var(--orange-600); }
			.cr-counts { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
			.cr-pct { font-weight: 700; font-size: 18px; margin-right: 4px; color: var(--text-color); }
			.cr-c { font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 999px; background: var(--control-bg); color: var(--text-color); }
			.cr-c.absent { background: var(--red-100); color: var(--red-700); } .cr-c.late { background: var(--orange-100); color: var(--orange-700); }
			.cr-c.excused { background: var(--blue-100); color: var(--blue-700); }
			.cr-locked { background: var(--orange-50, var(--control-bg)); color: var(--orange-700); padding: 8px 12px; border-radius: 8px; margin-bottom: 10px; font-size: 13px; }
			.cr-list { border: 1px solid var(--border-color); border-radius: 12px; overflow: hidden; background: var(--card-bg); }
			.cr-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-bottom: 1px solid var(--border-color); }
			.cr-row:last-child { border-bottom: 0; }
			.cr-row.st-absent { background: color-mix(in srgb, var(--red-500) 8%, transparent); }
			.cr-row.st-late { background: color-mix(in srgb, var(--orange-500) 8%, transparent); }
			.cr-row.st-excused { background: color-mix(in srgb, var(--blue-500) 7%, transparent); }
			.cr-av { flex: 0 0 34px; height: 34px; border-radius: 50%; background: var(--control-bg); display: flex; align-items: center; justify-content: center;
				font-weight: 700; color: var(--text-muted); overflow: hidden; }
			.cr-av img { width: 100%; height: 100%; object-fit: cover; }
			.cr-name { flex: 1; min-width: 0; font-weight: 600; color: var(--text-color); cursor: pointer; overflow: hidden; text-overflow: ellipsis; }
			.cr-name small { display: block; font-weight: 400; color: var(--text-muted); font-size: 11.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.cr-seg { display: flex; gap: 4px; flex: 0 0 auto; }
			.cr-b { width: 38px; height: 38px; border-radius: 9px; border: 1px solid var(--border-color); background: var(--card-bg);
				font-weight: 700; color: var(--text-muted); font-size: 14px; }
			.cr-b.on.b-present { background: var(--green-600); border-color: var(--green-600); color: #fff; }
			.cr-b.on.b-absent { background: var(--red-600); border-color: var(--red-600); color: #fff; }
			.cr-b.on.b-late { background: var(--orange-500); border-color: var(--orange-500); color: #fff; }
			.cr-b.on.b-excused { background: var(--blue-600); border-color: var(--blue-600); color: #fff; }
			.cr-list.ro .cr-b { pointer-events: none; } .cr-list.ro .cr-b:not(.on) { opacity: .35; }
			.cr-save { position: sticky; bottom: 12px; width: 100%; margin-top: 14px; height: 46px; font-size: 15px; border-radius: 12px; }
			.cr-empty { padding: 48px 16px; text-align: center; color: var(--text-muted); }
			@media (max-width: 480px) { .cr-b { width: 34px; height: 36px; } .cr-seg { gap: 3px; } .cr-row { padding: 8px; gap: 8px; } .cr-av { display: none; } }
		</style>`).appendTo("head");
	}
}
