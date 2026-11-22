# Stemic expenses: acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | Setup | 13 categories, each with an Expense account in the company | `test_expenses::test_categories_with_their_accounts` | [ ] |
| 2 | KES 11,600 incl. 1,600 VAT by bank | Dr Hosting 10,000, Dr Input VAT 1,600, Cr Bank 11,600 | `::test_expense_posts_with_vat` | [ ] |
| 3 | Cash / M-Pesa | Credit the cash / M-Pesa account | `::test_cash_and_mpesa_accounts` | [ ] |
| 4 | Cancel | Journal entry cancelled | `::test_cancel_reverses` | [ ] |
| 5 | VAT ≥ amount; no company | Refused | `::test_refused_without_company_and_bad_vat` | [ ] |
| 6 | Monthly repeat due | One draft for this month, chain carried; once | `::test_monthly_repeat_makes_one_draft` | [ ] |
| 7 | Expense without entry | Listed by Check Ledger; Post Missing Entries posts it | `::test_unposted_and_post_missing` | [ ] |
| 8 | This Month / report | Category totals; category column in the report | `::test_month_summary_and_report` | [ ] |

## Docs
- [x] README, CHANGELOG
