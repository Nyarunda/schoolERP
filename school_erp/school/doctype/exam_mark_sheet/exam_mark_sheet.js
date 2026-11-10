// Copyright (c) 2026, School ERP and contributors
// Fast marks entry: pick exam, stream, subject; students fill in; type marks and press Enter to move down.

frappe.ui.form.on("Exam Mark Sheet", {
	setup(frm) {
		frm.set_query("stream", () => (frm._exam_classes && frm._exam_classes.length
			? { filters: { is_active: 1, school_class: ["in", frm._exam_classes] } } : { filters: { is_active: 1 } }));
		frm.set_query("subject", () => (frm._exam_subjects && frm._exam_subjects.length ? { filters: { name: ["in", frm._exam_subjects] } } : {}));
	},

	onload(frm) {
		load_exam(frm);
	},

	refresh(frm) {
		frm.set_df_property("marks", "cannot_add_rows", 1);
		if (frm.doc.docstatus === 0) {
			const st = frm.doc.approval_status;
			const has_workflow = !!frappe.model.has_workflow(frm.doctype);
			if (st === "Pending Approval") {
				frm.set_intro(__("Waiting for approval by {0}. Approvers use the Actions menu to Approve or Return it.", [frm.doc.reviewer || __("the Head Teacher")]), "orange");
			} else if (st === "Returned") {
				frm.set_intro(__("Returned for correction: {0}. Fix the marks, Save, then Actions → Resend.", [frm.doc.review_comment || ""]), "red");
			} else {
				frm.set_intro(has_workflow
					? __("Type each student's marks (out of {0}). Tick Absent for anyone who missed the exam. Save as you go; when the class is done choose Actions → Send for Approval.", [frm.doc.max_marks || 100])
					: __("Type each student's marks (out of {0}). Tick Absent for anyone who missed the exam. Save as you go; Submit when the whole class is done.", [frm.doc.max_marks || 100]), "blue");
			}
		}
		if (frm.doc.docstatus === 1 && frm.doc.approved_by) {
			frm.dashboard.add_indicator(__("Approved by {0}", [frappe.user.full_name(frm.doc.approved_by)]), "green");
		}
		if (frm.doc.docstatus === 1) {
			frm.dashboard.add_indicator(__("Average {0}", [frm.doc.average]), "blue");
			frm.dashboard.add_indicator(__("Highest {0} · Lowest {1}", [frm.doc.highest, frm.doc.lowest]), "gray");
		}
		frm.fields_dict.marks.grid.wrapper.off("keydown.marks").on("keydown.marks", 'input[data-fieldname="marks"]', function (e) {
			if (e.key !== "Enter") return;
			e.preventDefault();
			const $rows = frm.fields_dict.marks.grid.wrapper.find(".grid-row");
			const idx = $(this).closest(".grid-row").index();
			const $next = $rows.eq(idx + 1).find('[data-fieldname="marks"]');
			if ($next.length) $next.trigger("click").find("input").focus();
		});
	},

	// Frappe Workflow hook: ask what needs correcting before "Return" (the Reject action)
	before_workflow_action(frm) {
		return school_dash.reason_before_reject(frm, "review_comment");
	},

	exam(frm) {
		load_exam(frm);
		fill(frm);
	},
	stream: fill,
	subject: fill,
});

function fill(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.exam || !frm.doc.stream || !frm.doc.subject) return;
	if ((frm.doc.marks || []).length) return;
	frm.call({ doc: frm.doc, method: "get_students", freeze: true }).then(() => frm.refresh_field("marks"));
}

function load_exam(frm) {
	if (!frm.doc.exam) return;
	frappe.db.get_doc("Exam", frm.doc.exam).then((e) => {
		frm._exam_classes = (e.classes || []).map((c) => c.school_class);
		frm._exam_subjects = (e.subjects || []).map((s) => s.subject);
	});
}
