import frappe
from frappe import _
from frappe.model.document import Document


class SchoolSMSGateway(Document):
	def validate(self):
		from school_erp.api.sms_gateway import check_url

		self.url = (self.url or "").strip()
		check_url(self.url)
		for field in ("recipient_param", "message_param", "api_key_param", "sender_param", "success_field"):
			self.set(field, (self.get(field) or "").strip())
		self.timeout = min(max(int(self.timeout or 20), 5), 60)
		if self.success_field and not (self.success_values or "").strip():
			frappe.throw(_("Enter the Success Values that {0} holds when a message is accepted").format(self.success_field))
		if self.enabled and not (self.success_field or self.success_text):
			frappe.msgprint(_("No success rule is set, so any HTTP 200 reply counts as sent. Many gateways reply 200 "
							  "even when a message fails: set Success Field or Reply Contains from the provider's documentation."),
							indicator="orange", alert=True)
