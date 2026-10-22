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
	},
});

frappe.ui.form.on("Student Promotion Item", {
	action(frm) {
		frm.dirty();
		frm.save();  // the server recomputes destinations and totals
	},
});
