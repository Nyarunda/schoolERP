# SchoolERP payment-safety review — 25 October 2026

**Branch:** `review/payment-safety-20261025`  
**Target:** `main`  
**Status:** Proposed changes for maintainer review; live Frappe/ERPNext integration tests NOT executed.

## Summary

This branch applies a small, reviewable first tranche of the payment audit, specifically to C2B confirmation input validation and callback acknowledgement reliability. It does **not** implement the complete payment-security roadmap. No production configuration or live payment has been changed.

## Changes implemented

1. **C2B confirmation envelope validation** (`school_erp/logic/paybill.py`, `school_erp/api/paybill.py`). Require configured paybill shortcode to match incoming `BusinessShortCode`; require a transaction ID for confirmation; reject zero, negative, non-finite, and greater-than-two-decimal amounts. Validation-stage requests do not require a transaction ID.
2. **Failed persistence is no longer acknowledged as success** (`school_erp/api/paybill.py`). Unexpected failures while recording the confirmation now return HTTP 503, log a traceback, and roll back the request transaction.
3. **Framework-free regression tests** (`school_erp/tests/test_logic.py`). Added checks for valid records, wrong/missing shortcode, missing reference, zero/negative/NaN/infinite amounts, excess decimal precision, and validation requests before an ID exists.

## Verification status

- Files were changed and committed on this branch using the GitHub repository integration.
- **Not executed here:** `bash scripts/check.sh` and `bench --site test.localhost run-tests --app school_erp`.
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
