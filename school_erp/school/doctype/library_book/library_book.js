// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Library Book", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Add Copies"), () => frappe.prompt([
			{ fieldname: "prefix", label: __("Accession prefix"), fieldtype: "Data", default: "ACC-" },
			{ fieldname: "start", label: __("First number"), fieldtype: "Int", reqd: 1, default: (frm.doc.copies || []).length + 1 },
			{ fieldname: "count", label: __("How many copies"), fieldtype: "Int", reqd: 1, default: 1 },
		], ({ prefix, start, count }) => {
			for (let i = 0; i < count; i++) frm.add_child("copies", { accession_no: `${prefix || ""}${String(start + i).padStart(4, "0")}`, status: "Available", condition: "New" });
			frm.refresh_field("copies");
			frm.save();
		}, __("Add copies"), __("Add")));
		if (frm.doc.available_copies) frm.add_custom_button(__("Issue a Copy"), () => frappe.new_doc("Library Loan", { book: frm.doc.name }));
	},
});
