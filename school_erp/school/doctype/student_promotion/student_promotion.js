// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Student Promotion", {
	refresh(frm) {
		frm.set_df_property("items", "cannot_add_rows", 1);
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Students"), () => {
				const go = () => frm.call({ doc: frm.doc, method: "get_students", freeze: true }).then(() => {
					frm.refresh_fields();
					frm.dirty();
					frm.save();
				});
				(frm.doc.items || []).length ? frappe.confirm(__("Reload the list? Changes to actions will be lost."), go) : go();
			}).addClass((frm.doc.items || []).length ? "" : "btn-primary");
			if ((frm.doc.items || []).length) {
				frm.set_intro(__("Each student moves to the next class in the same stream (e.g. Grade 4 East → Grade 5 East); the top class graduates. Change 'Action' to Repeat or Left School for anyone who shouldn't move up, save, then Submit. Fee balances stay on each student's account and carry into next year's statements."), "blue");
				frm.page.set_primary_action(__("Promote {0} students", [frm.doc.total_students]), () =>
					frappe.confirm(__("Promote {0}, graduate {1}, keep {2} in their class?", [frm.doc.to_promote, frm.doc.to_graduate, frm.doc.to_repeat]),
						() => frm.savesubmit()));
			} else {
				frm.set_intro(__("Choose the years and (optionally) classes, then click Get Students. Make sure each class's 'Next Class' is set."), "blue");
			}
		}
		if (frm.doc.docstatus === 1 && frappe.model.can_write("Student")) {
			frm.add_custom_button(__("Move a Student Back"), () => move_back_dialog(frm));
		}
	},
});

// A learner promoted by mistake (or who must repeat): back to the stream they were promoted from
function move_back_dialog(frm) {
	frappe.call("school_erp.api.students.promoted_students", { promotion: frm.doc.name }).then(({ message: rows }) => {
		if (!rows.length) return frappe.msgprint(__("No promoted learner left to move back."));
		const d = new frappe.ui.Dialog({
			title: __("Move a student back"),
			fields: [
				{ fieldname: "student", label: __("Learner"), fieldtype: "Select", reqd: 1,
					options: rows.map((r) => ({ value: r.student, label: `${r.student_name} (${r.new_stream} → ${r.current_stream})` })) },
				{ fieldname: "reason", label: __("Reason"), fieldtype: "Select", reqd: 1,
					options: ["Repeating the class", "Promoted by mistake"].join("\n"), default: "Repeating the class" },
				{ fieldname: "note", label: __("Note"), fieldtype: "Small Text" },
			],
			primary_action_label: __("Move Back"),
			primary_action(v) {
				d.hide();
				frappe.call({ method: "school_erp.api.students.move_back_from_promotion", freeze: true,
					args: { promotion: frm.doc.name, ...v } }).then(({ message: r }) => {
					frappe.show_alert({ message: __("Moved back to {0}", [r.to]), indicator: "green" });
					if (r.warning) frappe.msgprint({ title: __("Check the fees"), indicator: "orange", message: frappe.utils.escape_html(r.warning) });
					frm.reload_doc();
				});
			},
		});
		d.show();
	});
}

frappe.ui.form.on("Student Promotion Item", {
	action(frm) {
		frm.dirty();
		frm.save();  // the server recomputes destinations and totals
	},
});
