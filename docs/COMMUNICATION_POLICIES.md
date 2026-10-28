# Communication policies — Phase 1C groundwork

School ERP already stores guardian SMS/email preferences (`Student Guardian.receive_sms` and `receive_email`) and obtains guardian contacts via `get_guardian_contacts`. These preferences remain the primary per-recipient contact selection mechanism in the existing School ERP messaging flows.

## SMS budget controls

New settings under **School Settings → SMS & Email**:

- Daily SMS Attempt Limit (0 means no cap).
- Monthly SMS Attempt Limit (0 means no cap).

The queued **School Notification Delivery** sender introduced in PR #38 now reserves one attempt against both counters *before* calling the external SMS provider. It uses transaction row locks, fixed lock ordering, and commits the reservation before provider I/O. Attempts are counted even if provider submission fails. The usage counters live in each school's own site database.

**Important:** These caps currently protect the **new queued sender only**. Legacy bulk School Message SMS, fee-payment SMS, and other direct calls to `send_sms` are not yet routed through the ledger, and therefore cannot be described as quota-protected. Do not depend on this feature as a tenant-wide cost ceiling until all SMS producers are moved through the same policy and the concurrency tests have passed.

## Preferences and consent

Existing guardian `receive_sms` / `receive_email` flags are preserved, but opt-in evidence, quiet hours, transactional vs promotional category, legal basis and audit trail are **not yet implemented**. In particular, callers of the low-level `queue_delivery` API must select recipients only after checking their contact preference and applicable consent rules.

## Release dependency

Stacked on #38, which is stacked on #37. CI and a real Frappe/MariaDB concurrency test must pass before production usage.
