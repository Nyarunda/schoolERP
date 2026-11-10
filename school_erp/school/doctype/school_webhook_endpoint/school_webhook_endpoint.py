from frappe.model.document import Document


class SchoolWebhookEndpoint(Document):
    def validate(self):
        from school_erp.api.webhooks import validate_target, ALLOWED_EVENTS
        from frappe import throw
        validate_target(self.endpoint_url)
        events = set((self.event_types or "").splitlines())
        if not events or not events.issubset(ALLOWED_EVENTS):
            throw("Unsupported webhook event type")
        if not self.get_password("secret", raise_exception=False):
            throw("Webhook signing secret required")
