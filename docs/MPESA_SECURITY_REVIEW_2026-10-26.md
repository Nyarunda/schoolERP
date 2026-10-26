# SchoolERP M-Pesa payment security review — 26 October 2026

## Implemented in this review branch

- C2B validate/confirm rejects wrong shortcode and invalid/non-positive/non-finite/excess-precision amounts.
- C2B confirmation rejects missing receipt ID. Direct C2B record insertion also checks the envelope.
- C2B storage failures roll back and return non-success (503), instead of acknowledging a missing transaction. Provider retries cannot be assumed: reconcile.
- STK success must include a receipt, actual amount equal to requested amount, and the same payer phone number, before creating a Fee Payment.
- Successful STK status query without receipt stays pending a receipt-bearing callback instead of becoming a posted payment.
- Callback processing errors return non-success (503); logging and manual investigation are still necessary.
- Pure regression tests for malformed C2B and STK metadata.

## Not implemented and required before production

1. **Authenticity and reconciliation:** URL callback token is not proof Safaricom collected funds. Configure HTTPS, strong/rotated callback tokens, trusted ingress policy, rate limiting, restricted roles, and provider reconciliation. Do not claim Paybill C2B can always be individually queried: settlement statements/provider reports must be reconciled.
2. **Durable raw callback inbox:** isolate receipt/persistence from posting; guarantee replay and audit, with unique keys and transactional outbox. Current duplicate detection still has a check-then-insert race.
3. **Independent STK verification:** use STK Query where supported but do not infer receipt/amount/phone from a status-only response.
4. **Digital receipt verification:** build tenant-bound random verification reference + QR pointing to a public minimal-disclosure verification endpoint, which must verify the submitted Fee Payment and linked Payment Entry. Do not expose student balances or phone numbers.
5. **Operational exceptions:** missing callbacks, conflicting duplicates, settlement mismatch, payment reversals, orphan records, and manually assigned unmatched payments should have a bursar exception queue.
6. **Financial acceptance tests:** callback replay, same receipt conflicting payload, forged phone/amount, worker crash, failed DB commit, cancellation and reversal.

## Verify before merging

Run `pytest school_erp/tests/test_mpesa_security.py` in the Bench environment and the project's `bash scripts/check.sh`, plus Frappe integration tests. Retest sandbox C2B registration (600000) and STK (174379) separately on a disposable school; the current settings share a shortcode. Runtime results (26 October 2026, Daraja sandbox and a dev site):

- Paybill C2B on 600000: Safaricom's confirmation reached the public URL, passed these checks and was posted by Student ID.
- Paybill STK on 174379: the result arrived by Safaricom's callback.
- Buy Goods confirmations sent to the public URL: one paid to the till number was matched by the payer's phone and posted. One paid to the store number from a masked phone was left Unmatched.
- A foreign shortcode, an amount of 0.001 and a missing TransID were each refused with HTTP 400 and not stored.
- Till STK and Till C2B simulate cannot be tested in the sandbox, which has no Buy Goods shortcode. Prove them with a small live payment.

Two defects found in review were fixed: Till payments were refused (a till is reported by its store or its till number), and the STK payer-phone check never normalised numbers (`r"\\D"`).

**Do not enable live automatic posting solely on the strength of these changes.** Existing site data and uncommitted local changes were not touched.
