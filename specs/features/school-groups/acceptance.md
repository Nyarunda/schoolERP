# Schools with several branches: acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | Group with 2 branches; a single school | Branch cost centers under the group's; single school under "Schools" | `test_school_groups::test_branch_cost_centers_under_the_group` | [ ] |
| 2 | Branch invoice and payment | Income lines and the Payment Entry carry the branch's cost center | `::test_invoice_and_payment_post_with_the_branch_cost_center` | [ ] |
| 3 | A school joins the group | Its cost center moves under the group | `::test_moving_a_school_into_a_group_moves_its_cost_center` | [ ] |
| 4 | Combined bill | Invoice emails go to the head office; not licence emails; separate billing → school | `::test_combined_billing_emails_go_to_head_office` | [ ] |
| 5 | Statement and a 4,000 group payment on 2 × 3,000 | Statement to head office (6,000); split 3,000 + 1,000 oldest first, refs /1 /2; 2,000 left; overpayment refused | `::test_statement_and_group_payment_oldest_first` | [ ] |
| 6 | Non-admin | Refused | `::test_admin_only` | [ ] |

## Docs
- [x] README, CHANGELOG
