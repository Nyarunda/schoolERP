# Delete a school: acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | Preview | Counts of backups, domains, invoices, payments, commissions, tax records | `test_delete_school::test_preview` | [ ] |
| 2 | Schedule with the wrong words | Refused | `::test_schedule_needs_typed_confirmation` | [ ] |
| 3 | Schedule an Active school | Suspended; SaaS Deletion Scheduled for +7 days | `::test_schedule_suspends` | [ ] |
| 4 | Cancel during grace | Unsuspended, back to Active, deletion Cancelled | `::test_cancel_restores` | [ ] |
| 5 | Delete Now before the 7 days | Refused | `::test_not_before_grace` | [ ] |
| 6 | Due deletion runs (no tax records) | Final backup kept 90 days; drop-site called; backups and domains gone; invoices/payments cancelled and deleted; school record gone; SaaS Deletion Done | `::test_full_deletion` | [ ] |
| 7 | School with a KRA-submitted tax invoice | That invoice, its payment and tax records kept; school record status Deleted | `::test_tax_records_kept` | [ ] |
| 8 | Drop fails | SaaS Deletion Failed with the error, school record kept, Retry works | `::test_failure_and_retry` | [ ] |
| 9 | 90 days later | Final copy removed | `::test_final_copy_expires` | [ ] |
| 10 | Day before | Admins reminded once | `::test_reminder` | [ ] |
| 11 | Non-admin | Permission error | `::test_admin_only` | [ ] |

## Docs
- [x] README: Deleting a school
- [x] CHANGELOG
