# Refunds and credit notes: acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | 1,160 credit on a 5,800 invoice | Owes 4,640; return SI −1,160 with VAT 160 reversed; books agree | `test_credit_notes::test_partial_credit_reduces_what_is_owed` | [ ] |
| 2 | Full credit | Status Credited; no more credit allowed | `::test_full_credit_marks_credited` | [ ] |
| 3 | Paid 5,800, credit 2,000 with refund 2,000 | Owes 0, refunded 2,000; Payment Entry Pay from M-Pesa | `::test_refund_of_overpayment` | [ ] |
| 4 | Refund beyond overpayment or credit | Refused | `::test_refund_limited_to_money_overpaid` | [ ] |
| 5 | Cancel | Return and refund cancelled; balances restored | `::test_cancel_reverses_both` | [ ] |
| 6 | Cancel invoice with a credit note | Refused | `::test_invoice_cannot_be_cancelled_with_credit_notes` | [ ] |
| 7 | Tax invoice with KRA | Flagged Needed + alert; KRA number → Done | `::test_kra_credit_note_flagged` | [ ] |
| 8 | Payment after credit | Limited to the new balance | `::test_payment_cannot_exceed_balance_after_credit` | [ ] |

## Docs
- [x] README, CHANGELOG
