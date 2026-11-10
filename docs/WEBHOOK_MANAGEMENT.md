# School Webhook Management — Phase 2 (draft)

Each Frappe school site stores its own **School Webhook Endpoint** and
**School Webhook Delivery** records. Endpoints are configured with HTTPS
URLs, a signing secret, an enabled switch, event names (one per line), and
an attempt cap. School Admins and System Managers can create, change and
delete endpoints; deliveries are read-only to them (only the service writes
them). The signing secret is a password field and is never returned by the
API.

## Events

| Event | Sent when | `data` |
| --- | --- | --- |
| `student.created` | a Student is inserted | `student`, `school_class` |
| `fee_payment.posted` | a Fee Payment is submitted | `fee_payment`, `student`, `posting_date` |
| `invoice.submitted` | a student's Sales Invoice is submitted (not returns) | `invoice`, `student`, `school_term`, `posting_date` |

Every body is `{"id", "type", "site", "occurred_at", "data"}`. Events are
**thin**: identifiers only, no names, phone numbers, guardians or amounts. A
receiver that needs more reads it through the API with its own credentials,
so what leaves the school is only what that user may see. `id` is stable
(`<DocType>:<name>:<event>`): one delivery per endpoint and event.

The delivery rows are written in the document's own transaction (rolled back
with it) and the send is enqueued after commit. A webhook problem never
blocks the school's own work: it is written to the Error Log instead.

## Delivery

The dispatcher signs the exact JSON body with HMAC SHA-256 in
`X-Stemic-Signature-SHA256` and sends `X-Stemic-Event` and
`X-Stemic-Delivery`. HTTP 2xx is an **acceptance**, not proof that the
consumer applied the change. Other responses and network errors retry with
backoff (2, 4, 8… minutes) up to the endpoint's cap (at most five), then
stop as Failed. Retries are not exactly-once; receivers should deduplicate
by `X-Stemic-Delivery`. An interrupted `Sending` job is deliberately not
retried automatically.

## Destination safety (SSRF and DNS rebinding)

The URL must be `https` on port 443, without credentials, and not a
`localhost`/`.local` name. Each delivery resolves the name **once** and is
refused unless **every** address is public (no private, loopback,
link-local, metadata, unique-local or IPv4-mapped private addresses). It
then connects to that exact address with TLS verified against the name (SNI
and certificate), with no proxies, no redirects and a bounded response read.
Nothing re-resolves the name between the check and the connection, so a DNS
answer that changes after validation cannot point a delivery at the server's
own network. The endpoint is also checked when it is saved.

Tests (`school_erp/tests/test_webhooks.py`) deliver to a real local TLS
receiver and cover pinning (one DNS lookup per delivery, Host and SNI set to
the name), a rebinding answer refused before connecting, a certificate for
another name refused, retries and their cap, deduplication, the producers,
and permissions.

## Before production

- An egress firewall that denies internal networks and the metadata address
  to the workers is still recommended as a second layer.
- Callback receivers are external: test with each real consumer, including
  timeouts and its deduplication.
- No `attendance.recorded` event: School ERP has no attendance document yet.
