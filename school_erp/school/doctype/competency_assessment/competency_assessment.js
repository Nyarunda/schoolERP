// Copyright (c) 2026, School ERP and contributors
// Formative CBC assessment: one strand (optionally a sub-strand) for one stream; each learner gets a rubric level.

frappe.ui.form.on("Competency Assessment", {
	setup(frm) {
		frm.set_query("stream", () => ({ filters: { is_active: 1 } }));
		frm.set_query("strand", () => ({ filters: { is_active: 1, subject: frm.doc.subject || "", school_class: frm.doc.school_class || "" } }));
	},

	refresh(frm) {
		frappe.call("school_erp.api.cbc.rubric_levels", { rubric: frm.doc.rubric || "" }).then(({ message: r }) => {
			frm._levels = r.levels;
			frm.fields_dict.results.grid.update_docfield_property("level", "options", ["", ...r.levels.map((l) => l.level)].join("\n"));
			if (frm.doc.docstatus === 0) {
				const key = r.levels.map((l) => `<b>${l.level}</b> ${frappe.utils.escape_html(l.descriptor)}`).join(" · ");
				frm.set_intro(__("Pick the stream, learning area and strand, then Get Learners. Choose each learner's level: {0}. Submit when the class is done.", [key]), "blue");
			}
		});
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Learners"), () => get_learners(frm));
			frm.add_custom_button(__("Fill Blank Levels"), () => fill_blanks(frm));
		}
		if (frm.doc.docstatus === 1 && frm.doc.distribution) frm.dashboard.add_indicator(frm.doc.distribution, "blue");
		load_sub_strands(frm);
	},

	subject(frm) { frm.set_value("strand", ""); },
	stream(frm) { if (frm.doc.stream && !(frm.doc.results || []).length) get_learners(frm); },
	strand(frm) { frm.set_value("sub_strand", ""); load_sub_strands(frm); },
});

function load_sub_strands(frm) {
	if (!frm.doc.strand) return;
	frappe.call("school_erp.api.cbc.sub_strands", { strand: frm.doc.strand }).then(({ message }) => {
		frm.set_df_property("sub_strand", "options", message || []);
	});
}

function get_learners(frm) {
	if (!frm.doc.stream) return frappe.msgprint(__("Choose the stream first"));
	frappe.call("school_erp.api.cbc.stream_students", { stream: frm.doc.stream }).then(({ message }) => {
		const have = new Set((frm.doc.results || []).map((r) => r.student));
		let added = 0;
		(message || []).forEach((s) => {
			if (have.has(s.student)) return;
			frm.add_child("results", { student: s.student, student_name: s.student_name });
			added += 1;
		});
		frm.refresh_field("results");
		frappe.show_alert({ message: __("{0} learners added", [added]), indicator: "green" });
	});
}

function fill_blanks(frm) {
	const options = (frm._levels || []).map((l) => l.level);
	frappe.prompt({ fieldname: "level", label: __("Level"), fieldtype: "Select", options, reqd: 1 }, ({ level }) => {
		(frm.doc.results || []).forEach((r) => { if (!r.level) r.level = level; });
		frm.refresh_field("results");
		frm.dirty();
	}, __("Give every learner without a level"), __("Fill"));
}
