// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Exam", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.grading_scale) {
			frappe.db.get_single_value("School Settings", "default_grading_scale").then((v) => v && frm.set_value("grading_scale", v));
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const colors = { "Marks Entry": "orange", "Results Ready": "blue", Published: "green" };
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status]);
		frm.add_custom_button(__("Enter Marks"), () => frappe.new_doc("Exam Mark Sheet", { exam: frm.doc.name }));
		frm.add_custom_button(__("Generate Report Cards"), () =>
			frappe.call({ method: "school_erp.api.exams.generate_report_cards", args: { exam: frm.doc.name }, freeze: true, freeze_message: __("Calculating results and positions...") })
				.then(({ message }) => {
					frappe.show_alert({ message: __("{0} report cards ready", [message.report_cards]), indicator: "green" });
					if (message.not_included) {
						frappe.msgprint({ title: __("Some marks are not in yet"), indicator: "orange",
							message: __("{0} mark sheet(s) are not approved yet, so their marks are not on the report cards. Generate again once they are approved.", [message.not_included]) });
					}
					frm.reload_doc();
				}),
			__("Results"));
		frm.add_custom_button(__("Report Cards"), () => frappe.set_route("List", "Report Card", { exam: frm.doc.name }), __("Results"));
		frm.add_custom_button(__("Merit List"), () => frappe.set_route("query-report", "Exam Merit List", { exam: frm.doc.name }), __("Results"));
		frm.add_custom_button(__("Subject Analysis"), () => frappe.set_route("query-report", "Exam Subject Analysis", { exam: frm.doc.name }), __("Results"));
		if (frm.doc.status !== "Marks Entry") {
			frm.add_custom_button(frm.doc.status === "Published" ? __("Publish Again") : __("Publish to Parents"), () =>
				frappe.confirm(__("Show the report cards on the parent portal and send each parent an SMS (and the PDF by email)?"), () =>
					frappe.call({ method: "school_erp.api.exams.publish", args: { exam: frm.doc.name }, freeze: true })
						.then(({ message }) => { frappe.msgprint(__("{0} report cards published.", [message.published])); frm.reload_doc(); })),
				__("Results"));
		}
		frappe.call("school_erp.api.exams.exam_progress", { exam: frm.doc.name }).then(({ message: p }) => {
			render_progress(frm, p);
			if (p.to_approve) {
				frm.add_custom_button(__("Approve Marks ({0})", [p.to_approve]), () => approve_dialog(frm)).addClass("btn-primary");
			}
		});
	},
});

function render_progress(frm, p) {
	const esc = frappe.utils.escape_html;
	const icon = { done: "✓", pending: "⏳", returned: "↩", draft: "…", missing: "" };
	const color = { done: "var(--green-600)", pending: "var(--blue-600)", returned: "var(--red-600)", draft: "var(--orange-600)", missing: "var(--text-light)" };
	const say = { done: p.approval ? __("approved") : __("submitted"), pending: __("waiting for approval"), returned: __("returned for correction"),
		draft: __("in progress"), missing: __("not started") };
	const head = p.subjects.map((s) => `<th style="font-size:11px;padding:4px 6px;text-align:center">${esc(s)}</th>`).join("");
	const rows = p.rows.map((r) => `<tr><td style="padding:4px 6px;white-space:nowrap">${esc(r.stream)}</td>${r.cells.map((c) =>
		`<td style="text-align:center;padding:4px 6px;color:${color[c.state]};font-weight:600;cursor:pointer"
			data-sheet="${esc(c.sheet || "")}" data-stream="${esc(r.stream)}" data-subject="${esc(c.subject)}"
			title="${esc(r.stream)} · ${esc(c.subject)}: ${say[c.state]}">${icon[c.state] || "·"}</td>`).join("")}</tr>`).join("");
	const $w = frm.get_field("progress_html").$wrapper;
	const legend = p.approval
		? `✓ ${__("approved")} · ⏳ ${__("waiting for approval")} · ↩ ${__("returned")} · … ${__("in progress")}`
		: `✓ ${__("submitted")} · … ${__("in progress")}`;
	$w.html(`<div style="margin-bottom:8px"><b>${p.done}</b> ${__("of")} <b>${p.total}</b> ${p.approval ? __("mark sheets approved") : __("mark sheets submitted")}
		${p.pending ? `· <b>${p.pending}</b> ${__("waiting for approval")}` : ""}
		<span class="text-muted small">&nbsp; ${legend} · ${__("click a cell to open it")}</span></div>
		<div style="overflow-x:auto"><table class="table table-bordered table-sm" style="margin:0"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table></div>`);
	$w.find("[data-subject]").on("click", function () {
		const sheet = this.dataset.sheet;
		if (sheet) frappe.set_route("Form", "Exam Mark Sheet", sheet);
		else frappe.new_doc("Exam Mark Sheet", { exam: frm.doc.name, stream: this.dataset.stream, subject: this.dataset.subject });
	});
}

// Approve a whole class (or a few sheets) at once, after a glance at each sheet's numbers
function approve_dialog(frm) {
	frappe.call("school_erp.api.exams.approval_queue", { exam: frm.doc.name }).then(({ message: groups }) => {
		const esc = frappe.utils.escape_html;
		if (!groups.length) return frappe.msgprint(__("Nothing is waiting for your approval."));
		const d = new frappe.ui.Dialog({
			title: __("Approve marks: {0}", [frm.doc.exam_name || frm.doc.name]), size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "list" }],
			primary_action_label: __("Approve selected"),
			primary_action() {
				const names = d.$wrapper.find("input[data-sheet]:checked").map((i, el) => el.dataset.sheet).get();
				if (!names.length) return frappe.msgprint(__("Tick the mark sheets to approve"));
				frappe.call({ method: "school_erp.api.exams.approve_sheets", args: { names }, freeze: true, freeze_message: __("Approving...") })
					.then(({ message: r }) => {
						d.hide();
						frappe.show_alert({ message: __("{0} mark sheet(s) approved", [r.approved]), indicator: "green" }, 6);
						if (r.failed.length) frappe.msgprint({ title: __("Not approved"), indicator: "orange",
							message: r.failed.map((f) => `<div><b>${esc(f.name)}</b>: ${esc(f.error)}</div>`).join("") });
						frm.reload_doc();
					});
			},
		});
		const html = groups.map((g) => `
			<div style="margin-bottom:14px">
				<label style="font-weight:600;display:flex;gap:8px;align-items:center;margin-bottom:6px">
					<input type="checkbox" data-class="${esc(g.school_class)}" checked> ${esc(g.school_class)}
					<span class="text-muted small" style="font-weight:400">${__("{0} sheets", [g.sheets.length])}</span></label>
				<div style="overflow-x:auto"><table class="table table-sm table-bordered" style="margin:0">
					<thead><tr><th></th><th>${__("Stream")}</th><th>${__("Subject")}</th><th>${__("Teacher")}</th>
						<th class="text-right">${__("Students")}</th><th class="text-right">${__("Absent")}</th>
						<th class="text-right">${__("Average")}</th><th class="text-right">${__("High / Low")}</th><th></th></tr></thead>
					<tbody>${g.sheets.map((s) => `<tr>
						<td><input type="checkbox" data-sheet="${esc(s.name)}" data-in="${esc(g.school_class)}" checked></td>
						<td>${esc(s.stream)}</td><td>${esc(s.subject)}</td><td>${esc(s.teacher_name || "")}</td>
						<td class="text-right">${s.entered}</td><td class="text-right">${s.absent || ""}</td>
						<td class="text-right"><b>${s.average}</b> / ${s.max_marks}</td><td class="text-right">${s.highest} / ${s.lowest}</td>
						<td><a href="${frappe.utils.get_form_link("Exam Mark Sheet", s.name)}" target="_blank">${__("Open")}</a></td></tr>`).join("")}</tbody>
				</table></div>
			</div>`).join("");
		d.fields_dict.list.$wrapper.html(`<p class="text-muted small">${__("Check the averages, open any sheet that looks wrong to return it with a reason, then approve the rest.")}</p>${html}`);
		d.$wrapper.on("change", "input[data-class]", function () {
			d.$wrapper.find(`input[data-in="${CSS.escape(this.dataset.class)}"]`).prop("checked", this.checked);
		});
		d.show();
	});
}
