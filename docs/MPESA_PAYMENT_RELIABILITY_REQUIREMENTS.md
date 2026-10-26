# M-Pesa payment reliability and callback requirements

Status: implementation requirements. Paybill C2B hardening is in PR #17; STK Push is a separate implementation track. This document does **not** claim the STK flow is implemented.

## Scope and boundaries

Applies to SchoolERP and reusable payment-engine design for Stemic Billing and POS integrations. Each product requires its own explicit integration adapter, tenant-scoped policy, accounting mappings and end-to-end testing. Safaricom's C2B payment confirmation, STK Push request acceptance, STK payment result callback and STK transaction-status query are **not interchangeable**.

## Functional requirements

**MP-01 — Transaction initiation.** An STK initiation must write a payment intent before invoking Safaricom (client-generated idempotency key, tenant/site ID, student/account/invoice, normalized MSISDN, expected currency and amount, requester, timestamps, expiry). On a successful request acceptance response, durably record *both* `MerchantRequestID` and `CheckoutRequestID` and a `Pending` state; do not mark payment successful on HTTP 200 or `ResponseCode=0`. On API transport uncertainty, keep an explicit `Initiation Unknown` state for investigation; avoid blind repeated prompts.

**MP-02 — Callback authentication.** Use Safaricom/provider-approved controls (high-entropy callback path token where supported; HTTPS, secrets stored securely, optional published IP allowlisting, request size bounds, schema validation and monitoring). Do not treat a guessed `CheckoutRequestID`, matching phone, or matching amount as authentication. Tenant/site routing must be derived from trusted configuration, not arbitrary callback fields.

**MP-03 — Durable webhook inbox.** After cheap authentication and envelope checks, persist original callback bytes/payload, received timestamp, tenant/site, event hash, correlation IDs, and delivery state in a durable database inbox with database uniqueness constraints. ACK promptly **only after successful durable persistence**. Enqueue after commit for background processing. If persistence fails, return a failure response so retries can occur according to the provider contract. A duplicate delivery should return the provider's success ACK without reapplying funds. Verify the exact Daraja endpoint's expected acknowledgement shape (C2B and STK may differ).

**MP-04 — Reconciliation of missing/unknown callbacks.** Save unmatched or suspicious callbacks in a non-postable exception state; notify finance staff. Reconcile pending STK payment status using the relevant Safaricom query API after an appropriate timeout/backoff, respecting rate limits. Never treat a timeout as payment failure or success. Provide controlled manual reconciliation with evidence, reason, actor and audit log.

**MP-05 — Exact match and integrity.** Correlate on `CheckoutRequestID` and validate `MerchantRequestID` when available, tenant/site, short code, amount, currency, and expected merchant/account. Validate final receipt/transaction code and canonical provider result. Reject contradictions into Needs Review. Where Safaricom doesn't supply an attribute in a callback, use previously authenticated request details rather than inventing verification.

**MP-06 — Single accounting effect.** Unique constraints for callback event identity, checkout request, M-Pesa receipt number and posted payment reference. Use DB locking/state transitions so simultaneous workers and provider retries cannot post more than one Fee Payment / Payment Entry. Only verified success can allocate invoices and trigger service activation, attendance clearance, receipt SMS or customer-facing success. Reconcile manual payments that used the same receipt code.

**MP-07 — Lifecycle.** Suggested states: Created → Initiated → Pending → Confirmed → Posted; plus Initiation Unknown, Failed (confirmed), Expired (after authoritative check), Unmatched, Needs Review, Posting Failed, Reversed. Keep provider-reported status separate from accounting posting status. Every transition records its provenance and time. Do not allow manual override of invalid callback evidence by simply changing status.

**MP-08 — Tenant isolation and least privilege.** No cross-tenant resolution or leakage of learner, contact or fee data. Guest webhooks have no permission to read transactions, submit fees or invoke internal posting; workers use bounded privileged operations. Encrypt/redact PII and credentials, limit raw payload retention, and never log access tokens, callback URL secrets or full phone numbers.

**MP-09 — Reliability / operations.** Durable queue recovery scan for stored unprocessed events, bounded retry policy with exponential backoff, poison-event quarantine, observable age-of-pending, missed callbacks, unmatched exceptions, duplicate deliveries and reconciliations; alerts and operational dashboard drill-downs. ACK fast enough for Safaricom's current timeout/retry contract; don't run invoice posting inside the webhook response path.

**MP-10 — Audit and reporting.** Preserve immutable event and transition history, correlation IDs, provider references, Fee Payment / Payment Entry IDs, actor and reason for intervention. Reconciliation reports compare Safaricom confirmations, transaction ledger, ERPNext posting and bank settlement. Use separate audit records for reversal/refund handling.

## Delivery scope and acceptance tests

### Existing SchoolERP Paybill C2B
- [ ] Valid confirmation is stored durably before ACK and posted only by worker.
- [ ] Duplicate C2B `TransID` never posts a second receipt.
- [ ] Redis queue unavailable: ACK only if record was stored and background recovery posts later.
- [ ] MariaDB unavailable: failure response, no false ACK.
- [ ] Invalid token/shortcode/amount cannot trigger posting.
- [ ] Needs Review cannot be posted by automated retry or simple bursar action.
- [ ] Same receipt code manually entered in ERPNext is not double-posted.

### STK Push (separate feature, not implemented by this requirements push)
- [ ] Initiation writes intent, then persists both request IDs from accepted Express response.
- [ ] Request HTTP 200 does not change ledger balances or report payment success.
- [ ] Successful authenticated callback is durably ACKed and exactly-once applied.
- [ ] Duplicate, concurrent and out-of-order callbacks cannot post twice.
- [ ] Unmatched callback is quarantined; never dropped silently or falsely posted.
- [ ] Delayed/missing callback can be queried without blind duplicate prompts.
- [ ] Safaricom negative result/timeout/ambiguous query correctly remains distinguishable.
- [ ] School/tenant/account/payment amount mismatches cannot cross-post.
- [ ] Cancel/reversal/refund is audited and does not mutate original payment proof.

## Deployment gates

Run `bash scripts/check.sh`, Frappe v16 integration tests on a disposable site, Daraja sandbox end-to-end tests, then production credential and endpoint validation with IP/token controls. Test retries, lost Redis, lost DB, concurrent callbacks and reconciliation. Do not merge or enable automatic production posting solely on static source-contract tests.

## Implementation notes

Prefer a dedicated append-only M-Pesa Callback Inbox DocType and an STK Payment Intent DocType, backed by database uniqueness for `CheckoutRequestID` and provider receipt number; split HTTP ingress, durable recording, job worker and ERPNext posting. The Paybill C2B flow can share idempotent ledger/event infrastructure but should keep its separate Safaricom envelope semantics.
