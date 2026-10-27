// Money from students comes in through Fee Payment (it allocates to fee types and sends the receipt), so receiving
// from a customer here is for normal customers. Refunds paid out to a student stay possible.
frappe.ui.form.on("Payment Entry", {
	onload: (frm) => school_erp.exclude_students(frm, "party", school_erp_receiving_from_customer),
	refresh: (frm) => school_erp.exclude_students(frm, "party", school_erp_receiving_from_customer),
	party_type: (frm) => school_erp.exclude_students(frm, "party", school_erp_receiving_from_customer),
});

function school_erp_receiving_from_customer(doc) {
	return doc.party_type === "Customer" && doc.payment_type === "Receive";
}
