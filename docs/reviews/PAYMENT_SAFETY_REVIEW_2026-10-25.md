# SchoolERP payment-safety review — 25 October 2026

**Branch:** `review/payment-safety-20261025`  
**Target:** `main`  
**Status:** Proposed changes for maintainer review; live Frappe/ERPNext integration tests NOT executed.

## Summary

This branch applies a small, reviewable first tranche of the payment audit, specifically to C2B confirmation input validation and callback acknowledgement reliability. It does **not** implement the complete payment-security roadmap. No production configuration or live payment has been changed.

## Changes implemented

1. **C2B envelope checks** (`school_erp/logic/paybill.py`, `school_erp/api/paybill.py`). `envelope_problems()` checks the raw Daraja payload: `BusinessShortCode` must match School Settings, a confirmation needs a `TransID`, and `TransAmount` must be a positive, finite amount with at most 2 decimals (parsed as a string, so malformed values never raise).
   - **Validation** (before the payment completes): a bad amount returns `C2B00013` (invalid amount); any other problem returns `C2B00016`.
   - **Confirmation** (money already received): a payment that fails the checks is **stored as `Needs Review`** with the reason, logged, never auto-posted or retried by the hourly job, and acknowledged. The bursar posts it with *Post to Student* after checking. Only a confirmation with no `TransID` (nothing to key a record on) is refused with HTTP 400, with the full payload in the Error Log for statement reconciliation.
   - `Needs Review` is shown in the transaction list/form, the Paybill Reconciliation report and the management dashboard's attention list.
2. **Failed persistence is no longer acknowledged as success** (`school_erp/api/paybill.py`). Unexpected failures while recording the confirmation now return HTTP 503, log a traceback, and roll back the request transaction.
3. **Tests.** Framework-free (`test_logic.py`): envelope checks for shortcode, missing reference, zero/negative/NaN/infinite/over-precise/non-numeric amounts, and payload normalisation never raising. Integration (`test_integration.py`): a wrong-shortcode confirmation is stored for review, skipped by the retry job and postable by the bursar; a non-numeric amount is stored for review; a missing TransID returns 400; validation result codes; a storage failure returns 503 and rolls back.

## Verification status

- `bash scripts/check.sh`: passed (27 logic tests, 56 DocTypes valid).
- `bench --site test.localhost run-tests --module school_erp.tests.test_integration` on Frappe/ERPNext 16.52: 11 tests passed.
- **Not executed:** Daraja Sandbox callbacks (reviewer checklist item 4).
- CI configuration exists in `.github/workflows/ci.yml`; review the new branch's Actions run before merge.
- No claim is made that Safaricom retries unsuccessful confirmation requests. HTTP 503 makes our failure visible; external reconciliation is mandatory even if a provider does not retry.

## Remaining issues — not fixed in this branch

| Priority | Finding | Proposed next action |
| --- | --- | --- |
| P0 | C2B insert race between existence check and unique-key insert | Catch unique-constraint violations and verify existing record content; test concurrent deliveries. |
| P0 | A callback is acknowledged after record storage, but worker enqueue/recovery semantics deserve an integration test | Test queue outage after commit, and scheduled recovery of `Received` transactions. |
| P0 | Token in callback URL is long-lived and may appear in access logs | Design rotation, log redaction, network/source verification and statement reconciliation. |
| P0 | STK results can be reported as paid before accounting posting completes | Distinguish `Provider Paid` from `Accounted`; verify amount, request identity and receipt. |
| P1 | Manual financial-record CRUD permissions are broad | Remove normal user delete/amount edit permissions; introduce audited reconciliation operations. |
| P1 | Fee Payment reference uniqueness is an application-level check | Test concurrent posting, reference collisions, and posted reversal workflows. |
| P1 | Monetary payload normalization currently uses `float` | Refactor to decimal-safe values end-to-end (callback parsing and accounting). |
| P1 | Failed-posting hourly retry is slow and unclassified | Introduce retry schedule and operational exception queue. |
| P1 | Parent-to-student STK authorization needs verification through the exposed API entry points | Add negative permission tests and rate limiting. |

## Reviewer checklist

1. Inspect the three source-file diffs and verify C2B behavior matches the contracted Safaricom payloads.
2. Run `bash scripts/check.sh`.
3. Run a clean Frappe/ERPNext v16 test bench: `bench --site test.localhost run-tests --app school_erp`.
4. Test genuine Sandbox C2B registration, validation and confirmation, including malformed, duplicate and wrong-shortcode callbacks.
5. Verify the production reverse proxy does not inadvertently leak callback query-string tokens.
6. **Do not merge or turn on live payments solely on the basis of this small patch.**

## Risk / compatibility

Requiring the expected shortcode may reject older/malformed sandbox fixtures or callbacks using a shortcode other than School Settings. Confirm the registered C2B shortcode and existing test fixtures before release. The existing API's HTTP 200 success response format is preserved for valid confirmations.
