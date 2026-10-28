# School Webhook Management — Phase 2 (draft)

Each Frappe school site stores its own **School Webhook Endpoint** and
**School Webhook Delivery** records. Endpoints are configured with HTTPS
URLs, a signing secret, an enabled switch, event names (one per line), and
an attempt cap. Use only explicit events:
`student.created`, `fee_payment.posted`, `attendance.recorded`,
`invoice.submitted`.

The internal `school_erp.api.webhooks.publish(event_id, event_type, payload)`
accepts a pre-redacted, small event payload, deduplicates one delivery per
endpoint/event pair, and enqueues after transaction commit. The dispatcher
signs the exact JSON payload using HMAC SHA-256 in
`X-Stemic-Signature-SHA256`, and includes the event name and delivery ID.
HTTP 2xx is an **acceptance**, not proof that the external consumer applied
the change. Other responses retry at most five times, with backoff.

**Do not enable in production yet.** This draft requires a hardened egress
transport that pins a validated public IP across DNS resolution and the TLS
connection to prevent DNS rebinding/SSRF. The initial `requests` transport
re-resolves the hostname after validation and therefore is not sufficient
for hostile endpoint configurations. Infrastructure-level egress policy must
also deny internal networks and metadata addresses. Retries are not
exactly-once; receivers should deduplicate by `X-Stemic-Delivery`. An
interrupted `Sending` job is deliberately not automatically retried.

The event producers are **not wired** by this PR. Events must be published
only after final transaction state is committed, using an explicit
allowlisted data schema without personal, financial, or credential fields by
default. Add integration tests of a real receiving server, external timeouts,
worker kills, permissions, and tenant isolation before release.

This PR is stacked on #39 → #38 → #37, and remains draft.
