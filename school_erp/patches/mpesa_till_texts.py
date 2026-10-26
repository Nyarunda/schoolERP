import frappe

# Default texts that assumed a Paybill. A school that edited them keeps its own wording.
OLD_TO_NEW = {
	"payment_instructions": (
		"Pay via M-Pesa Paybill {paybill}, Account No: {student_id}. Always use the Student ID as the account number.",
		"Pay via {mpesa}. For a Paybill, always use the Student ID as the account number.",
	),
	"billing_sms_template": (
		"Dear {guardian_name}, {term} fees for {first_name} ({student_id}) have been posted. Balance due: {balance}, by {due_date}. Paybill {paybill}, Acc {student_id}. {school_name}",
		"Dear {guardian_name}, {term} fees for {first_name} ({student_id}) have been posted. Balance due: {balance}, by {due_date}. Pay via {mpesa}. {school_name}",
	),
	"reminder_sms_template": (
		"Dear {guardian_name}, kindly clear {first_name}'s fee balance of {balance}. Paybill {paybill}, Acc {student_id}. {school_name}",
		"Dear {guardian_name}, kindly clear {first_name}'s fee balance of {balance}. Pay via {mpesa}. {school_name}",
	),
}


def execute():
	"""Switch untouched default texts to {mpesa}, which reads right for a Paybill and for a Till."""
	for field, (old, new) in OLD_TO_NEW.items():
		if (frappe.db.get_single_value("School Settings", field) or "").strip() == old:
			frappe.db.set_single_value("School Settings", field, new)
	if not frappe.db.get_single_value("School Settings", "mpesa_account_type"):
		frappe.db.set_single_value("School Settings", "mpesa_account_type", "Paybill")
