# Every shilling through the General Ledger: acceptance

| # | Given / when | Then | Test | On test site |
|---|---|---|---|---|
| 1 | A KES 500 cash pocket money deposit is submitted | A submitted JE: Dr Cash 500, Cr Pocket Money Held 500, linked on the transaction | `test_money_through_gl::test_deposit_posts` | [ ] |
| 2 | An M-Pesa deposit | Dr the M-Pesa mode's account | `::test_deposit_mpesa_account` | [ ] |
| 3 | A withdrawal of 200 | Dr Pocket Money Held 200, Cr Cash 200 | `::test_withdrawal_posts` | [ ] |
| 4 | Purchases in "Each purchase" mode | Each: Dr Pocket Money Held, Cr Tuck Shop Sales | `::test_purchase_each` | [ ] |
| 5 | Three purchases by one till user in "Daily summary" mode, then the daily job runs | One JE for the total; all three linked; running again posts nothing more | `::test_purchase_daily_summary` | [ ] |
| 6 | Refund, Adjustment In, Adjustment Out | Lines as in requirements 1 | `test_logic::test_pocket_money_lines` | [ ] |
| 7 | A posted deposit is cancelled | Its JE is cancelled; GL nets to zero | `::test_cancel_reverses` | [ ] |
| 8 | Existing balances total 3,000 and migrate runs | One opening JE Dr Temporary Opening 3,000, Cr Pocket Money Held 3,000; a second migrate adds none | `::test_opening_entry_once` | [ ] |
| 9 | After any of the above | Reconciliation shows GL Pocket Money Held = sum of balances (difference 0) | `::test_reconciliation` | [ ] |
| 10 | A validated M-Pesa payment with an unknown account number arrives | Status Unmatched; JE Dr M-Pesa, Cr Unidentified Receipts | `::test_unmatched_to_suspense` | [ ] |
| 11 | The bursar assigns it to a learner | Suspense JE cancelled; Fee Payment posted; Unidentified Receipts back to 0 | `::test_assign_clears_suspense` | [ ] |
| 12 | A Needs Review payment arrives | No JE until verified and posted | `::test_needs_review_not_posted` | [ ] |
| 13 | A teacher's fine of 50 is marked Fine Paid by cash | JE Dr Cash 50, Cr Library Fines 50; second click refused; waived fine can't be paid | `::test_fine_paid` | [ ] |
| 14 | Fees on and billing ticked | Fine still invoiced as today (no Fine Paid entry) | `::test_fine_billed_to_fees_unchanged` | [ ] |
| 15 | A Driver Daily Log with fuel cost 4,000 is submitted | A School Expense (Fuel, 4,000) in Pending Approval, linked both ways; approving posts Dr Fuel & Transport | `::test_fuel_expense_raised` | [ ] |
| 16 | That log is cancelled before approval | The expense is cancelled too | `::test_fuel_log_cancel` | [ ] |
| 17 | Accounts missing on a fresh company | Saving School Settings creates them under the right groups | `::test_accounts_created` | [ ] |
| 18 | A transaction exists without a posting | "Check Ledger" lists it | `::test_unposted_money` | [ ] |

## Not broken

- [ ] `./scripts/check.sh` and CI green
- [ ] Fee billing, Fee Payment, matched M-Pesa and expenses post exactly as before
- [ ] Shop staff can record purchases without Accounts roles
- [ ] School Viewer can read the new fields and the reconciliation
- [ ] Unlicensed module: nothing posts for it

## Docs

- [ ] `docs/ACCOUNTING.md` (accounts used by each kind of money)
- [ ] User guide: Fees/Finance, Pocket Money, Library, Transport sections
- [ ] `CHANGELOG.md`
