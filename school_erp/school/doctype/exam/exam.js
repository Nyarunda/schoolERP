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
				.then(({ message }) => { frappe.show_alert({ message: __("{0} report cards ready", [message.report_cards]), indicator: "green" }); frm.reload_doc(); }),
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
		frappe.call("school_erp.api.exams.exam_progress", { exam: frm.doc.name }).then(({ message: p }) => render_progress(frm, p));
	},
});

function render_progress(frm, p) {
	const esc = frappe.utils.escape_html;
	const icon = { done: "✓", draft: "…", missing: "" };
	const color = { done: "var(--green-600)", draft: "var(--orange-600)", missing: "var(--text-light)" };
	const head = p.subjects.map((s) => `<th style="font-size:11px;padding:4px 6px;text-align:center">${esc(s)}</th>`).join("");
	const rows = p.rows.map((r) => `<tr><td style="padding:4px 6px;white-space:nowrap">${esc(r.stream)}</td>${r.cells.map((c) =>
		`<td style="text-align:center;padding:4px 6px;color:${color[c.state]};font-weight:600;cursor:pointer"
			data-sheet="${esc(c.sheet || "")}" data-stream="${esc(r.stream)}" data-subject="${esc(c.subject)}"
			title="${esc(r.stream)} · ${esc(c.subject)}: ${c.state === "done" ? __("submitted") : c.state === "draft" ? __("in progress") : __("not started")}">${icon[c.state] || "·"}</td>`).join("")}</tr>`).join("");
	const $w = frm.get_field("progress_html").$wrapper;
	$w.html(`<div style="margin-bottom:8px"><b>${p.done}</b> ${__("of")} <b>${p.total}</b> ${__("mark sheets submitted")}
		<span class="text-muted small">&nbsp; ✓ ${__("submitted")} · … ${__("in progress")} · ${__("click a cell to enter marks")}</span></div>
		<div style="overflow-x:auto"><table class="table table-bordered table-sm" style="margin:0"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table></div>`);
	$w.find("[data-subject]").on("click", function () {
		const sheet = this.dataset.sheet;
		if (sheet) frappe.set_route("Form", "Exam Mark Sheet", sheet);
		else frappe.new_doc("Exam Mark Sheet", { exam: frm.doc.name, stream: this.dataset.stream, subject: this.dataset.subject });
	});
}
