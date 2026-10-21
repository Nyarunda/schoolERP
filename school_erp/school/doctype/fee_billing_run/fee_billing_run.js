// Copyright (c) 2026, School ERP and contributors
// Invoice a term for all students or a filtered group: get students & fees, review, untick, post.

frappe.ui.form.on("Fee Billing Run", {
	setup(frm) {
		frm.set_query("stream", () => {
			const classes = (frm.doc.classes || []).map((c) => c.school_class);
			return classes.length ? { filters: { school_class: ["in", classes] } } : {};
		});
	},

	school_term(frm) {
		if (frm.doc.school_term && !frm.doc.due_date) {
			frappe.db.get_value("School Term", frm.doc.school_term, "start_date").then(({ message }) => {
				frm.set_value("due_date", frappe.datetime.add_days(message.start_date, 14));
			});
		}
	},

	refresh(frm) {
		frm.set_df_property("students", "cannot_add_rows", 1);
		frm.fields_dict.students.grid.update_docfield_property("include", "read_only", frm.doc.docstatus !== 0);
		show_summary(frm);

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Students & Fees"), () => get_students(frm)).addClass(frm.doc.students && frm.doc.students.length ? "" : "btn-primary");
			if ((frm.doc.students || []).length) {
				frm.add_custom_button(__("Tick all"), () => set_all(frm, 1), __("Students"));
				frm.add_custom_button(__("Untick all"), () => set_all(frm, 0), __("Students"));
				frm.page.set_primary_action(__("Post {0} Invoices", [frm.doc.total_students || 0]), () => post(frm));
				frm.set_intro(__("Check the students and totals below. Untick anyone you don't want to invoice now, then click Post."), "blue");
			} else {
				frm.set_intro(__("Choose the term and, if you like, classes, a stream or Day/Boarder (blank = everyone). Then click Get Students & Fees."), "blue");
			}
			if (frm.doc.auto_generated) {
				frm.dashboard.set_headline_alert(__("Created automatically at the start of the term, ready for your review."), "blue");
			}
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Invoices"), () => frappe.set_route("List", "Sales Invoice", { fee_billing_run: frm.doc.name }));
			if (["Queued", "Running"].includes(frm.doc.status)) {
				frm.dashboard.set_headline_alert(__("Posting invoices..."), "blue");
				frappe.realtime.on("fee_billing_run_done", (d) => d.name === frm.doc.name && frm.reload_doc());
				setTimeout(() => ["Queued", "Running"].includes(frm.doc.status) && frm.reload_doc(), 6000);
			} else if (frm.doc.status === "Completed with Errors") {
				frm.dashboard.set_headline_alert(__("Some students could not be invoiced. See the Error rows below."), "orange");
			}
		}
	},
});

frappe.ui.form.on("Fee Billing Run Student", {
	include(frm) {
		recalc(frm);
	},
});

function get_students(frm) {
	if (!frm.doc.school_term) return frappe.msgprint(__("Choose the term first"));
	const go = () => frm.call({ doc: frm.doc, method: "get_students", freeze: true, freeze_message: __("Working out each student's fees...") })
		.then(({ message: m }) => {
			frm.refresh_fields();
			frm.dirty();
			frm.save().then(() => {
				let msg = __("{0} students to invoice, total {1}.", [m.students, format_currency(m.amount)]);
				if (m.already_billed) msg += " " + __("{0} already invoiced for this term (left out).", [m.already_billed]);
				if (m.no_fees) msg += " " + __("{0} have no fees in the fee structure.", [m.no_fees]);
				frappe.show_alert({ message: msg, indicator: "green" }, 8);
			});
		});
	if ((frm.doc.students || []).length) {
		frappe.confirm(__("Refresh the list? Any unticked students will be ticked again."), go);
	} else {
		go();
	}
}

function set_all(frm, include) {
	(frm.doc.students || []).forEach((r) => (r.include = include));
	frm.refresh_field("students");
	recalc(frm);
}

function recalc(frm) {
	// live totals while ticking/unticking (the server recomputes on save)
	let count = 0, total = 0;
	const by = {};
	(frm.doc.students || []).forEach((r) => {
		if (!r.include) return;
		count += 1;
		total += r.total || 0;
		JSON.parse(r.lines_json || "[]").forEach((l) => {
			const amt = Math.round(l.amount * (1 - (l.discount_percent || 0) / 100) * 100) / 100;
			by[l.fee_type] = by[l.fee_type] || { students: 0, amount: 0 };
			by[l.fee_type].students += 1;
			by[l.fee_type].amount += amt;
		});
	});
	frm.set_value("total_students", count);
	frm.set_value("total_amount", total);
	frm.clear_table("fee_summary");
	Object.entries(by).forEach(([fee_type, v]) => frm.add_child("fee_summary", { fee_type, students: v.students, amount: v.amount }));
	frm.refresh_field("fee_summary");
	frm.page.set_primary_action(__("Post {0} Invoices", [count]), () => post(frm));
	show_summary(frm);
}

function post(frm) {
	const doit = () => frappe.confirm(
		__("Create {0} invoices totalling {1} for {2}?", [frm.doc.total_students, format_currency(frm.doc.total_amount), frm.doc.school_term]) +
			(frm.doc.send_notifications ? "<br>" + __("Parents will be notified.") : ""),
		() => frm.savesubmit());
	frm.is_dirty() ? frm.save().then(doit) : doit();
}

function show_summary(frm) {
	const w = frm.fields_dict.sb_totals && frm.fields_dict.sb_totals.wrapper;
	if (!frm.doc.students || !frm.doc.students.length) return;
	const done = frm.doc.students.filter((r) => r.status === "Invoiced").length;
	const err = frm.doc.students.filter((r) => r.status === "Error").length;
	if (frm.doc.docstatus === 1) {
		frm.dashboard.clear_headline();
		frm.dashboard.add_indicator(__("{0} invoiced", [done]), "green");
		if (err) frm.dashboard.add_indicator(__("{0} errors", [err]), "red");
		frm.dashboard.add_indicator(__("Total {0}", [format_currency(frm.doc.total_billed)]), "blue");
	}
}
