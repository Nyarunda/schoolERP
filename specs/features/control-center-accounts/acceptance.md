# Control Center accounts: acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | Company set, old switch off | Invoice posts anyway | `test_accounting::test_posting_is_compulsory_once_a_company_is_chosen` | [ ] |
| 2 | Invoice + payment made before a company was chosen | Listed by Check Ledger; Post Missing Entries posts both and the commission; then nothing listed, amounts agree | `test_accounting::test_post_missing_and_ledger_check` | [ ] |
| 3 | No company | Nothing posts | `test_accounting::test_nothing_is_posted_when_switched_off` | [ ] |
| 4 | Sidebar | Follows the layout; no link lost or doubled | `check.sh` | [ ] |

## Docs
- [x] README: Accounts
- [x] CHANGELOG
