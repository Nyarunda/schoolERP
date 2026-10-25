// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Timetable", {
	setup(frm) {
		frm.set_query("teacher", "slots", () => ({ filters: { is_active: 1 } }));
		frm.set_query("period", "slots", () => ({ filters: { is_break: 0 } }));
	},
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Print Timetable"), () => frm.print_doc());
		}
		load_lookups().then(() => {
			set_session_times(frm);
			render_week_chart(frm);
		});
	},
	slots_remove(frm) {
		refresh_sessions(frm);
	},
});

frappe.ui.form.on("Timetable Slot", {
	day: refresh_sessions,
	period: refresh_sessions,
	subject: refresh_sessions,
	teacher: refresh_sessions,
	room: (frm) => render_week_chart(frm),
});

function refresh_sessions(frm) {
	load_lookups().then(() => {
		set_session_times(frm);
		frm.refresh_field("slots");
		render_week_chart(frm);
	});
}

// Bell schedule, subject colours and teacher names, fetched once per page load
let lookups = null;
function load_lookups() {
	if (!lookups) {
		lookups = Promise.all([
			frappe.db.get_list("Period", { fields: ["name", "period_name", "sequence", "start_time", "end_time", "is_break"], order_by: "sequence asc", limit: 100 }),
			frappe.db.get_list("Subject", { fields: ["name", "short_name", "color"], limit: 500 }),
			frappe.db.get_list("Teacher", { fields: ["name", "teacher_name"], limit: 1000 }),
		]).then(([periods, subjects, teachers]) => ({
			periods,
			subjects: Object.fromEntries(subjects.map((s) => [s.name, s])),
			teachers: Object.fromEntries(teachers.map((t) => [t.name, t.teacher_name])),
		}));
	}
	return lookups;
}

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const SESSION_NAMES = { 2: __("Double"), 3: __("Triple") };
const hm = (t) => { const [h, m] = String(t || "0:00").split(":"); return `${String(parseInt(h, 10)).padStart(2, "0")}:${m.slice(0, 2)}`; };
const minutes = (t) => { const [h, m] = hm(t).split(":"); return +h * 60 + +m; };

// Mirrors school_erp.logic.timetable.session_blocks so the grid updates while editing; the server sets the same values on save
function session_blocks(slots, periods) {
	const order = Object.fromEntries(periods.map((p, i) => [p.name, i]));
	const lessons = slots.filter((s) => s.subject && s.period in order)
		.sort((a, b) => DAYS.indexOf(a.day) - DAYS.indexOf(b.day) || order[a.period] - order[b.period]);
	const blocks = [];
	for (const s of lessons) {
		const last = blocks[blocks.length - 1];
		if (last && last.day === s.day && last.subject === s.subject && (last.teacher || "") === (s.teacher || "")
			&& order[s.period] === order[last.slots[last.slots.length - 1].period] + 1) {
			last.slots.push(s);
		} else {
			blocks.push({ day: s.day, subject: s.subject, teacher: s.teacher || "", slots: [s] });
		}
	}
	const by_name = Object.fromEntries(periods.map((p) => [p.name, p]));
	for (const b of blocks) {
		b.size = b.slots.length;
		b.start = hm(by_name[b.slots[0].period].start_time);
		b.end = hm(by_name[b.slots[b.size - 1].period].end_time);
	}
	return blocks;
}

function set_session_times(frm) {
	if (!lookups) return;
	lookups.then(({ periods }) => {
		const by_name = Object.fromEntries(periods.map((p) => [p.name, p]));
		for (const s of frm.doc.slots || []) {
			const p = by_name[s.period];
			s.time = p ? `${hm(p.start_time)}-${hm(p.end_time)}` : "";
			s.session = "";
		}
		for (const b of session_blocks(frm.doc.slots || [], periods)) {
			if (b.size < 2) continue;
			b.slots.forEach((s, i) => {
				s.time = `${b.start}-${b.end}`;
				s.session = `${SESSION_NAMES[b.size] || __("{0} periods", [b.size])} ${i + 1}/${b.size}`;
			});
		}
		frm.refresh_field("slots");
	});
}

// Fallback colours for subjects without one (categorical, readable on white and dark)
const PALETTE = ["#2a78d6", "#eb6834", "#1f9d6b", "#8b5cf6", "#d4a106", "#d6336c", "#0e98b4", "#6b7d2a", "#b85c38", "#5c6ac4"];
const color_for = (name, subjects) => {
	const c = subjects[name] && subjects[name].color;
	if (c) return c;
	let h = 0;
	for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
	return PALETTE[h % PALETTE.length];
};

const WEEK_CHART_CSS = `
	.tt-chart { --tt-row: 76px; font-size: 12px; }
	.tt-legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-bottom: 12px; color: var(--text-muted); }
	.tt-legend span { display: inline-flex; align-items: center; gap: 6px; }
	.tt-legend i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
	.tt-legend .dbl { width: 22px; height: 10px; border-radius: 3px; border: 2px solid var(--text-muted); }
	.tt-scroll { overflow-x: auto; padding-bottom: 4px; }
	.tt-grid { display: grid; grid-template-columns: 92px minmax(980px, 1fr); }
	.tt-axis { position: relative; height: 26px; border-bottom: 1px solid var(--border-color); }
	.tt-axis span { position: absolute; top: 4px; transform: translateX(-50%); color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
	.tt-day { display: flex; flex-direction: column; justify-content: center; padding-right: 10px; height: var(--tt-row); border-bottom: 1px solid var(--border-color); font-weight: 600; color: var(--heading-color, var(--text-color)); }
	.tt-day small { font-weight: 400; color: var(--text-muted); }
	.tt-track { position: relative; height: var(--tt-row); border-bottom: 1px solid var(--border-color); }
	.tt-tick { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--border-color); opacity: .6; }
	.tt-break { position: absolute; top: 0; bottom: 0; background: repeating-linear-gradient(135deg, var(--subtle-fg, #f3f4f6) 0 6px, transparent 6px 12px); }
	.tt-break span { position: absolute; bottom: 3px; left: 50%; transform: translateX(-50%); font-size: 10px; color: var(--text-muted); white-space: nowrap; }
	.tt-block { position: absolute; top: 6px; bottom: 6px; border-radius: 8px; padding: 5px 7px; line-height: 1.3; overflow: hidden; cursor: pointer; color: var(--text-color);
		background: color-mix(in srgb, var(--c) 14%, var(--card-bg, #fff)); border: 1px solid color-mix(in srgb, var(--c) 45%, transparent); border-left: 4px solid var(--c);
		transition: transform .12s, box-shadow .12s; }
	.tt-block:hover { transform: translateY(-1px); box-shadow: 0 6px 16px -8px var(--c); z-index: 2; }
	.tt-block.multi { border-width: 2px; border-left-width: 5px; }
	.tt-block b { display: block; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tt-block small { display: block; font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tt-badge { float: right; margin-left: 4px; font-size: 9.5px; font-weight: 800; letter-spacing: .4px; padding: 1px 5px; border-radius: 4px; background: var(--c); color: #fff; }
	.tt-free { position: absolute; top: 6px; bottom: 6px; border-radius: 8px; border: 1px dashed var(--border-color); }
	.tt-empty { color: var(--text-muted); padding: 16px 0; }
`;

function render_week_chart(frm) {
	const field = frm.get_field("week_chart");
	if (!field || !lookups) return;
	if (!document.getElementById("tt-chart-css")) $(`<style id="tt-chart-css">${WEEK_CHART_CSS}</style>`).appendTo("head");
	lookups.then(({ periods, subjects, teachers }) => {
		const $w = $(field.wrapper);
		const slots = frm.doc.slots || [];
		if (!slots.length || !periods.length) { $w.empty(); return; }
		const esc = frappe.utils.escape_html;
		const t0 = Math.min(...periods.map((p) => minutes(p.start_time)));
		const t1 = Math.max(...periods.map((p) => minutes(p.end_time)));
		const x = (t) => ((minutes(t) - t0) / (t1 - t0)) * 100;
		const days = DAYS.filter((d) => d !== "Saturday" || slots.some((s) => s.day === "Saturday"));
		const blocks = session_blocks(slots, periods);
		const teaching = periods.filter((p) => !p.is_break);

		// hour ticks
		const ticks = [];
		for (let m = Math.ceil(t0 / 60) * 60; m <= t1; m += 60) ticks.push(m);
		const tick_x = (m) => ((m - t0) / (t1 - t0)) * 100;
		const axis = ticks.map((m) => `<span style="left:${tick_x(m)}%">${String(m / 60).padStart(2, "0")}:00</span>`).join("");
		const tick_lines = ticks.map((m) => `<div class="tt-tick" style="left:${tick_x(m)}%"></div>`).join("");
		const breaks = periods.filter((p) => p.is_break).map((p) => `<div class="tt-break" style="left:${x(p.start_time)}%;width:${x(p.end_time) - x(p.start_time)}%"
			title="${esc(p.period_name || p.name)} ${hm(p.start_time)}-${hm(p.end_time)}">${x(p.end_time) - x(p.start_time) > 4 ? `<span>${esc(p.period_name || p.name)}</span>` : ""}</div>`).join("");

		const rows = days.map((day) => {
			const mine = blocks.filter((b) => b.day === day);
			const used = new Set(slots.filter((s) => s.day === day && s.subject).map((s) => s.period));
			const free = teaching.filter((p) => !used.has(p.name)).map((p) => `<div class="tt-free" style="left:calc(${x(p.start_time)}% + 2px);width:calc(${x(p.end_time) - x(p.start_time)}% - 4px)" title="${__("Free")} ${hm(p.start_time)}-${hm(p.end_time)}"></div>`).join("");
			const cells = mine.map((b) => {
				const sub = subjects[b.subject] || {};
				const label = sub.short_name || b.subject;
				const teacher = teachers[b.teacher] || "";
				const room = b.slots[0].room || "";
				const badge = b.size > 1 ? `<span class="tt-badge">${b.size === 2 ? "×2" : "×" + b.size}</span>` : "";
				const tip = [b.subject, `${b.start}-${b.end}`, b.size > 1 ? SESSION_NAMES[b.size] || "" : "", teacher, room].filter(Boolean).join(" · ");
				return `<div class="tt-block ${b.size > 1 ? "multi" : ""}" data-row="${esc(b.slots[0].name)}" title="${esc(tip)}"
					style="--c:${esc(color_for(b.subject, subjects))};left:calc(${x(b.start)}% + 2px);width:calc(${x(b.end) - x(b.start)}% - 4px)">
					${badge}<b>${esc(label)}</b><small>${b.size > 1 ? `${b.start}-${b.end}` : b.start}</small><small>${esc(teacher)}${room ? " · " + esc(room) : ""}</small></div>`;
			}).join("");
			const count = mine.reduce((n, b) => n + b.size, 0);
			return `<div class="tt-day">${__(day)}<small>${__("{0} lessons", [count])}</small></div>
				<div class="tt-track">${tick_lines}${breaks}${free}${cells}</div>`;
		}).join("");

		const doubles = blocks.filter((b) => b.size > 1).length;
		const used_subjects = [...new Set(blocks.map((b) => b.subject))];
		const legend = used_subjects.map((s) => `<span><i style="background:${esc(color_for(s, subjects))}"></i>${esc((subjects[s] || {}).short_name || s)}</span>`).join("")
			+ (doubles ? `<span><i class="dbl"></i>${__("{0} double sessions", [doubles])}</span>` : "");

		$w.html(`<div class="tt-chart">
			<div class="tt-legend">${legend}</div>
			<div class="tt-scroll"><div class="tt-grid">
				<div></div><div class="tt-axis">${axis}</div>
				${rows}
			</div></div>
		</div>`);
		$w.find(".tt-block").on("click", function () {
			const row = frm.fields_dict.slots.grid.grid_rows_by_docname[this.dataset.row];
			if (row) row.toggle_view(true);
		});
	});
}
