# SchoolERP review recommendations

## Critical

- Make callback storage durable before acknowledging receipt and reconcile missed provider notifications.
- Ensure concurrent and duplicate callbacks post only once using database constraints and locks.
- Validate shortcode, account, transaction identity, amount, and company.
- Verify STK receipt details against the original payment request; distinguish provider-paid from ledger-posted.
- Authorize every parent-to-student API interaction.

## High priority

- Implement a documented payment state machine, retries with backoff, and an exception workbench.
- Use decimal-safe money processing and test all fee allocations, advances, cancellations, and general ledger effects.
- Restrict editing/deleting provider-confirmed records and audit manual reconciliation.
- Add callback credential rotation, redaction, abuse prevention, and proxy-aware IP verification.
- Expand tests for failures, concurrency, permissions, reversals, and statement reconciliation.
- Pin supported Frappe/ERPNext dependencies and require passing CI checks before merge.

## Product and operations

- Retain ERPNext as accounting system of record while separating payment transport, validation, posting, and reconciliation into testable services.
- Add role-specific management, bursar, teacher, and parent dashboards with responsive design.
- Verify student-customer syncing, fee billing, promotions, examinations, staff workflows, and notifications.
- Add monitoring, backup restoration drills, operational runbooks, and staged deployment rollback.

## Acceptance gates

1. Clean install and complete automated test suite pass.
2. Sandbox valid/invalid/replayed payment and simultaneous-posting tests pass.
3. Fee balances reconcile with Payment Entry, Sales Invoice, and General Ledger.
4. Unauthorized parents/staff cannot access or modify another person's restricted records.
5. Callback/worker outages recover without losing payments; provider statement reconciles.
6. Restore test and production monitoring are verified before enabling live posting.

This document records recommendations, not completed implementations. See PAYMENT_SAFETY_REVIEW_2026-10-25.md for code changes and known limitations.
